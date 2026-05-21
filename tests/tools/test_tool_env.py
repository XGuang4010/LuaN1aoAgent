from pathlib import Path

from tools import tool_env


def test_resolve_project_tool_prefers_explicit_tool_path(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "TOOLS_HOME=D:\\Tools\\PentestWorkspace\n"
        "NUCLEI_PATH=D:\\Custom\\nuclei.exe\n",
        encoding="utf-8",
    )

    resolved = tool_env.resolve_project_tool(
        tool_name="nuclei",
        env_var_name="NUCLEI_PATH",
        tools_home_subpath=r"nuclei\nuclei.exe",
        dotenv_path=env_file,
        existing_paths={
            r"D:\Custom\nuclei.exe",
            r"D:\Tools\PentestWorkspace\nuclei\nuclei.exe",
        },
    )

    assert resolved == r"D:\Custom\nuclei.exe"


def test_resolve_project_tool_returns_none_when_not_configured(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text("", encoding="utf-8")

    resolved = tool_env.resolve_project_tool(
        tool_name="nuclei",
        env_var_name="NUCLEI_PATH",
        tools_home_subpath=r"nuclei\nuclei.exe",
        dotenv_path=env_file,
        existing_paths=set(),
    )

    assert resolved is None
