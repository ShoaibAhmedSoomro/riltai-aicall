"""SDK-level exceptions.

All errors raised from `social_cangaroo_sdk` are subclasses of `SocialCangarooSdkError` so
calling code can catch them as one category.
"""


class SocialCangarooSdkError(Exception):
    """Base class for all SDK errors."""


class ValidationError(SocialCangarooSdkError):
    """Raised when node data fails client-side validation (unknown field,
    missing required field, obvious type mismatch).

    Server-side Pydantic validation runs on save and may raise further
    errors via `ApiError` — this class covers the fast-fail cases caught
    at the `Workflow.add()` call site.
    """


class ApiError(SocialCangarooSdkError):
    """Raised when the Social Cangaroo backend returns a non-2xx response."""

    def __init__(self, status_code: int, message: str, body: object = None):
        super().__init__(f"[{status_code}] {message}")
        self.status_code = status_code
        self.body = body


class SpecMismatchError(SocialCangarooSdkError):
    """Raised when a referenced node type isn't registered on the server."""
