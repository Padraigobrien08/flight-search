import tomllib
from pathlib import Path

from fastapi.testclient import TestClient

BACKEND = Path(__file__).resolve().parents[2]


def test_container_and_fly_config():
    dockerfile = (BACKEND / "Dockerfile").read_text()
    assert "uv" in dockerfile and "USER" in dockerfile
    fly = tomllib.loads((BACKEND / "fly.toml").read_text())
    assert fly["http_service"]["internal_port"] == 8000
    assert fly["http_service"]["min_machines_running"] == 0


def test_health_reports_deploy_state():
    from app.main import app

    body = TestClient(app).get("/api/health").json()
    assert {"version", "fare_provider", "spend_cap_reached"} <= set(body)
