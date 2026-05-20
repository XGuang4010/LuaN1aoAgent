import json
from pathlib import Path

from tools.searchsploit_wrapper import build_result_record, handle_args


def test_handle_args_returns_json_results_for_keyword_search(tmp_path: Path):
    exploit_root = tmp_path / "exploitdb"
    exploit_file = exploit_root / "exploits" / "php" / "webapps" / "51826.py"
    exploit_file.parent.mkdir(parents=True)
    exploit_file.write_text(
        "# Exploit Title: Wordpress Plugin Canto < 3.0.5 - RFI\n"
        "# CVE : CVE-2023-3452\n"
        "print('demo')\n",
        encoding="utf-8",
    )

    payload = handle_args(
        ["-j", "canto", "wordpress"],
        exploit_root=exploit_root,
        script_path=tmp_path / "searchsploit.py",
    )
    data = json.loads(payload)

    results = data["RESULTS_EXPLOIT"]
    assert len(results) == 1
    assert results[0]["Title"].startswith("Wordpress Plugin Canto")
    assert results[0]["EDB-ID"] == "51826"


def test_handle_args_supports_cve_search(tmp_path: Path):
    exploit_root = tmp_path / "exploitdb"
    exploit_file = exploit_root / "exploits" / "php" / "webapps" / "51826.py"
    exploit_file.parent.mkdir(parents=True)
    exploit_file.write_text(
        "# Exploit Title: Wordpress Plugin Canto < 3.0.5 - RFI\n"
        "# CVE : CVE-2023-3452\n",
        encoding="utf-8",
    )

    payload = handle_args(
        ["--cve", "2023-3452", "-j"],
        exploit_root=exploit_root,
        script_path=tmp_path / "searchsploit.py",
    )
    data = json.loads(payload)

    assert data["RESULTS_EXPLOIT"][0]["EDB-ID"] == "51826"


def test_handle_args_supports_path_lookup(tmp_path: Path):
    exploit_root = tmp_path / "exploitdb"
    exploit_file = exploit_root / "exploits" / "php" / "webapps" / "51826.py"
    exploit_file.parent.mkdir(parents=True)
    exploit_file.write_text(
        "# Exploit Title: Wordpress Plugin Canto < 3.0.5 - RFI\n"
        "# CVE : CVE-2023-3452\n",
        encoding="utf-8",
    )

    payload = handle_args(
        ["-p", "51826"],
        exploit_root=exploit_root,
        script_path=tmp_path / "searchsploit.py",
    )

    assert "Exploit: Wordpress Plugin Canto" in payload
    assert f"Path: {exploit_file}" in payload


def test_build_result_record_uses_relative_path(tmp_path: Path):
    exploit_root = tmp_path / "exploitdb"
    exploit_file = exploit_root / "exploits" / "php" / "webapps" / "51826.py"
    exploit_file.parent.mkdir(parents=True)
    exploit_file.write_text(
        "# Exploit Title: Demo Exploit\n",
        encoding="utf-8",
    )

    record = build_result_record(exploit_file, exploit_root)

    assert record["Path"] == str(Path("exploits") / "php" / "webapps" / "51826.py")
    assert record["Title"] == "Demo Exploit"
