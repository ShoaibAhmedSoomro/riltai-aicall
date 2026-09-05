from fastapi import APIRouter, Depends, HTTPException

from api.constants import ENABLE_SIGNUP
from api.db import db_client
from api.db.models import UserModel
from api.enums import OrgRole, PostHogEvent
from api.schemas.auth import (
    AuthResponse,
    LoginRequest,
    ProfileUpdateRequest,
    SignupRequest,
    UserProfileFields,
    UserResponse,
)
from api.services.auth.depends import get_user, require_local_auth
from api.services.organization_bootstrap import ensure_organization_bootstrapped
from api.services.posthog_client import capture_event
from api.utils.auth import create_jwt_token, hash_password, verify_password

router = APIRouter(
    prefix="/auth",
    tags=["auth"],
)


def _user_response(
    user: UserModel, *, organization_id: int | None = None
) -> UserResponse:
    """Shape a user for the wire.

    Single place on purpose: signup, login, /me and the profile update all
    return the same model, and they had already drifted once — login omitted
    the display name, so a returning user's stored name never reached the
    session cookie.
    """
    return UserResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        organization_id=(
            organization_id
            if organization_id is not None
            else user.selected_organization_id
        ),
        provider_id=user.provider_id,
        profile=UserProfileFields(**(user.profile or {})),
        created_at=user.created_at.isoformat() if user.created_at else None,
        is_superuser=bool(user.is_superuser),
    )


@router.post(
    "/signup",
    response_model=AuthResponse,
    dependencies=[Depends(require_local_auth)],
)
async def signup(request: SignupRequest):
    # An invite is resolved first because it decides two things: whether signup
    # is permitted at all on an invite-only install, and which organization the
    # new user lands in.
    invite = None
    if request.invite_token:
        invite = await db_client.get_acceptable_invite(request.invite_token)
        if invite is None:
            # One message for unknown, revoked, already-used and expired. The
            # endpoint is unauthenticated, so distinguishing them would let
            # anyone probe which tokens exist.
            raise HTTPException(
                status_code=400, detail="This invitation is no longer valid."
            )
        if invite.email != request.email.strip().lower():
            raise HTTPException(
                status_code=400,
                detail="This invitation was sent to a different email address.",
            )

    # ENABLE_SIGNUP=false means invite-only, not closed: an invitation is exactly
    # the permission that flag is withholding from the general public.
    if not ENABLE_SIGNUP and invite is None:
        raise HTTPException(status_code=403, detail="Signup is disabled")

    # Check if email is already taken
    existing_user = await db_client.get_user_by_email(request.email)
    if existing_user:
        raise HTTPException(status_code=409, detail="Email already registered")

    # Hash password and create user
    hashed = hash_password(request.password)
    user = await db_client.create_user_with_email(
        email=request.email,
        password_hash=hashed,
        name=request.name,
    )

    if invite is not None:
        # Join the inviting organization instead of creating a personal one.
        # Consume the invite BEFORE linking: mark_invite_accepted is conditional
        # on the row still being pending, so two concurrent signups on one token
        # cannot both produce a membership.
        if not await db_client.mark_invite_accepted(invite.id):
            raise HTTPException(
                status_code=400, detail="This invitation is no longer valid."
            )
        organization = await db_client.get_organization_by_id(invite.organization_id)
        if organization is None:
            raise HTTPException(
                status_code=400, detail="The inviting organization no longer exists."
            )
        await db_client.add_user_to_organization(
            user.id, organization.id, role=invite.role
        )
    else:
        # Create organization for the user
        org_provider_id = f"org_{user.provider_id}"
        organization, _ = await db_client.get_or_create_organization_by_provider_id(
            org_provider_id=org_provider_id, user_id=user.id
        )

        # Link user to organization. Explicitly admin: this person created the
        # organization, so they must be able to administer it.
        await db_client.add_user_to_organization(
            user.id, organization.id, role=OrgRole.ADMIN.value
        )

    await db_client.update_user_selected_organization(user.id, organization.id)

    # Create default service configuration. This never raises, so signup still
    # succeeds if MPS is down; `_handle_oss_auth` re-enters bootstrap on the
    # user's subsequent authenticated requests, so a failure here is recovered
    # rather than permanent. Doing it here anyway means the common case has a
    # model configuration and SIP connectivity by the time the UI first loads.
    await ensure_organization_bootstrapped(
        organization.id,
        created_by=user.provider_id,
    )

    # Create JWT token
    token = create_jwt_token(user.id, request.email)

    capture_event(
        distinct_id=str(user.provider_id),
        event=PostHogEvent.SIGNED_UP,
        properties={
            "organization_id": organization.id,
            "auth_provider": "local",
        },
    )

    return AuthResponse(
        token=token,
        user=_user_response(user, organization_id=organization.id),
    )


@router.post(
    "/login",
    response_model=AuthResponse,
    dependencies=[Depends(require_local_auth)],
)
async def login(request: LoginRequest):
    # Look up user by email
    user = await db_client.get_user_by_email(request.email)
    if not user or not user.password_hash:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # Verify password
    if not verify_password(request.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # Create JWT token
    token = create_jwt_token(user.id, user.email)

    capture_event(
        distinct_id=str(user.provider_id),
        event=PostHogEvent.SIGNED_IN,
        properties={
            "organization_id": user.selected_organization_id,
            "auth_provider": "local",
        },
    )

    return AuthResponse(
        token=token,
        user=_user_response(user),
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user(user: UserModel = Depends(get_user)):
    return _user_response(user)


@router.patch(
    "/profile",
    response_model=AuthResponse,
    dependencies=[Depends(require_local_auth)],
)
async def update_profile(
    request: ProfileUpdateRequest, user: UserModel = Depends(get_user)
):
    """Update the signed-in user's own display name, email or password.

    Local auth only. The hosted provider owns its users' identities and has its
    own account UI, so this route 404s there rather than writing rows the
    identity provider would then overwrite.

    Returns a fresh token because the JWT carries the email (api/utils/auth.py
    create_jwt_token): after an email change the old token describes a user who
    no longer exists under that address, and the OSS session cookie is a
    write-once snapshot, so the client needs a new one to stop showing stale
    details.
    """
    changing_password = request.new_password is not None

    if changing_password:
        if not user.password_hash:
            # A user created before email/password auth, or via another path,
            # has nothing to verify against.
            raise HTTPException(
                status_code=400, detail="This account has no password set"
            )
        if not request.current_password:
            raise HTTPException(
                status_code=400, detail="Current password is required to set a new one"
            )
        if not verify_password(request.current_password, user.password_hash):
            raise HTTPException(status_code=401, detail="Current password is incorrect")

    if (
        request.email is not None
        and request.email.lower() != (user.email or "").lower()
    ):
        existing = await db_client.get_user_by_email(request.email)
        if existing and existing.id != user.id:
            raise HTTPException(status_code=409, detail="Email already registered")

    updated = await db_client.update_user_profile(
        user.id,
        name=request.name,
        email=request.email,
        password_hash=hash_password(request.new_password)
        if changing_password
        else None,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="User not found")

    return AuthResponse(
        token=create_jwt_token(updated.id, updated.email),
        user=_user_response(updated),
    )
