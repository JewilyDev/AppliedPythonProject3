import secrets
import sqlite3
import string
from datetime import timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import HttpUrl

from auth_router import get_current_user, get_optional_user
from caching import invalidate_link_caches, redirect_cache, stats_cache
from db import get_db
from schemas import (
    ExpiredLinkItem,
    LinkCreateRequest,
    LinkCreateResponse,
    LinkSearchItem,
    LinkStatsResponse,
    LinkUpdateRequest,
    MessageResponse,
)
from utils import dt_to_str, str_to_dt, utc_now


router = APIRouter(prefix="/links", tags=["links"])

CODE_ALPHABET = string.ascii_letters + string.digits
REDIRECT_CACHE_TTL_SECONDS = 300
STATS_CACHE_TTL_SECONDS = 120


def build_short_url(request: Request, short_code: str) -> str:
    return f"{request.base_url}links/{short_code}"


def generate_short_code(conn: sqlite3.Connection, length: int = 7) -> str:
    while True:
        short_code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(length))
        exists = conn.execute(
            "SELECT 1 FROM links WHERE short_code = ?",
            (short_code,),
        ).fetchone()
        if not exists:
            return short_code


def save_removed_link(conn: sqlite3.Connection, row: sqlite3.Row, reason: str) -> None:
    conn.execute(
        """
        INSERT INTO link_events (
            short_code, original_url, created_at, removed_at, remove_reason, click_count, last_accessed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            row["short_code"],
            row["original_url"],
            row["created_at"],
            dt_to_str(utc_now()),
            reason,
            row["click_count"],
            row["last_accessed_at"],
        ),
    )


def cleanup_expired_links(conn: sqlite3.Connection) -> int:
    now_iso = dt_to_str(utc_now())
    expired_rows = conn.execute(
        "SELECT * FROM links WHERE expires_at IS NOT NULL AND expires_at <= ?",
        (now_iso,),
    ).fetchall()
    deleted = 0
    for row in expired_rows:
        save_removed_link(conn, row, reason="expired")
        conn.execute("DELETE FROM links WHERE id = ?", (row["id"],))
        invalidate_link_caches(row["short_code"])
        deleted += 1
    if deleted:
        conn.commit()
    return deleted


@router.get("/search", response_model=list[LinkSearchItem])
def search_links(original_url: HttpUrl = Query(...)) -> list[LinkSearchItem]:
    conn = get_db()
    cleanup_expired_links(conn)
    rows = conn.execute(
        """
        SELECT short_code, original_url, created_at, expires_at
        FROM links
        WHERE original_url = ?
        ORDER BY created_at DESC
        """,
        (str(original_url),),
    ).fetchall()
    conn.close()
    return [
        LinkSearchItem(
            short_code=row["short_code"],
            original_url=row["original_url"],
            created_at=str_to_dt(row["created_at"]),
            expires_at=str_to_dt(row["expires_at"]),
        )
        for row in rows
    ]


@router.post("/shorten", response_model=LinkCreateResponse)
def create_short_link(
    payload: LinkCreateRequest,
    request: Request,
    user: sqlite3.Row | None = Depends(get_optional_user),
) -> LinkCreateResponse:
    conn = get_db()
    cleanup_expired_links(conn)

    short_code = payload.custom_alias
    if short_code:
        exists = conn.execute(
            "SELECT 1 FROM links WHERE short_code = ?",
            (short_code,),
        ).fetchone()
        if exists:
            conn.close()
            raise HTTPException(status_code=409, detail="Alias is already taken")
    else:
        short_code = generate_short_code(conn)

    created_at = utc_now()
    expires_at = payload.expires_at
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    conn.execute(
        """
        INSERT INTO links (short_code, original_url, created_at, expires_at, owner_user_id)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            short_code,
            str(payload.original_url),
            dt_to_str(created_at),
            dt_to_str(expires_at),
            user["id"] if user else None,
        ),
    )
    conn.commit()
    conn.close()

    return LinkCreateResponse(
        short_code=short_code,
        short_url=build_short_url(request, short_code),
        original_url=str(payload.original_url),
        created_at=created_at,
        expires_at=expires_at,
    )


@router.get("/expired", response_model=list[ExpiredLinkItem])
def expired_links_history() -> list[ExpiredLinkItem]:
    conn = get_db()
    rows = conn.execute(
        """
        SELECT short_code, original_url, removed_at, remove_reason, click_count
        FROM link_events
        ORDER BY removed_at DESC
        """,
    ).fetchall()
    conn.close()
    return [
        ExpiredLinkItem(
            short_code=row["short_code"],
            original_url=row["original_url"],
            removed_at=str_to_dt(row["removed_at"]),
            remove_reason=row["remove_reason"],
            click_count=row["click_count"],
        )
        for row in rows
    ]


