## [LRN-20260519-001] correction

**Logged**: 2026-05-19T00:00:00Z
**Priority**: medium
**Status**: pending
**Area**: config

### Summary
项目命令应默认使用仓库内 `venv` 解释器，而不是假设系统全局 Python 在 PATH 中可用。

### Details
在本仓库的 PowerShell 环境中，裸命令 `python`、`pytest` 不一定可用。用户明确说明项目虚拟环境位于 `venv`。后续执行测试、启动服务和验证命令时，应统一使用 `d:\Projects\LuaN1aoAgent\venv\Scripts\python.exe`，避免因为 PATH 差异导致误判。

### Suggested Action
对本仓库后续所有 Python 与 pytest 调用，优先使用仓库虚拟环境解释器的绝对路径。

### Metadata
- Source: conversation
- Related Files: d:\Projects\LuaN1aoAgent\venv
- Tags: python, venv, powershell, correction

---
