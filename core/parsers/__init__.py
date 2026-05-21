from typing import Callable
from core.data_contracts import ToolFinding

PARSER_REGISTRY: dict[str, Callable[[str], list[ToolFinding]]] = {}


def register_parser(tool_name: str):
    def decorator(func: Callable[[str], list[ToolFinding]]):
        PARSER_REGISTRY[tool_name] = func
        return func
    return decorator


def parse_tool_output(tool_name: str, raw_output: str) -> list[ToolFinding]:
    parser = PARSER_REGISTRY.get(tool_name)
    if parser:
        return parser(raw_output)
    return fallback_parser(raw_output)


def fallback_parser(output: str) -> list[ToolFinding]:
    return [ToolFinding(category="raw_output", key="full", value=output[:2000], confidence=1.0)]


# Import parsers to register them
from core.parsers import nmap_parser
from core.parsers import dirsearch_parser
from core.parsers import httpx_parser
from core.parsers import http_parser
from core.parsers import subfinder_parser
from core.parsers import nuclei_parser
from core.parsers import sqlmap_parser
