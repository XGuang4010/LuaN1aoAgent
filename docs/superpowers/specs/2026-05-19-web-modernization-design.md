# Web Layer Modernization Design

## 背景

当前项目的 Web 层基于 FastAPI/Starlette，但实现仍保留部分旧接口写法。在当前环境下，`fastapi 0.136.1` 与 `starlette 1.0.0` 已触发以下问题：

- 主页访问 `GET /` 返回 500
- `@app.on_event("startup")` 产生弃用告警
- `python -m web.server` 触发模块预导入 warning
- Web 资源路径依赖当前工作目录，运行位置变化时存在失败风险

本次工作仅针对 `web/` 层进行现代化迁移与小范围结构整理，不扩散到 `core/`、`rag/` 与 P-E-R 主流程逻辑。

## 目标

- 修复 `GET /` 的模板渲染错误
- 将 Web 层迁移到当前新版 FastAPI/Starlette 推荐写法
- 消除已确认的 Web 启动与运行 warning
- 收敛 Web 层应用初始化、静态资源路径与入口组织
- 为 Web 层补充最小回归测试
- 为 Web 主栈补充明确的版本约束，避免环境漂移

## 非目标

- 不修改 `core/`、`rag/`、`tools/` 的业务语义
- 不重写前端页面或 API 协议
- 不进行与本次兼容性无关的大规模重构
- 不追求“所有依赖全部最新”，而是锁定一组可验证的新版兼容组合

## 范围

本次仅修改以下区域：

- `web/server.py`
- `web/__init__.py`
- Web 层新增或更新测试文件
- `requirements.txt` 及必要的项目依赖约束文件

必要时可增加 Web 层内部辅助模块，但必须保持边界清晰，不向其他子系统扩散。

## 已知问题与根因

### 1. 模板响应签名已不兼容

当前主页路由使用旧式模板调用：

```python
return templates.TemplateResponse("index.html", {"request": request})
```

在当前 Starlette 版本中，更稳定的调用签名是显式传入 `request`、模板名和上下文，因此旧写法在运行时触发模板缓存路径上的异常。

### 2. 生命周期事件使用弃用路径

当前 Web 应用使用 `@app.on_event("startup")` 初始化数据库。该接口在新版 FastAPI 生态中已进入弃用路径，继续沿用只会积累警告与未来升级风险。

### 3. 包导入副作用导致 `python -m web.server` warning

`web/__init__.py` 在包导入时提前导入 `web.server`，与 `python -m web.server` 的模块执行路径冲突，导致模块已进入 `sys.modules` 后再次执行。

### 4. 静态与模板目录依赖工作目录

当前实现直接使用 `"web/static"` 与 `"web/templates"` 相对路径。只要运行工作目录不是项目根，静态文件挂载与模板加载就可能失败。

### 5. Web 请求体普遍使用裸 `Dict[str, Any]`

这不是当前 500 的根因，但它使 Web 边界缺乏结构化校验，也不利于后续继续向新版 FastAPI/Pydantic 风格收敛。

## 迁移方案

### 方案选择

采用“Web 兼容迁移 + 小范围结构整理”：

- 先完成新版接口兼容修复
- 再做少量局部整理，降低后续继续升级成本
- 不修改现有 API 语义，不做无关架构重写

### 设计原则

- 兼容优先：先保证现有 Web 功能可运行
- 边界清晰：仅在 `web/` 范围内整理
- 少即是多：只抽取确实影响可维护性的初始化与输入边界
- AI Native：不为了工程感而过度拆模块，仅抽最小必要单元

## 详细设计

### 1. 应用初始化改为工厂化

在 `web/server.py` 中引入 `create_app()` 或等价的初始化封装，集中处理：

- `FastAPI(...)` 实例创建
- `lifespan` 生命周期注册
- 中间件注册
- 静态目录挂载
- 模板系统初始化
- 路由绑定

保留模块级 `app` 供 `uvicorn` 与现有使用方式兼容，但 `app` 由工厂函数生成，而不是散落在文件顶部逐步拼装。

这样做的目的是把“应用创建”与“业务路由”分离，避免后续每次升级都在文件顶部追着改初始化细节。

### 2. 生命周期统一迁移到 `lifespan`

将数据库初始化逻辑迁移为 `lifespan`：

- 启动时执行 `init_db()`
- 关闭时保留空清理钩子或记录日志

此改动只替换生命周期挂载方式，不改变数据库初始化行为。

