from __future__ import annotations

import json
import re
from pathlib import Path


def _extract_title(content: str, fallback: str) -> str:
    for line in content.splitlines():
        lowered = line.lower()
        if lowered.startswith("# exploit title:"):
            return line.split(":", 1)[1].strip()
    return fallback


def _extract_cve(content: str) -> str:
    match = re.search(r"\bCVE-\d{4}-\d+\b", content, re.IGNORECASE)
    return match.group(0).upper() if match else ""


def _extract_edb_id(file_path: Path) -> str:
    return file_path.stem


def build_result_record(file_path: Path, exploit_root: Path) -> dict[str, str]:
    content = file_path.read_text(encoding="utf-8", errors="ignore")
    relative_path = file_path.relative_to(exploit_root)
    return {
        "Title": _extract_title(content, file_path.name),
        "EDB-ID": _extract_edb_id(file_path),
        "Path": str(relative_path),
        "CVE": _extract_cve(content),
    }


def _iter_exploit_files(exploit_root: Path):
    exploits_dir = exploit_root / "exploits"
    if not exploits_dir.exists():
        return
    for file_path in exploits_dir.rglob("*"):
        if file_path.is_file():
            yield file_path


def _search_records(exploit_root: Path, terms: list[str]) -> list[dict[str, str]]:
    normalized_terms = [term.lower() for term in terms if term.strip()]
    results: list[dict[str, str]] = []
    for file_path in _iter_exploit_files(exploit_root) or []:
        record = build_result_record(file_path, exploit_root)
        haystack = " ".join(
            [
                record["Title"],
                record["Path"],
                record.get("CVE", ""),
                record["EDB-ID"],
            ]
        ).lower()
        if all(term in haystack for term in normalized_terms):
            results.append(record)
    return sorted(results, key=lambda item: item["EDB-ID"], reverse=True)


def _find_by_edb_id(exploit_root: Path, edb_id: str) -> dict[str, str] | None:
    for file_path in _iter_exploit_files(exploit_root) or []:
        if file_path.stem == str(edb_id):
            return build_result_record(file_path, exploit_root)
    return None


def _normalize_cve_arg(raw_cve: str) -> str:
    raw_cve = raw_cve.strip().upper()
    if raw_cve.startswith("CVE-"):
        return raw_cve
    return f"CVE-{raw_cve}"


def handle_args(args: list[str], *, exploit_root: Path, script_path: Path) -> str:
    if "-p" in args:
        index = args.index("-p")
        edb_id = args[index + 1]
        record = _find_by_edb_id(exploit_root, edb_id)
        if not record:
            return f"No Results for EDB-ID {edb_id}\n"
        abs_path = exploit_root / record["Path"]
        return (
            f"Exploit: {record['Title']}\n"
            f"    URL: https://www.exploit-db.com/exploits/{record['EDB-ID']}\n"
            f"   Path: {abs_path}\n"
        )

    terms: list[str] = []
    if "--cve" in args:
        index = args.index("--cve")
        terms.append(_normalize_cve_arg(args[index + 1]))
    for arg in args:
        if arg in {"-j", "--cve"}:
            continue
        if "--cve" in args and arg == args[args.index("--cve") + 1]:
            continue
        if arg.startswith("-"):
            continue
        terms.append(arg)

    records = _search_records(exploit_root, terms)
    return json.dumps({"RESULTS_EXPLOIT": records}, ensure_ascii=False)


def main() -> int:
    script_path = Path(__file__).resolve()
    exploit_root = script_path.parent / "searchsploit_db"
    print(handle_args(__import__("sys").argv[1:], exploit_root=exploit_root, script_path=script_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
