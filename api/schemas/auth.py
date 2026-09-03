from zoneinfo import available_timezones

from pydantic import BaseModel, EmailStr, Field, field_validator


class SignupRequest(BaseModel):
    email: EmailStr
    password: str
    name: str | None = None

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


# Fixed set so the UI can guarantee a readable avatar in both themes; a free
# hex would let a user pick something unreadable on their own dashboard.
AVATAR_COLORS = ("slate", "teal", "indigo", "amber", "rose", "violet")


class UserProfileFields(BaseModel):
    """Self-service preferences stored in ``users.profile``.

    Validated here rather than by the column so the JSON blob stays a known
    shape. Unknown keys are rejected outright: silently accepting them would
    let a typo persist forever as dead data nothing reads.
    """

    model_config = {"extra": "forbid"}

    job_title: str | None = Field(default=None, max_length=100)
    phone: str | None = Field(default=None, max_length=40)
    # Overrides the organization timezone for this user's dated reports.
    timezone: str | None = None
    avatar_color: str | None = None

    @field_validator("timezone")
    @classmethod
    def known_timezone(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        if v not in available_timezones():
            raise ValueError(f"Unknown timezone: {v}")
        return v

    @field_validator("avatar_color")
    @classmethod
    def known_color(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        if v not in AVATAR_COLORS:
            raise ValueError(f"Colour must be one of: {', '.join(AVATAR_COLORS)}")
        return v

    @field_validator("job_title", "phone")
    @classmethod
    def blank_is_cleared(cls, v: str | None) -> str | None:
        # An empty field in the form means "remove this", not "store an empty
        # string", so the stored blob never accumulates falsy noise.
        if v is None:
            return None
        return v.strip() or None


class ProfileUpdateRequest(BaseModel):
    """A partial profile update for the local auth provider.

    Every field is optional and only the ones present are applied, so changing
    a display name does not require re-sending the email. An empty string in
    ``name`` clears it; omitting the field leaves it alone.

    A password change requires ``current_password`` as well: possessing a valid
    session is not treated as proof of the old password, so a stolen token
    cannot be used to lock the owner out.
    """

    name: str | None = None
    email: EmailStr | None = None
    current_password: str | None = None
    new_password: str | None = None
    # Sent whole when any preference changes: the blob is small and replacing
    # it avoids a merge protocol for something the form always holds in full.
    profile: UserProfileFields | None = None

    @field_validator("new_password")
    @classmethod
    def password_min_length(cls, v: str | None) -> str | None:
        # Mirrors SignupRequest so a password set here cannot be weaker than
        # one accepted at signup.
        if v is not None and len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class UserResponse(BaseModel):
    id: int
    email: str | None
    name: str | None = None
    organization_id: int | None = None
    provider_id: str | None = None
    profile: UserProfileFields = Field(default_factory=UserProfileFields)
    # Read-only account facts a profile screen displays but cannot edit.
    created_at: str | None = None
    is_superuser: bool = False


class AuthResponse(BaseModel):
    token: str
    user: UserResponse
