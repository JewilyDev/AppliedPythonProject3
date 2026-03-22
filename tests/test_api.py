from datetime import timedelta

import db
from caching import redirect_cache
from utils import dt_to_str, utc_now


def register_user(client, username: str, password: str = "12345") -> None:
    response = client.post(
        "/auth/register",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200


def login_user(client, username: str, password: str = "12345") -> str:
    response = client.post(
        "/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    assert token
    return token


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_auth_register_login_and_validation(client) -> None:
    response = client.post("/auth/register", json={"username": "ab", "password": "12345"})
    assert response.status_code == 422

    response = client.post("/auth/register", json={"username": "bad name", "password": "12345"})
    assert response.status_code == 422

    response = client.post("/auth/register", json={"username": "student1", "password": "12345"})
    assert response.status_code == 200
    assert response.json() == {"message": "User created"}

    response = client.post("/auth/register", json={"username": "student1", "password": "12345"})
    assert response.status_code == 400
    assert response.json()["detail"] == "Username already exists"

    response = client.post("/auth/login", json={"username": "student1", "password": "12345"})
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]

    response = client.post("/auth/login", json={"username": "student1", "password": "wrong"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Wrong username or password"


def test_create_search_redirect_and_stats(client) -> None:
    response = client.post(
        "/links/shorten",
        json={"original_url": "https://example.com/path", "custom_alias": "portret"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["short_code"] == "portret"
    assert payload["short_url"].endswith("/links/portret")
    assert payload["original_url"] == "https://example.com/path"

    response = client.get("/links/search", params={"original_url": payload["original_url"]})
    assert response.status_code == 200
    items = response.json()
    assert len(items) == 1
    assert items[0]["short_code"] == "portret"

    response = client.get("/links/portret", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "https://example.com/path"

    response = client.get("/links/portret/stats")
    assert response.status_code == 200
    stats = response.json()
    assert stats["short_code"] == "portret"
    assert stats["click_count"] == 1
    assert stats["last_accessed_at"] is not None

    response = client.get("/links/portret", follow_redirects=False)
    assert response.status_code == 307

    response = client.get("/links/portret/stats")
    assert response.status_code == 200
    assert response.json()["click_count"] == 2


def test_alias_conflict_and_bad_alias(client) -> None:
    response = client.post(
        "/links/shorten",
        json={"original_url": "https://first.com", "custom_alias": "my_link"},
    )
    assert response.status_code == 200

    response = client.post(
        "/links/shorten",
        json={"original_url": "https://second.com", "custom_alias": "my_link"},
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "Alias is already taken"

    response = client.post(
        "/links/shorten",
        json={"original_url": "https://second.com", "custom_alias": "bad alias"},
    )
    assert response.status_code == 422


def test_optional_user_with_invalid_token_creates_anonymous_link(client) -> None:
    response = client.post(
        "/links/shorten",
        json={"original_url": "https://anonymous.com", "custom_alias": "anon_from_bad_token"},
        headers=auth_headers("invalid-token"),
    )
    assert response.status_code == 200

    conn = db.get_db()
    row = conn.execute("SELECT owner_user_id FROM links WHERE short_code = ?", ("anon_from_bad_token",)).fetchone()
    conn.close()
    assert row is not None
    assert row["owner_user_id"] is None


def test_update_delete_and_permissions(client) -> None:
    register_user(client, "owner1")
    register_user(client, "other1")
    owner_token = login_user(client, "owner1")
    other_token = login_user(client, "other1")

    response = client.post(
        "/links/shorten",
        json={"original_url": "https://owned.com", "custom_alias": "owned_link"},
        headers=auth_headers(owner_token),
    )
    assert response.status_code == 200

    response = client.put("/links/owned_link", json={"new_url": "https://new.com"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Authorization header required"

    response = client.put(
        "/links/owned_link",
        json={"new_url": "https://new.com"},
        headers=auth_headers("totally-wrong-token"),
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid token"

    response = client.put(
        "/links/owned_link",
        json={"new_url": "https://new.com"},
        headers=auth_headers(other_token),
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "You can edit only your links"

    response = client.delete("/links/owned_link", headers=auth_headers(other_token))
    assert response.status_code == 403
    assert response.json()["detail"] == "You can delete only your links"

    response = client.put(
        "/links/owned_link",
        json={"new_url": "https://new.com"},
        headers=auth_headers(owner_token),
    )
    assert response.status_code == 200

    response = client.delete("/links/owned_link", headers=auth_headers(owner_token))
    assert response.status_code == 200
    assert response.json()["message"] == "Link deleted"

    response = client.get("/links/owned_link/stats")
    assert response.status_code == 404

    response = client.get("/links/expired")
    assert response.status_code == 200
    assert any(item["short_code"] == "owned_link" and item["remove_reason"] == "manual_delete" for item in response.json())


def test_edit_and_delete_forbidden_for_anonymous_link(client) -> None:
    response = client.post(
        "/links/shorten",
        json={"original_url": "https://anon-only.com", "custom_alias": "anon_link"},
    )
    assert response.status_code == 200

    register_user(client, "editor1")
    token = login_user(client, "editor1")

    response = client.put(
        "/links/anon_link",
        json={"new_url": "https://new-anon.com"},
        headers=auth_headers(token),
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Anonymous links can not be edited"

    response = client.delete("/links/anon_link", headers=auth_headers(token))
    assert response.status_code == 403
    assert response.json()["detail"] == "Anonymous links can not be deleted"


def test_expiration_and_cleanup_unused(client) -> None:
    response = client.post(
        "/links/shorten",
        json={"original_url": "https://expired-target.com", "custom_alias": "exp_link"},
    )
    assert response.status_code == 200
    expired_original = response.json()["original_url"]

    response = client.post(
        "/links/shorten",
        json={"original_url": "https://stale-target.com", "custom_alias": "stale_link"},
    )
    assert response.status_code == 200
    stale_original = response.json()["original_url"]

    conn = db.get_db()
    old_time = dt_to_str(utc_now() - timedelta(days=40))
    conn.execute("UPDATE links SET expires_at = ? WHERE short_code = ?", (old_time, "exp_link"))
    conn.execute("UPDATE links SET created_at = ? WHERE short_code = ?", (old_time, "stale_link"))
    conn.commit()
    conn.close()

    response = client.get("/links/search", params={"original_url": expired_original})
    assert response.status_code == 200
    assert response.json() == []

    response = client.post("/links/cleanup-unused", params={"days": 30})
    assert response.status_code == 200
    assert response.json()["message"].startswith("Removed ")

    response = client.get("/links/search", params={"original_url": stale_original})
    assert response.status_code == 200
    assert response.json() == []

    response = client.get("/links/expired")
    assert response.status_code == 200
    history = response.json()
    assert any(item["short_code"] == "exp_link" and item["remove_reason"] == "expired" for item in history)
    assert any(item["short_code"] == "stale_link" and item["remove_reason"] == "unused_30_days" for item in history)


def test_cleanup_unused_days_validation(client) -> None:
    response = client.post("/links/cleanup-unused", params={"days": 0})
    assert response.status_code == 422

    response = client.post("/links/cleanup-unused", params={"days": 999})
    assert response.status_code == 422


def test_open_short_link_not_found_when_cached_url_exists(client) -> None:
    redirect_cache.set("ghost", "https://ghost.example.com", 300)
    response = client.get("/links/ghost", follow_redirects=False)
    assert response.status_code == 404


def test_mass_create_links_smoke(client) -> None:
    short_codes: set[str] = set()
    for i in range(20):
        response = client.post(
            "/links/shorten",
            json={"original_url": f"https://bulk{i}.example.com"},
        )
        assert response.status_code == 200
        short_codes.add(response.json()["short_code"])

    assert len(short_codes) == 20
