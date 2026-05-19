# Web Modernization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `web/` 层迁移到当前新版 FastAPI/Starlette 推荐写法，修复首页 500 与已知 warning，并补齐最小回归测试与版本约束。

**Architecture:** 保持现有 Web API 语义不变，只重构应用初始化、生命周期、模板调用、包入口与请求体验证边界。通过 `create_app()` 集中应用装配逻辑，使用 `lifespan` 取代旧启动事件，使用基于文件位置的资源路径提升启动稳定性。

**Tech Stack:** Python 3.10+, FastAPI, Starlette, Pydantic, Jinja2, SSE-Starlette, Pytest

---

## 文件结构

- 修改：`d:\Projects\LuaN1aoAgent\web\server.py`
  - 负责 Web 应用初始化、路由、SSE、任务启动与模板渲染
- 修改：`d:\Projects\LuaN1aoAgent\web\__init__.py`
  - 负责 Web 包导出策略，消除导入副作用
- 修改：`d:\Projects\LuaN1aoAgent\requirements.txt`
  - 负责固定 Web 主栈依赖组合
- 新增：`d:\Projects\LuaN1aoAgent\tests\web\test_server_modernization.py`
  - 负责覆盖首页渲染、应用构造与包导入行为

## Task 1: 先锁定失败场景

**Files:**
- Create: `d:\Projects\LuaN1aoAgent\tests\web\test_server_modernization.py`
- Modify: `d:\Projects\LuaN1aoAgent\web\server.py`
- Modify: `d:\Projects\LuaN1aoAgent\web\__init__.py`

- [ ] **Step 1: 写首页渲染失败测试**

```python
from fastapi.testclient import TestClient

from web.server import app


def test_index_returns_200():
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert "html" in response.headers["content-type"].lower()
```

- [ ] **Step 2: 写应用构造测试**

```python
from web.server import create_app


def test_create_app_exposes_root_route():
    app = create_app()
    route_paths = {route.path for route in app.routes}
    assert "/" in route_paths
    assert "/api/ops" in route_paths
```

- [ ] **Step 3: 写包导入无副作用测试**

```python
import importlib
import sys


def test_import_web_package_does_not_import_web_server():
    sys.modules.pop("web", None)
    sys.modules.pop("web.server", None)

    importlib.import_module("web")

    assert "web.server" not in sys.modules
```

- [ ] **Step 4: 运行测试确认当前失败**

Run:

```powershell
& 'd:\Projects\LuaN1aoAgent\venv\Scripts\python.exe' -m pytest d:\Projects\LuaN1aoAgent\tests\web\test_server_modernization.py -v
```

Expected:

```text
FAILED test_index_returns_200
FAILED test_create_app_exposes_root_route
FAILED test_import_web_package_does_not_import_web_server
```

- [ ] **Step 5: 提交测试基线**

```bash
git add tests/web/test_server_modernization.py
git commit -m "test: add web modernization regression coverage"
```

## Task 2: 重构应用初始化与生命周期

**Files:**
- Modify: `d:\Projects\LuaN1aoAgent\web\server.py`
- Test: `d:\Projects\LuaN1aoAgent\tests\web\test_server_modernization.py`

- [ ] **Step 1: 引入基于文件位置的路径常量**

将 `web/server.py` 顶部的相对路径初始化替换为：

```python
from contextlib import asynccontextmanager
from pathlib import Path


WEB_DIR = Path(__file__).resolve().parent
STATIC_DIR = WEB_DIR / "static"
TEMPLATES_DIR = WEB_DIR / "templates"

STATIC_DIR.mkdir(parents=True, exist_ok=True)
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
```

- [ ] **Step 2: 用 `lifespan` 取代 `on_event`**

在 `web/server.py` 中新增：

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield
```

并删除：

```python
@app.on_event("startup")
async def startup_event():
    await init_db()
