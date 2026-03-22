import sqlite3
from datetime import timezone

import auth_router
import db
import links_router
from caching import SimpleTTLCache, invalidate_link_caches, redirect_cache, stats_cache
from links_router import cleanup_expired_links, generate_short_code
from utils import dt_to_str, utc_now


def test_hash_password_and_parse_bearer_token() -> None:
    assert auth_router.hash_password("abc") == auth_router.hash_password("abc")
    assert auth_router.hash_password("abc") != auth_router.hash_password("abcd")

    assert auth_router.parse_bearer_token(None) is None
    assert auth_router.parse_bearer_token("Token 123") is None
    assert auth_router.parse_bearer_token("Bearer") is None
    assert auth_router.parse_bearer_token("Bearer   mytoken   ") == "mytoken"
    assert auth_router.parse_bearer_token("bearer abc") == "abc"


def test_get_current_user_and_get_optional_user(test_db_path) -> None:
    conn = db.get_db()
    conn.execute(
        "INSERT INTO users (username, password_hash, token, created_at) VALUES (?, ?, ?, ?)",
        ("u_test", "h", "token123", dt_to_str(utc_now())),
    )
    conn.commit()
    conn.close()

    user = auth_router.get_current_user("Bearer token123")
    assert user["username"] == "u_test"

    optional_user = auth_router.get_optional_user("Bearer token123")
    assert optional_user is not None
    assert optional_user["username"] == "u_test"

    assert auth_router.get_optional_user(None) is None


def test_simple_ttl_cache_and_invalidate() -> None:
    cache = SimpleTTLCache()
    cache.set("k", 1, ttl_seconds=5)
    assert cache.get("k") == 1

    cache.delete("k")
    assert cache.get("k") is None

    cache.set("expired", 2, ttl_seconds=0)
    assert cache.get("expired") is None

    redirect_cache.set("code1", "https://example.com", ttl_seconds=30)
    stats_cache.set("code1", {"click_count": 1}, ttl_seconds=30)
    invalidate_link_caches("code1")
    assert redirect_cache.get("code1") is None
    assert stats_cache.get("code1") is None


def test_generate_short_code_retries_on_collision(monkeypatch) -> None:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE links (short_code TEXT UNIQUE)")
    conn.execute("INSERT INTO links (short_code) VALUES ('AAAAAAA')")
    conn.commit()

    sequence = iter(list("AAAAAAABBBBBBB"))
    monkeypatch.setattr(links_router.secrets, "choice", lambda _: next(sequence))

    code = generate_short_code(conn, length=7)
    assert code == "BBBBBBB"


def test_cleanup_expired_links_and_save_events(test_db_path) -> None:
    conn = db.get_db()
    now = utc_now()
    conn.execute(
        """
        INSERT INTO links (short_code, original_url, created_at, click_count, last_accessed_at, expires_at, owner_user_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "expired123",
            "https://expired.com",
            dt_to_str(now),
            7,
            dt_to_str(now.astimezone(timezone.utc)),
            dt_to_str(now),
            None,
        ),
    )
    conn.commit()

    deleted = cleanup_expired_links(conn)
    assert deleted == 1

    row = conn.execute("SELECT * FROM links WHERE short_code = ?", ("expired123",)).fetchone()
    assert row is None

    event = conn.execute("SELECT * FROM link_events WHERE short_code = ?", ("expired123",)).fetchone()
    assert event is not None
    assert event["remove_reason"] == "expired"
    assert event["click_count"] == 7

    deleted_again = cleanup_expired_links(conn)
    assert deleted_again == 0
    conn.close()
