import hashlib
import secrets
import sqlite3

from fastapi import APIRouter, Header, HTTPException

from db import get_db
from schemas import LoginRequest, MessageResponse, RegisterRequest, TokenResponse
from utils import dt_to_str, utc_now


router = APIRouter(prefix="/auth", tags=["auth"])


def hash_password(raw_password: str) -> str:
    return hashlib.sha256(raw_password.encode("utf-8")).hexdigest()


def get_user_by_token(conn: sqlite3.Connection, token: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM users WHERE token = ?",
        (token,),
    ).fetchone()


def parse_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.split(" ", maxsplit=1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip()


def get_current_user(authorization: str | None = Header(default=None)) -> sqlite3.Row:
    token = parse_bearer_token(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="Authorization header required")
    conn = get_db()
    user = get_user_by_token(conn, token)
    conn.close()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user


def get_optional_user(authorization: str | None = Header(default=None)) -> sqlite3.Row | None:
    token = parse_bearer_token(authorization)
    if not token:
        return None
    conn = get_db()
    user = get_user_by_token(conn, token)
    conn.close()
    return user


@router.post("/register", response_model=MessageResponse)
def register(payload: RegisterRequest) -> MessageResponse:
    conn = get_db()
    existing = conn.execute(
        "SELECT 1 FROM users WHERE username = ?",
        (payload.username,),
    ).fetchone()
    if existing:
        conn.close()
        raise HTTPException(status_code=400, detail="Username already exists")

    conn.execute(
        "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
        (payload.username, hash_password(payload.password), dt_to_str(utc_now())),
    )
    conn.commit()
    conn.close()
    return MessageResponse(message="User created")


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest) -> TokenResponse:
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM users WHERE username = ?",
        (payload.username,),
    ).fetchone()
    if not row or row["password_hash"] != hash_password(payload.password):
        conn.close()
        raise HTTPException(status_code=401, detail="Wrong username or password")

    token = secrets.token_urlsafe(24)
    conn.execute(
        "UPDATE users SET token = ? WHERE id = ?",
        (token, row["id"]),
    )
    conn.commit()
    conn.close()
    return TokenResponse(access_token=token)