```

- [ ] **Step 3: 引入 `create_app()` 工厂函数**

将应用初始化收敛为：

```python
def create_app() -> FastAPI:
    app = FastAPI(title="鸾鸟自主渗透系统 Web (DB Mode)", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    return app


app = create_app()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
```

- [ ] **Step 4: 保持现有路由装配方式**

确保所有现有 `@app.get(...)` 和 `@app.post(...)` 装饰器继续绑定到模块级 `app`，只重构初始化，不移动路由主体。

核对关键代码保持不变：

```python
@app.get("/api/ops")
async def api_ops():
    ...


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    ...
```

- [ ] **Step 5: 跑测试确认 `create_app()` 已可用**

Run:

```powershell
& 'd:\Projects\LuaN1aoAgent\venv\Scripts\python.exe' -m pytest d:\Projects\LuaN1aoAgent\tests\web\test_server_modernization.py::test_create_app_exposes_root_route -v
```

Expected:

```text
PASSED
```

- [ ] **Step 6: 提交初始化重构**

```bash
git add web/server.py tests/web/test_server_modernization.py
git commit -m "refactor: modernize web app initialization"
```

## Task 3: 修复模板响应与入口副作用

**Files:**
- Modify: `d:\Projects\LuaN1aoAgent\web\server.py`
- Modify: `d:\Projects\LuaN1aoAgent\web\__init__.py`
- Test: `d:\Projects\LuaN1aoAgent\tests\web\test_server_modernization.py`

- [ ] **Step 1: 将首页模板响应改为新版显式签名**

把 `index()` 中的返回值改成：

```python
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={},
    )
```

- [ ] **Step 2: 清理 `web.__init__` 导入副作用**

将 `web/__init__.py` 改为只保留包元信息：

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LuaN1ao Web可视化模块。"""

__all__: list[str] = []
__version__ = "1.0.0"
```

- [ ] **Step 3: 更新首页与导入测试预期**

在 `tests/web/test_server_modernization.py` 中保留以下断言：

```python
def test_index_returns_200():
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"].lower()
```

```python
def test_import_web_package_does_not_import_web_server():
    sys.modules.pop("web", None)
    sys.modules.pop("web.server", None)
    importlib.import_module("web")
    assert "web.server" not in sys.modules
```

- [ ] **Step 4: 跑测试确认首页与导入行为修复**

Run:

```powershell
& 'd:\Projects\LuaN1aoAgent\venv\Scripts\python.exe' -m pytest d:\Projects\LuaN1aoAgent\tests\web\test_server_modernization.py::test_index_returns_200 d:\Projects\LuaN1aoAgent\tests\web\test_server_modernization.py::test_import_web_package_does_not_import_web_server -v
```

Expected:

```text
PASSED test_index_returns_200
PASSED test_import_web_package_does_not_import_web_server
```

- [ ] **Step 5: 手工验证模块启动 warning**

Run:

```powershell
& 'd:\Projects\LuaN1aoAgent\venv\Scripts\python.exe' -m web.server
```

Expected:

```text
Application startup complete.
Uvicorn running on http://127.0.0.1:8000
```

并确认输出中不再出现：

```text
RuntimeWarning: 'web.server' found in sys.modules
DeprecationWarning: on_event is deprecated
```

- [ ] **Step 6: 提交主页与入口修复**

```bash
git add web/server.py web/__init__.py tests/web/test_server_modernization.py
git commit -m "fix: align web template and module entry with new fastapi"
```

## Task 4: 为关键请求体补最小 Pydantic 模型

**Files:**
- Modify: `d:\Projects\LuaN1aoAgent\web\server.py`
- Test: `d:\Projects\LuaN1aoAgent\tests\web\test_server_modernization.py`

- [ ] **Step 1: 在 `web/server.py` 中加入最小请求模型**

新增：

```python
from pydantic import BaseModel, Field


class OpsReorderPayload(BaseModel):
    order: list[str] = Field(default_factory=list)


class InterventionDecisionPayload(BaseModel):
    approved: bool
    notes: str | None = None


class InjectTaskPayload(BaseModel):
    task: str


class McpAddPayload(BaseModel):
    server_name: str
    command: str
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)


class RenameOpPayload(BaseModel):
    name: str
```

- [ ] **Step 2: 将路由签名从裸字典迁移到模型**

将以下函数签名替换为模型版本：

```python
async def api_ops_reorder(payload: OpsReorderPayload):
    order = payload.order
```

```python
async def api_submit_intervention_decision(op_id: str, payload: InterventionDecisionPayload):
    ...
```

