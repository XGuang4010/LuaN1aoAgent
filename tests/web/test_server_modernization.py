import asyncio
import importlib
import os
import sys
from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient
from tools import mcp_client


def _reset_modules():
    for module_name in (
        "web.server",
        "web",
        "core.database",
        "core.database.utils",
        "core.database.models",
    ):
        sys.modules.pop(module_name, None)


def _reload_web_package(database_path: Path | None = None):
    if database_path is None:
        os.environ.pop("DATABASE_PATH", None)
    else:
        os.environ["DATABASE_PATH"] = str(database_path)
    _reset_modules()
    return importlib.import_module("web")


def _reload_web_server(database_path: Path):
    _reload_web_package(database_path)
    return importlib.import_module("web.server")


async def _seed_sessions(server_module, session_ids: list[str]):
    async with server_module.AsyncSessionLocal() as session:
        for index, session_id in enumerate(session_ids):
            session.add(
                server_module.SessionModel(
                    id=session_id,
                    name=f"task-{session_id}",
                    goal=f"goal-{session_id}",
                    status="pending",
                    sort_index=index + 10,
                    created_at=datetime.now(),
                    updated_at=datetime.now(),
                )
            )
        await session.commit()


def test_web_package_exposes_create_app():
    web = _reload_web_package()

    assert hasattr(web, "create_app")


def test_importing_web_does_not_import_web_server():
    _reload_web_package()

    assert "web.server" not in sys.modules


def test_homepage_returns_200_from_app_factory():
    web = _reload_web_package()
    app = web.create_app()
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200


def test_mcp_config_path_stays_bound_to_project_root(tmp_path, monkeypatch):
    server = _reload_web_server(tmp_path / "mcp_path.db")
    expected = Path(__file__).resolve().parents[2] / "mcp.json"

    monkeypatch.chdir(tmp_path)

    assert Path(server._get_mcp_config_path()).resolve() == expected.resolve()
    assert Path(mcp_client._get_mcp_config_path()).resolve() == expected.resolve()


def test_reorder_ops_accepts_structured_payload(tmp_path):
    server = _reload_web_server(tmp_path / "reorder_success.db")

    with TestClient(server.app) as client:
        asyncio.run(_seed_sessions(server, ["op-a", "op-b"]))

        response = client.post("/api/ops/reorder", json={"order": ["op-b", "op-a"]})

    assert response.status_code == 200
    assert response.json() == {"ok": True}

    async def _fetch_sort_indexes():
        async with server.AsyncSessionLocal() as session:
            rows = await session.execute(
                server.select(server.SessionModel).order_by(server.SessionModel.id)
            )
            return {
                item.id: item.sort_index
                for item in rows.scalars().all()
            }

    assert asyncio.run(_fetch_sort_indexes()) == {"op-a": 1, "op-b": 0}


def test_reorder_ops_rejects_invalid_payload(tmp_path):
    server = _reload_web_server(tmp_path / "reorder_invalid.db")

    with TestClient(server.app) as client:
        response = client.post("/api/ops/reorder", json={"order": "bad"})

    assert response.status_code == 422
