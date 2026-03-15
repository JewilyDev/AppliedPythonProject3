import string
from datetime import datetime, timezone


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def dt_to_str(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def str_to_dt(value: str | None) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def is_alias_valid(alias: str) -> bool:
    allowed = set(string.ascii_letters + string.digits + "_-")
    return 3 <= len(alias) <= 32 and all(ch in allowed for ch in alias)