```python
async def api_ops_inject_task(op_id: str, payload: InjectTaskPayload):
    ...
```

```python
async def api_mcp_add(payload: McpAddPayload):
    ...
```

```python
async def api_ops_rename(op_id: str, payload: RenameOpPayload):
    ...
```

- [ ] **Step 3: 为一个关键接口补成功用例**

在测试文件中加入：

```python
def test_reorder_ops_accepts_structured_payload():
    client = TestClient(app)
    response = client.post("/api/ops/reorder", json={"order": []})
    assert response.status_code == 200
```

- [ ] **Step 4: 为一个关键接口补校验失败用例**

在测试文件中加入：

```python
def test_reorder_ops_rejects_invalid_payload():
    client = TestClient(app)
    response = client.post("/api/ops/reorder", json={"order": "bad"})
    assert response.status_code == 422
```

- [ ] **Step 5: 运行局部测试**

Run:

```powershell
& 'd:\Projects\LuaN1aoAgent\venv\Scripts\python.exe' -m pytest d:\Projects\LuaN1aoAgent\tests\web\test_server_modernization.py -k reorder -v
```

Expected:

```text
PASSED test_reorder_ops_accepts_structured_payload
PASSED test_reorder_ops_rejects_invalid_payload
```

- [ ] **Step 6: 提交输入边界收敛**

```bash
git add web/server.py tests/web/test_server_modernization.py
git commit -m "refactor: add typed request models for web endpoints"
```

## Task 5: 锁定依赖并完成总回归

**Files:**
- Modify: `d:\Projects\LuaN1aoAgent\requirements.txt`
- Modify: `d:\Projects\LuaN1aoAgent\tests\web\test_server_modernization.py`

- [ ] **Step 1: 收紧 Web 主栈依赖版本**

将 `requirements.txt` 中相关依赖调整为显式约束，例如：

```text
jinja2>=3.1,<4
uvicorn>=0.34,<1
fastapi>=0.136,<1
sse-starlette>=2.3,<4
pydantic>=2.11,<3
```

保留其余依赖不动，避免把迁移范围扩散到 Web 之外。

- [ ] **Step 2: 运行新增 Web 测试**

Run:

```powershell
& 'd:\Projects\LuaN1aoAgent\venv\Scripts\python.exe' -m pytest d:\Projects\LuaN1aoAgent\tests\web\test_server_modernization.py -v
```

Expected:

```text
all passed
```

- [ ] **Step 3: 运行现有核心测试**

Run:

```powershell
& 'd:\Projects\LuaN1aoAgent\venv\Scripts\python.exe' -m pytest d:\Projects\LuaN1aoAgent\tests\core\test_graph_manager_attack_chain_summary.py -v
```

Expected:

```text
all passed
```

- [ ] **Step 4: 做一次启动回归**

Run:

```powershell
& 'd:\Projects\LuaN1aoAgent\venv\Scripts\python.exe' -m web.server
```

Expected:

```text
Uvicorn running on http://127.0.0.1:8000
```

然后请求：

```powershell
Invoke-WebRequest http://127.0.0.1:8000/
```

Expected:

```text
StatusCode        : 200
```

- [ ] **Step 5: 检查诊断并修复新增问题**

Run diagnostics for:

```text
d:\Projects\LuaN1aoAgent\web\server.py
d:\Projects\LuaN1aoAgent\web\__init__.py
d:\Projects\LuaN1aoAgent\tests\web\test_server_modernization.py
```

Expected:

```text
No newly introduced errors
```

- [ ] **Step 6: 提交最终 Web 迁移结果**

```bash
git add requirements.txt web/server.py web/__init__.py tests/web/test_server_modernization.py
git commit -m "feat: migrate web layer to modern fastapi patterns"
```

## 自检结果

- 规格覆盖：已覆盖设计文档中的初始化、生命周期、模板调用、入口副作用、请求模型、测试与依赖约束要求
- 占位检查：无 `TODO`、`TBD`、`类似 Task N` 之类占位描述
- 类型一致性：计划中统一使用 `create_app()`、`lifespan`、`TemplateResponse(request=..., name=..., context=...)` 与请求模型命名

