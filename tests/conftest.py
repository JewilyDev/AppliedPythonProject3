from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import db
import main
from caching import redirect_cache, stats_cache


@pytest.fixture(autouse=True)
def clear_caches() -> None:
    redirect_cache._data.clear()
    stats_cache._data.clear()


@pytest.fixture
def test_db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db_path = tmp_path / "test_hw3.db"
    monkeypatch.setattr(db, "DB_PATH", db_path)
    db.init_db()
    return db_path


@pytest.fixture
def client(test_db_path: Path) -> TestClient:
    with TestClient(main.app) as test_client:
        yield test_client
