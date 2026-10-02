"""The organization-wide phone numbers list: one view of which agent answers which
number, across every provider account the organization has."""

import itertools
from types import SimpleNamespace

import pytest

from api.db.models import (
    OrganizationModel,
    TelephonyConfigurationModel,
    TelephonyPhoneNumberModel,
    TelephonyTrunkModel,
    UserModel,
    WorkflowModel,
)
from api.routes import organization as routes

_n = itertools.count()


async def _org(async_session):
    n = next(_n)
    org = OrganizationModel(provider_id=f"pn-org-{n}")
    async_session.add(org)
    await async_session.flush()
    user = UserModel(provider_id=f"pn-user-{n}", selected_organization_id=org.id)
    async_session.add(user)
    await async_session.flush()
    return org, user


async def _config(async_session, org, name, provider="twilio", inactive=False):
    cfg = TelephonyConfigurationModel(
        organization_id=org.id, name=name, provider=provider, credentials={}, inactive=inactive
    )
    async_session.add(cfg)
    await async_session.flush()
    return cfg


async def _number(async_session, org, cfg, address, *, workflow=None, trunk=None, label=None):
    row = TelephonyPhoneNumberModel(
        organization_id=org.id,
        telephony_configuration_id=cfg.id,
        address=address,
        address_normalized=address,
        address_type="pstn",
        label=label,
        inbound_workflow_id=workflow.id if workflow else None,
        telephony_trunk_id=trunk.id if trunk else None,
    )
    async_session.add(row)
    await async_session.flush()
    return row


def _as(user):
    return SimpleNamespace(selected_organization_id=user.selected_organization_id, id=user.id)


@pytest.mark.asyncio
async def test_numbers_from_every_provider_account_appear_together(db_session, async_session):
    org, user = await _org(async_session)
    twilio = await _config(async_session, org, "Dubai Twilio")
    sip = await _config(async_session, org, "Office PBX", provider="ari")
    await _number(async_session, org, twilio, "+971501111111")
    await _number(async_session, org, sip, "+971502222222")

    out = await routes.list_organization_phone_numbers(_as(user))

    got = {(p.address, p.telephony_configuration_name, p.telephony_provider) for p in out.phone_numbers}
    assert got == {
        ("+971501111111", "Dubai Twilio", "twilio"),
        ("+971502222222", "Office PBX", "ari"),
    }


@pytest.mark.asyncio
async def test_each_number_names_the_agent_that_answers_it_or_none(db_session, async_session):
    org, user = await _org(async_session)
    cfg = await _config(async_session, org, "Main")
    agent = WorkflowModel(name="Support Agent", organization_id=org.id, user_id=user.id)
    async_session.add(agent)
    await async_session.flush()
    await _number(async_session, org, cfg, "+971501111111", workflow=agent)
    await _number(async_session, org, cfg, "+971502222222")

    out = await routes.list_organization_phone_numbers(_as(user))

    by_addr = {p.address: p for p in out.phone_numbers}
    assert by_addr["+971501111111"].inbound_workflow_name == "Support Agent"
    assert by_addr["+971501111111"].inbound_workflow_id == agent.id
    assert by_addr["+971502222222"].inbound_workflow_name is None  # unassigned, not hidden


@pytest.mark.asyncio
async def test_the_trunk_and_an_inactive_account_are_shown(db_session, async_session):
    org, user = await _org(async_session)
    cfg = await _config(async_session, org, "Old account", provider="cloudonix", inactive=True)
    trunk = TelephonyTrunkModel(telephony_configuration_id=cfg.id, name="Primary carrier", settings={})
    async_session.add(trunk)
    await async_session.flush()
    await _number(async_session, org, cfg, "+971501111111", trunk=trunk)

    (only,) = (await routes.list_organization_phone_numbers(_as(user))).phone_numbers

    assert only.telephony_trunk_name == "Primary carrier"
    assert only.telephony_configuration_inactive is True


@pytest.mark.asyncio
async def test_another_organizations_numbers_are_never_listed(db_session, async_session):
    mine, my_user = await _org(async_session)
    theirs, _ = await _org(async_session)
    await _number(async_session, mine, await _config(async_session, mine, "Mine"), "+971501111111")
    await _number(async_session, theirs, await _config(async_session, theirs, "Theirs"), "+971509999999")

    out = await routes.list_organization_phone_numbers(_as(my_user))

    assert [p.address for p in out.phone_numbers] == ["+971501111111"]


@pytest.mark.asyncio
async def test_an_organization_with_no_numbers_gets_an_empty_list(db_session, async_session):
    _, user = await _org(async_session)
    assert (await routes.list_organization_phone_numbers(_as(user))).phone_numbers == []


@pytest.mark.asyncio
async def test_the_order_is_stable_by_account_then_creation(db_session, async_session):
    org, user = await _org(async_session)
    b = await _config(async_session, org, "B account")
    a = await _config(async_session, org, "A account")
    await _number(async_session, org, b, "+971503333333")
    await _number(async_session, org, a, "+971501111111")
    await _number(async_session, org, a, "+971502222222")

    out = await routes.list_organization_phone_numbers(_as(user))

    assert [p.address for p in out.phone_numbers] == ["+971501111111", "+971502222222", "+971503333333"]