### 3. 模板与静态资源路径改为基于文件位置解析

使用 `Path(__file__).resolve().parent` 计算：

- `web/static`
- `web/templates`

所有资源路径都基于模块文件所在目录计算，不再依赖 `os.getcwd()`。

这可以保证以下启动方式都一致：

- `python -m web.server`
- 在项目根使用 `uvicorn web.server:app`
- 从其他工作目录导入应用对象

### 4. 模板响应迁移到新版显式签名

主页路由统一使用显式参数：

```python
templates.TemplateResponse(
    request=request,
    name="index.html",
    context={},
)
```

目标是消除参数位置耦合，避免再次被 Starlette 签名演进击穿。

### 5. 消除 `web/__init__.py` 导入副作用

调整 `web/__init__.py`，避免在包导入阶段直接导入 `web.server`。

候选做法：

- 仅保留包元信息，不导出 `app`
- 或使用惰性导出机制，只有明确访问时才触发导入

默认优先选择更简单、更少副作用的方案：`__init__.py` 不再主动导入 `web.server`。

### 6. 请求体验证做最小结构化收敛

对 Web 层中最关键、最容易误用的请求体引入最小 Pydantic 模型，例如：

- 任务重排
- MCP 添加
- 任务注入
- 任务重命名
- 干预决策

原则：

- 只为 Web 边界提供结构化输入
- 保持字段名和现有前端调用兼容
- 不在本次引入复杂验证逻辑

### 7. 保持 SSE 与任务启动行为不变

以下高风险行为本次只做兼容回归，不做语义重写：

- `EventSourceResponse` SSE 推送
- `subprocess.Popen` 启动 agent 任务
- 现有 `/api/*` 路由返回结构

这样可以把风险集中在“初始化与兼容层”，避免扩散到执行链路。

## 版本策略

### 目标

锁定一组经过本地验证的 Web 主栈版本组合，避免依赖漂移。

### 约束对象

- `fastapi`
- `starlette`
- `uvicorn`
- `pydantic`
- `sse-starlette`
- `jinja2`

### 版本原则

- 使用当前生态中稳定的新版本组合
- 显式约束主版本兼容区间或确定版本
- 优先保证本仓库运行稳定，而非无边界追新

最终具体版本号以本地验证通过的组合为准。

## 测试策略

### 自动化测试

新增或更新 Web 相关测试，至少覆盖：

- 应用可成功构造
- `GET /` 返回 200
- 模板可正常渲染
- `python -m web.server` 不再出现模块预导入 warning

如果当前仓库已有适合的测试风格，优先沿用；否则新增最小 Web 测试文件，不引入过度测试。

### 手工验证

至少执行以下检查：

- 启动 `python -m web.server`
- 浏览器访问首页
- 检查静态资源是否正常加载
- 检查启动日志是否仍存在已知 warning

### 回归重点

- `GET /api/events` SSE 仍可建立连接
- `POST /api/ops` 任务创建接口不受影响
- 静态文件路径在不同工作目录下仍正常

## 风险与缓解

### 风险 1：`web/server.py` 改动集中，容易引入局部回归

缓解：

- 将改动收敛在应用初始化与输入边界
- 保持既有路由函数主体尽量不动
- 用测试覆盖首页和启动路径

### 风险 2：`sse-starlette` 与新版 Starlette 组合可能有隐藏兼容问题

缓解：

- 不主动改 SSE 逻辑
- 保留 SSE 作为专门回归点
- 若发现版本冲突，以验证通过的组合回调依赖约束

### 风险 3：入口调整可能影响外部导入方式

缓解：

- 保留 `web.server:app` 兼容入口
- 仅移除 `web.__init__` 的副作用导入，不破坏模块路径

## 实施顺序

1. 为 Web 层补失败测试或最小复现测试
2. 重构 `web/server.py` 初始化方式与路径解析
3. 迁移 `TemplateResponse` 与 `lifespan`
4. 调整 `web/__init__.py`
5. 为关键请求体补最小 Pydantic 模型
6. 锁定 Web 主栈依赖版本
7. 运行测试与手工回归

## 验收标准

- `python -m web.server` 可正常启动
- 首页 `GET /` 返回 200，模板正常渲染
- 不再出现 `web.server found in sys.modules` warning
- 不再出现 `on_event is deprecated` warning
- Web 层测试通过
- 现有核心测试不因本次修改失败

