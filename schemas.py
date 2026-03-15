import string
from datetime import datetime, timezone

from pydantic import BaseModel, Field, HttpUrl, field_validator

from utils import is_alias_valid, utc_now


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=40)
    password: str = Field(min_length=4, max_length=120)

    @field_validator("username")
    @classmethod
    def username_chars(cls, value: str) -> str:
        allowed = set(string.ascii_letters + string.digits + "_")
        if any(ch not in allowed for ch in value):
            raise ValueError("username can contain only letters, numbers and underscore")
        return value


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LinkCreateRequest(BaseModel):
    original_url: HttpUrl
    custom_alias: str | None = None
    expires_at: datetime | None = None

    @field_validator("custom_alias")
    @classmethod
    def alias_validator(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if not is_alias_valid(value):
            raise ValueError("custom_alias: use 3-32 symbols (letters, digits, _ and -)")
        return value

    @field_validator("expires_at")
    @classmethod
    def expiry_validator(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return value
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        if value <= utc_now():
            raise ValueError("expires_at must be in the future")
        return value


class LinkUpdateRequest(BaseModel):
    new_url: HttpUrl


class LinkCreateResponse(BaseModel):
    short_code: str
    short_url: str
    original_url: str
    created_at: datetime
    expires_at: datetime | None


class LinkStatsResponse(BaseModel):
    short_code: str
    original_url: str
    created_at: datetime
    click_count: int
    last_accessed_at: datetime | None
    expires_at: datetime | None


class LinkSearchItem(BaseModel):
    short_code: str
    original_url: str
    created_at: datetime
    expires_at: datetime | None


class ExpiredLinkItem(BaseModel):
    short_code: str
    original_url: str
    removed_at: datetime
    remove_reason: str
    click_count: int


class MessageResponse(BaseModel):
    message: str

