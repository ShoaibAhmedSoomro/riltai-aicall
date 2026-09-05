"""Grant or revoke the platform SuperAdmin tier.

`users.is_superuser` has existed for a long time, but nothing in the codebase
could ever set it: there was no endpoint, no script, no seed and no data
migration. The only way to create a superuser was to write SQL against the
database by hand, which is a poor story for a tier that can impersonate any
user in any organization.

Run from the repo root with the api environment available:

    python -m scripts.grant_superuser someone@example.com
    python -m scripts.grant_superuser someone@example.com --revoke
    python -m scripts.grant_superuser --list

Deliberately a script and not an endpoint. The tier spans every tenant, so
granting it should require access to the server rather than a session in the
product -- there is no in-app path to escalate to it, by design.
"""

import argparse
import asyncio
import sys

from loguru import logger

logger.remove()

from api.db import db_client  # noqa: E402
from api.db.models import UserModel  # noqa: E402


async def _set_flag(user: UserModel, value: bool) -> None:
    """Write the flag directly.

    There is no db client method for this and adding one would put a
    superuser-granting helper on the shared client, reachable from request
    handlers. Keeping the write here keeps the only path to the tier on the
    server.
    """
    from sqlalchemy import update

    async with db_client.async_session() as session:
        await session.execute(
            update(UserModel).where(UserModel.id == user.id).values(is_superuser=value)
        )
        await session.commit()


async def _list() -> int:
    from sqlalchemy import select

    async with db_client.async_session() as session:
        result = await session.execute(
            select(UserModel).where(UserModel.is_superuser.is_(True)).order_by(UserModel.id)
        )
        users = list(result.scalars().all())

    if not users:
        # Worth saying plainly: an install with no superuser has nobody who can
        # use the /superadmin surface or impersonate for support.
        print("No superusers. Grant one with: python -m scripts.grant_superuser <email>")
        return 0
    print(f"{len(users)} superuser(s):")
    for u in users:
        print(f"  id={u.id}  {u.email or '(no email)'}  provider_id={u.provider_id}")
    return 0


async def _main(email: str, revoke: bool) -> int:
    user = await db_client.get_user_by_email(email)
    if user is None:
        print(f"No user with email {email!r}.", file=sys.stderr)
        print("Check the address, or list users in the database. This script does "
              "not create accounts.", file=sys.stderr)
        return 1

    # is_superuser was added nullable with no backfill, so pre-existing rows hold
    # NULL rather than False. Compare truthily or a NULL reads as "already set".
    already = bool(user.is_superuser)
    want = not revoke
    if already == want:
        state = "already a superuser" if want else "already not a superuser"
        print(f"{email} is {state}. Nothing to do.")
        return 0

    if revoke:
        # Refuse to remove the last one: nothing in the product can grant the
        # tier back, so an install with zero superusers needs this script and
        # server access to recover -- which is exactly what someone revoking
        # remotely may be about to lose.
        from sqlalchemy import func, select

        async with db_client.async_session() as session:
            result = await session.execute(
                select(func.count()).select_from(UserModel).where(
                    UserModel.is_superuser.is_(True)
                )
            )
            if int(result.scalar() or 0) <= 1:
                print("Refusing: this is the only superuser, and nothing in the "
                      "product can grant the tier back.", file=sys.stderr)
                return 1

    await _set_flag(user, want)
    verb = "Granted" if want else "Revoked"
    print(f"{verb} SuperAdmin for {email} (user id {user.id}).")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("email", nargs="?", help="the account to change")
    parser.add_argument("--revoke", action="store_true", help="remove the tier instead")
    parser.add_argument("--list", action="store_true", help="show current superusers")
    args = parser.parse_args()

    if args.list:
        raise SystemExit(asyncio.run(_list()))
    if not args.email:
        parser.error("an email is required unless --list is given")
    raise SystemExit(asyncio.run(_main(args.email, args.revoke)))


if __name__ == "__main__":
    main()