@router.post("/cleanup-unused", response_model=MessageResponse)
def cleanup_unused_links(days: int = Query(default=30, ge=1, le=365)) -> MessageResponse:
    conn = get_db()
    cleanup_expired_links(conn)

    threshold = utc_now() - timedelta(days=days)
    threshold_iso = dt_to_str(threshold)
    rows = conn.execute(
        """
        SELECT * FROM links
        WHERE (last_accessed_at IS NOT NULL AND last_accessed_at <= ?)
           OR (last_accessed_at IS NULL AND created_at <= ?)
        """,
        (threshold_iso, threshold_iso),
    ).fetchall()

    removed = 0
    for row in rows:
        save_removed_link(conn, row, reason=f"unused_{days}_days")
        conn.execute("DELETE FROM links WHERE id = ?", (row["id"],))
        invalidate_link_caches(row["short_code"])
        removed += 1

    conn.commit()
    conn.close()
    return MessageResponse(message=f"Removed {removed} unused links")


@router.get("/{short_code}")
def open_short_link(short_code: str) -> RedirectResponse:
    cached_url = redirect_cache.get(short_code)

    conn = get_db()
    cleanup_expired_links(conn)

    if cached_url is None:
        row = conn.execute(
            "SELECT * FROM links WHERE short_code = ?",
            (short_code,),
        ).fetchone()
        if not row:
            conn.close()
            raise HTTPException(status_code=404, detail="Short link not found")
        target_url = row["original_url"]
        redirect_cache.set(short_code, target_url, REDIRECT_CACHE_TTL_SECONDS)
    else:
        target_url = cached_url
        row = conn.execute(
            "SELECT * FROM links WHERE short_code = ?",
            (short_code,),
        ).fetchone()
        if not row:
            conn.close()
            raise HTTPException(status_code=404, detail="Short link not found")

    now = dt_to_str(utc_now())
    conn.execute(
        """
        UPDATE links
        SET click_count = click_count + 1,
            last_accessed_at = ?
        WHERE id = ?
        """,
        (now, row["id"]),
    )
    conn.commit()
    conn.close()
    stats_cache.delete(short_code)
    return RedirectResponse(url=target_url, status_code=307)


@router.get("/{short_code}/stats", response_model=LinkStatsResponse)
def get_link_stats(short_code: str) -> LinkStatsResponse:
    cached_stats = stats_cache.get(short_code)
    if cached_stats:
        return cached_stats

    conn = get_db()
    cleanup_expired_links(conn)
    row = conn.execute(
        "SELECT * FROM links WHERE short_code = ?",
        (short_code,),
    ).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Short link not found")

    response = LinkStatsResponse(
        short_code=row["short_code"],
        original_url=row["original_url"],
        created_at=str_to_dt(row["created_at"]),
        click_count=row["click_count"],
        last_accessed_at=str_to_dt(row["last_accessed_at"]),
        expires_at=str_to_dt(row["expires_at"]),
    )
    stats_cache.set(short_code, response, STATS_CACHE_TTL_SECONDS)
    return response


@router.put("/{short_code}", response_model=MessageResponse)
def update_link(
    short_code: str,
    payload: LinkUpdateRequest,
    user: sqlite3.Row = Depends(get_current_user),
) -> MessageResponse:
    conn = get_db()
    cleanup_expired_links(conn)
    row = conn.execute(
        "SELECT * FROM links WHERE short_code = ?",
        (short_code,),
    ).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Short link not found")
    if row["owner_user_id"] is None:
        conn.close()
        raise HTTPException(status_code=403, detail="Anonymous links can not be edited")
    if row["owner_user_id"] != user["id"]:
        conn.close()
        raise HTTPException(status_code=403, detail="You can edit only your links")

    conn.execute(
        "UPDATE links SET original_url = ? WHERE id = ?",
        (str(payload.new_url), row["id"]),
    )
    conn.commit()
    conn.close()
    invalidate_link_caches(short_code)
    return MessageResponse(message="Link updated")


@router.delete("/{short_code}", response_model=MessageResponse)
def delete_link(short_code: str, user: sqlite3.Row = Depends(get_current_user)) -> MessageResponse:
    conn = get_db()
    cleanup_expired_links(conn)
    row = conn.execute(
        "SELECT * FROM links WHERE short_code = ?",
        (short_code,),
    ).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Short link not found")
    if row["owner_user_id"] is None:
        conn.close()
        raise HTTPException(status_code=403, detail="Anonymous links can not be deleted")
    if row["owner_user_id"] != user["id"]:
        conn.close()
        raise HTTPException(status_code=403, detail="You can delete only your links")

    save_removed_link(conn, row, reason="manual_delete")
    conn.execute("DELETE FROM links WHERE id = ?", (row["id"],))
    conn.commit()
    conn.close()
    invalidate_link_caches(short_code)
    return MessageResponse(message="Link deleted")
