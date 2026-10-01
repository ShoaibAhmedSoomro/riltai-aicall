"""The product is priced in one currency. A rate typed as dollars and stored as
dirhams would be a 3.67x error in every cost figure, so it is refused."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from api.constants import BILLING_CURRENCY
from api.routes import organization_usage as routes


def _user():
    return SimpleNamespace(selected_organization_id=1)


@pytest.mark.asyncio
async def test_a_dollar_rate_card_is_refused_not_stored_as_dirhams(monkeypatch):
    upsert = AsyncMock()
    monkeypatch.setattr(routes.db_client, "upsert_configuration", upsert)

    with pytest.raises(HTTPException) as exc:
        await routes.save_usage_rate_card(
            routes.UsageRateCardRequest(price_per_minute_usd=0.1, currency="USD"),
            _user(),
        )

    assert exc.value.status_code == 422
    upsert.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_rate_card_without_a_currency_is_stored_in_dirhams(monkeypatch):
    upsert = AsyncMock()
    monkeypatch.setattr(routes.db_client, "upsert_configuration", upsert)

    resp = await routes.save_usage_rate_card(
        routes.UsageRateCardRequest(price_per_minute_usd=0.35), _user()
    )

    assert BILLING_CURRENCY == "AED"
    assert upsert.await_args.args[2] == {
        "price_per_minute_usd": 0.35,
        "currency": "AED",
    }
    assert resp.currency == "AED"
