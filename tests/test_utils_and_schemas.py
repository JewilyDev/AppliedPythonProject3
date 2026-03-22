from datetime import datetime, timedelta

import pytest
from pydantic import ValidationError

from schemas import LinkCreateRequest, RegisterRequest
from utils import dt_to_str, is_alias_valid, str_to_dt, utc_now


def test_utc_now_is_timezone_aware() -> None:
    value = utc_now()
    assert value.tzinfo is not None


def test_dt_to_str_and_str_to_dt() -> None:
    assert dt_to_str(None) is None
    assert str_to_dt(None) is None

    naive_dt = datetime(2030, 1, 1, 12, 30, 0)
    iso_string = dt_to_str(naive_dt)
    assert iso_string == "2030-01-01T12:30:00+00:00"

    parsed = str_to_dt("2030-01-01T12:30:00")
    assert parsed is not None
    assert parsed.tzinfo is not None
    assert parsed.year == 2030


def test_alias_validation_function() -> None:
    assert is_alias_valid("good_alias-123")
    assert not is_alias_valid("ab")
    assert not is_alias_valid("bad alias")
    assert not is_alias_valid("!")


def test_register_request_validation() -> None:
    valid = RegisterRequest(username="student_1", password="12345")
    assert valid.username == "student_1"

    with pytest.raises(ValidationError):
        RegisterRequest(username="bad name", password="12345")


def test_link_create_request_validators() -> None:
    future_naive = datetime.utcnow() + timedelta(days=1)
    item = LinkCreateRequest(
        original_url="https://example.com",
        custom_alias="alias_ok",
        expires_at=future_naive,
    )
    assert item.custom_alias == "alias_ok"
    assert item.expires_at is not None
    assert item.expires_at.tzinfo is not None

    with pytest.raises(ValidationError):
        LinkCreateRequest(
            original_url="https://example.com",
            custom_alias="bad alias",
        )

    with pytest.raises(ValidationError):
        LinkCreateRequest(
            original_url="https://example.com",
            custom_alias="alias_ok",
            expires_at=utc_now() - timedelta(seconds=5),
        )
