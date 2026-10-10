import os
import tempfile
from pathlib import Path

import pytest

_tmp = tempfile.mkdtemp()
os.environ["HYPERLANE_DB_PATH"] = str(Path(_tmp) / "test.db")
os.environ["HYPERLANE_SECRET"] = "test-secret"
os.environ["HYPERLANE_FRONTEND_DIST"] = str(Path(_tmp) / "nodist")
os.environ["HYPERLANE_LLM_PROVIDER"] = "none"


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient

    from hyperlane.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture()
def user(client):
    """A logged-in user (creates one if needed)."""
    users = client.get("/api/users").json()
    if not users:
        u = client.post("/api/users", json={"name": "Test Pilot", "role": "developer"}).json()
    else:
        u = users[0]
    client.post("/api/auth/login", json={"user_id": u["id"]})
    return u
