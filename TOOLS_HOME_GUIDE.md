# TOOLS_HOME Guide

## Purpose

This document defines the only supported external tool loading rule used by the project.

Supported tool root example:

```text
D:\Tools\PentestWorkspace
```

---

## Loading Rule

The project resolves external security tools from the project root `.env` only.

- only the repository-local `.env` is used
- system environment variables are not supported as a tool source
- `PATH` is not supported as a tool fallback
- missing project-local configuration causes direct failure

This rule applies consistently to:

- [tool_env.py](file:///d:/Projects/LuaN1aoAgent/tools/tool_env.py)
- [mcp_service.py](file:///d:/Projects/LuaN1aoAgent/tools/mcp_service.py)
- [domain_scanner.py](file:///d:/Projects/LuaN1aoAgent/domain_scanner.py)

---

## Environment Variables

Primary project-local variable:

```ini
TOOLS_HOME=D:\Tools\PentestWorkspace
```

Optional per-tool overrides in the same project root `.env`:

```ini
SQLMAP_PATH=
DIRSEARCH_PATH=
NUCLEI_PATH=
SUBFINDER_PATH=
PD_HTTPX_PATH=
SEARCHSPLOIT_PATH=
```

Important constraints:

- these variables must be configured in the project root `.env`
- setting them in the operating system environment does not make the project support that mode
- leaving them unset means the related tool is treated as not configured

---

## Resolution Order

Each tool is resolved with one fixed order:

1. explicit per-tool path from the project root `.env`
2. `TOOLS_HOME` plus the conventional subdirectory path from the project root `.env`
3. stop and fail

There is no additional lookup after step 2:

- no system environment variable fallback
- no inherited parent-process environment fallback
- no `PATH` lookup through `shutil.which()` or shell resolution

---

## Directory Layout

Recommended `TOOLS_HOME` layout:

```text
D:\Tools\PentestWorkspace\
├── dirsearch\
│   └── dirsearch.exe
├── httpx\
│   └── httpx.exe
├── nuclei\
│   └── nuclei.exe
├── searchsploit\
│   └── searchsploit.exe
├── sqlmap\
│   └── sqlmap.exe
└── subfinder\
    └── subfinder.exe
```

Tool meaning:

- `sqlmap`: SQL injection testing
- `dirsearch`: directory and file enumeration
- `nuclei`: template-based vulnerability scanning
- `subfinder`: subdomain discovery
- `httpx`: ProjectDiscovery HTTP probing tool
- `searchsploit`: local Exploit-DB lookup

`httpx` here specifically means **ProjectDiscovery httpx**, not the Python `httpx` CLI.

---

## Example Config

Minimal project-local config:

```ini
TOOLS_HOME=D:\Tools\PentestWorkspace
```

Explicit override example:

```ini
TOOLS_HOME=D:\Tools\PentestWorkspace
PD_HTTPX_PATH=D:\Tools\PentestWorkspace\httpx\httpx.exe
NUCLEI_PATH=D:\Tools\PentestWorkspace\nuclei\nuclei.exe
SUBFINDER_PATH=D:\Tools\PentestWorkspace\subfinder\subfinder.exe
```

---

## Current Status

Current tool availability under `TOOLS_HOME`:

- available: `sqlmap`, `dirsearch`, `nuclei`, `subfinder`, `httpx`
- missing: `searchsploit`

Current project behavior:

- `mcp_service.py` only accepts tool paths resolved from the project root `.env`
- `domain_scanner.py` only accepts tool paths resolved from the project root `.env`
- any missing tool configuration now fails directly with an explicit error

---

## One-Line Answer

The project supports external security tools from the repository-local `.env` only, and explicitly does not support system environment variables or `PATH` as fallback sources.
