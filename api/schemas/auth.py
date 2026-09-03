from pydantic import BaseModel, EmailStr, field_validator


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


class AuthResponse(BaseModel):
    token: str
    user: UserResponse
