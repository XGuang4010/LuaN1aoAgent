from __future__ import annotations

from pathlib import Path
from typing import Iterable

from dotenv import dotenv_values


PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROJECT_DOTENV = PROJECT_ROOT / ".env"


def _normalize_existing_paths(existing_paths: Iterable[str] | None) -> set[str] | None:
    if existing_paths is None:
        return None
    return {str(path).strip() for path in existing_paths}


def _path_exists(path: str, existing_paths: set[str] | None = None) -> bool:
    normalized = str(path).strip()
    if not normalized:
        return False
    if existing_paths is not None:
        return normalized in existing_paths
    return Path(normalized).exists()


def load_project_tool_env(dotenv_path: str | Path | None = None) -> dict[str, str]:
    env_path = Path(dotenv_path) if dotenv_path else PROJECT_DOTENV
    if not env_path.exists():
        return {}
    return {
        key: str(value).strip()
        for key, value in dotenv_values(env_path).items()
        if value is not None and str(value).strip()
    }


def resolve_project_tool(
    tool_name: str,
    env_var_name: str,
    tools_home_subpath: str,
    *,
    dotenv_path: str | Path | None = None,
    existing_paths: Iterable[str] | None = None,
) -> str | None:
    del tool_name

    env_map = load_project_tool_env(dotenv_path)
    normalized_existing_paths = _normalize_existing_paths(existing_paths)

    explicit = env_map.get(env_var_name, "").strip()
    if explicit and _path_exists(explicit, normalized_existing_paths):
        return explicit

    tools_home = env_map.get("TOOLS_HOME", "").strip()
    if tools_home:
        candidate = str(Path(tools_home) / tools_home_subpath)
        if _path_exists(candidate, normalized_existing_paths):
            return candidate

    return None
