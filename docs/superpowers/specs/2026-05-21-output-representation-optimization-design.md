# 输出表征优化与证据可视化设计

**日期**: 2026-05-21
**状态**: 设计定稿
**涉及模块**: `core/executor.py`, `core/data_contracts.py`, `core/graph_manager.py`, `core/parsers/`, `web/server.py`, `web/static/app.js`, `web/templates/index.html`

---

## 1. 问题概述

当前 Executor 将工具执行结果以纯文本形式传递给 LLM：

```
动作 step_1 (工具=http_request) 的结果: {json...}
动作 step_2 (工具=shell_exec) 的结果: {long output...} ... (Truncated from 50000)
```

存在以下问题：
- **扁平字符串** — 所有结构化数据被拍平，下游每次都要重新解析
- **截断破坏结构** — 简单前缀截断，可能在 JSON 中间截断
- **无结果提取** — nmap/dirsearch 等工具输出格式固定，但未做结构化提取
- **错误分类不足** — 只覆盖 SYNTAX/MISSING_TOOL 两种"可纠正"错误
- **Web UI 缺乏详情** — DAG 节点只能看状态，不能查看完整输出和发现
- **无法追问任务进度** — 用户无法在 Web UI 中自然语言提问

---

## 2. 整体架构变更

```
当前:
  Executor → str (raw output) → data['observation'] → Reflector → Planner

优化后:
  Executor → StructuredObservation → data['observation'] (observation + findings + evidence)
              ↓                    ↓                      ↓
          LLM 消息(摘要)      Web UI 详情面板        CausalGraph 证据节点
                                        ↓
                                 任务级对话对话框 (只读查询)
```

---

## 3. P1: 结构化结果契约

### 3.1 新增数据类

在 `core/data_contracts.py` 中新增：

```python
@dataclass
class ToolFinding:
    category: str          # "open_port" / "service" / "subdomain" / "tech_stack" / "vuln" / "http_header" / "url" / "os"
    key: str               # 唯一标识，如 "80/tcp"
    value: str | dict      # 核心值
    confidence: float      # 0.0-1.0
    evidence_ref: str | None  # 原始输出行引用

@dataclass
class ToolError:
    error_type: str        # MISSING_TOOL / TIMEOUT / AUTH / SYNTAX / NETWORK / RUNTIME / UNKNOWN
    message: str
    fix_suggestion: str
    is_correctable: bool

@dataclass
class StructuredObservation:
    step_id: str
    tool: str
    status: Literal["success", "partial", "failed"]
    summary: str           # LLM 友好摘要（2-3 行）
    raw_output: str        # 完整原始输出（按需截断）
    findings: list[ToolFinding]
    errors: list[ToolError]
    evidence_ids: list[str]
    truncated: bool
    truncation_info: str | None
```

### 3.2 Executor 改动

`core/executor.py` 第 886 行：

```python
# 当前
observations.append(f"动作 {step_id} (工具={tool_name}) 的结果: {result_str}")

# 改为
obs = StructuredObservation(
    step_id=step_id,
    tool=tool_name,
    status=determine_status(result_str, tool_name),
    summary=generate_summary(tool_name, result_str),
    raw_output=result_str,
    findings=parse_tool_output(tool_name, result_str),
    errors=parse_errors(result_str),
    truncated=was_truncated,
)
observations.append(obs)
```

### 3.3 LLM 消息格式变更

```python
# 当前
messages.append({"role": "user", "content": f"你并行执行了 N 个动作，观察到：\n{full_observation}"})

# 改为
formatted = f"你并行执行了 {len(last_step_ids)} 个动作：\n"
for obs in observations:
    status_icon = {"success": "✅", "partial": "⚠️", "failed": "❌"}[obs.status]
    formatted += f"  {status_icon} [{obs.tool}] {obs.step_id}: {obs.summary}\n"
    if obs.findings:
        formatted += f"    → 发现: {len(obs.findings)} 项 ({', '.join(set(f.category for f in obs.findings))})\n"
    if obs.errors:
        for err in obs.errors:
            formatted += f"    → 错误: [{err.error_type}] {err.message}\n"
messages.append({"role": "user", "content": formatted})
```

### 3.4 智能截断

- **双缓冲区**：raw_output 保存前 200K chars（到 DB），LLM 消息只传 summary + findings
- **按字段截断**：优先保留 findings，错误信息
- **截断标记**：truncation_info 描述被截断的内容类型

### 3.5 错误分类扩展

| 类型 | 可纠正 | 说明 |
|------|--------|------|
| SYNTAX | ✅ | 命令语法错误，可修正 |
| MISSING_TOOL | ⚠️ | 工具未安装，换工具或提示安装 |
| TIMEOUT | ✅ | 超时可重试（延长超时） |
| NETWORK | ✅ | 网络错误，可重试 |
| AUTH | ⚠️ | 认证失败，需凭据更新 |
| RUNTIME | ❌ | 运行异常，不可重试 |
| UNKNOWN | ❌ | 无法识别错误 |

### 3.6 存储方案

实际存储基于 `models.py` 的 `GraphNodeModel.data` JSON 列，所有字段存入其中：

| 字段 | 存储位置 |
|------|---------|
| StructuredObservation | `data['observation']` (JSON) |
| ToolFinding.findings | `data['findings']` (JSON list) |
| raw_output | `data['raw_output']` (JSON str) |
| evidence_ids | `data['evidence_ids']` (list[str]) + CausalGraph Edge |

> **说明**：`GraphNodeModel` 的 `data` 列（`Mapped[Dict[str, Any]]`）是所有扩展信息的统一存储位置。旧数据的 `data['observation']` 为纯文本字符串，读取时按类型回退；
> 新旧兼容逻辑：
> ```python
> data = node.data or {}
> raw = data.get("observation", "")
> if isinstance(raw, str):
>     # 旧格式：直接回退为 raw_output
>     obs = StructuredObservation(raw_output=raw, ...)
> else:
>     # 新格式：data['observation'] 为 StructuredObservation 字典
>     obs = StructuredObservation(**raw)
> findings = data.get("findings", [])
> ```

---

## 4. P2: 工具输出解析器

### 4.1 新模块结构

```
core/parsers/
├── __init__.py          # PARSER_REGISTRY + parse_tool_output()
├── nmap_parser.py       # nmap -sV / -A 输出解析
├── dirsearch_parser.py  # URL 发现列表解析
├── httpx_parser.py      # HTTP 探测结果解析
├── http_parser.py       # http_request 响应解析
├── subfinder_parser.py  # 子域名发现解析
├── nuclei_parser.py     # 漏洞检测结果解析
└── sqlmap_parser.py     # SQL 注入检测结果解析
```

### 4.2 解析器接口

所有解析器遵循统一签名：`(raw_output: str) -> list[ToolFinding]`

### 4.3 Finding 分类体系

| category | 来源工具 | 示例 |
|----------|---------|------|
| open_port | nmap | "80/tcp" → "Apache httpd 2.4.41" |
| service | nmap/httpx | "http" → "Apache 2.4.41" |
| subdomain | subfinder/dirsearch | "api.target.com" → "A 1.2.3.4" |
| tech_stack | httpx/http_request | "framework" → "React 18" |
| url | dirsearch | "/admin" → "200 OK (3456 bytes)" |
| vuln | nuclei | "CVE-2024-XXXX" → "SQL Injection" |
| http_header | http_request | "server" → "nginx/1.18.0" |
| os | nmap | "os" → "Linux 5.4 (Ubuntu 20.04)" |

### 4.4 Fallback 策略

未注册的 tool_name 走 fallback：
```python
def fallback_parser(output: str) -> list[ToolFinding]:
    return [ToolFinding(category="raw_output", key="full", value=output[:2000], confidence=1.0)]
```

### 4.5 证据节点自动写入

Executor 在构建 StructuredObservation 后，遍历 findings，对每条调用新增的 `add_evidence()` 方法：

```python
# GraphManager 新增方法签名
def add_evidence(
    self,
    category: str,          # finding category
    content: str | dict,    # finding value
    source_step: str,       # 来源 substep_id
    confidence: float,      # 0.0-1.0
    hypothesis_id: str | None = None,  # 可选关联假设
) -> str:                   # 返回 evidence_node_id
    """在因果图谱中创建 Evidence 节点并关联到来源步骤。"""
```

Executor 调用：
```python
evidence_node_id = graph_manager.add_evidence(
    category=f.category,
    content=f.value,
    source_step=step_id,
    confidence=f.confidence,
)
obs.evidence_ids.append(evidence_node_id)
```

---

## 5. P3: DAG 节点交互详情面板

### 5.1 交互流程

```
点击 DAG 节点
  → fetch /api/node/{node_id}/detail
    → 返回 {observation, findings, evidence_nodes, next_steps}
      → 右侧滑出式面板 (CSS transform: translateX())
        → 5 个标签页浏览
```

### 5.2 详情面板标签页

| 标签页 | 内容 |
|--------|------|
| 概览 | 节点 ID、类型、状态、工具、参数、执行时间、summary、截断提示 |
| 发现 | Findings 按 category 分组，每项显示 key/value/置信度进度条，可折叠 |
| 证据 | 关联证据节点列表，每条显示类别标签/内容摘要/置信度，点击跳转 P4 |
| 原始输出 | raw_output 全文语法高亮，行号，搜索，截断提示，"复制全文"按钮 |
| 建议 | 基于 findings category 规则引擎生成下一步建议 |

### 5.3 任务级对话对话框

- **入口**：顶部工具栏 / 详情面板底部 / 节点右键菜单
- **只读模式**：对话 LLM 无工具权限，不干预 P-E-R 循环
- **上下文注入**：自动注入当前任务图谱状态、所有节点 findings、因果关系链
- **API**：`POST /api/task/{op_id}/chat` → SSE 流式响应
- **LLM system prompt**：只读上下文，描述当前任务结构，不包含 MCP 工具列表
- **预设快捷问题**："当前进度如何？"、"发现了哪些关键信息？"、"下一步建议？"等

### 5.4 新增 API 端点

```
GET  /api/node/{node_id}/detail          → 节点详情 (observation + findings + evidence + next_steps)
GET  /api/subtask/{subtask_id}/log       → 子任务执行日志（结构化列表）
POST /api/task/{op_id}/chat              → 任务对话 (SSE stream)
```

---

## 6. P4: 证据可视化视图

### 6.1 三栏式证据浏览器

| 栏 | 内容 | 功能 |
|----|------|------|
| 左 | 过滤面板 | 按分类筛选、置信度滑块、关键词搜索 |
| 中 | 证据列表 | 每条显示分类标签/值/置信度，选中高亮 |
| 右 | 证据详情 | 完整信息 + 因果链可视化 |

### 6.2 因果链可视化

每条证据详情中展示 mini 因果图：
```
[🔍 Evidence] ──confidence──▶ [💭 Hypothesis] ──confidence──▶ [⚠️ Vulnerability]
```

纯 HTML/CSS 渲染，无需第三方图表库。

### 6.3 新增 API 端点

```
GET /api/task/{op_id}/evidence            → 全部证据节点（支持 category/confidence 过滤）
GET /api/evidence/{evidence_id}           → 单个证据详情
GET /api/evidence/{evidence_id}/chain     → 完整因果链（节点列表 + 边列表）
```

---

## 7. 文件变更清单

### 新增文件

| 文件 | 说明 |
|------|------|
| `core/parsers/__init__.py` | 解析器注册表 + parse_tool_output() |
| `core/parsers/nmap_parser.py` | nmap 输出解析 |
| `core/parsers/dirsearch_parser.py` | dirsearch 输出解析 |
| `core/parsers/httpx_parser.py` | httpx 输出解析 |
| `core/parsers/http_parser.py` | http_request 响应解析 |
| `core/parsers/subfinder_parser.py` | subfinder 输出解析 |
| `core/parsers/nuclei_parser.py` | nuclei 输出解析 |
| `core/parsers/sqlmap_parser.py` | sqlmap 输出解析 |

### 修改文件

| 文件 | 改动 |
|------|------|
| `core/data_contracts.py` | 新增 ToolFinding、ToolError、StructuredObservation |
| `core/executor.py` | 重构 observation 构建逻辑、LLM 消息格式化、错误分类扩展；**见下方删除清单** |
| `core/graph_manager.py` | 新增 `add_evidence()` 方法 |
| `web/server.py` | 新增 API 路由（node detail、evidence、chat） |
| `web/static/app.js` | DAG 节点点击事件、详情面板 UI、对话 widget、证据视图 |
| `web/templates/index.html` | 面板和对话对话框的 CSS/HTML 模板 |

### 7.3 旧代码删除/替换清单 (P1 实施时)

实施 P1 `StructuredObservation` 时，`core/executor.py` 中的以下代码需同步删除或替换：

| 行号范围 (当前) | 操作 | 原因 |
|-----------------|------|------|
| `observations.append(f"动作 {step_id}...")` (当前 ~886) | **替换**为 `observations.append(StructuredObservation(...))` | 字符串 → 结构化对象 |
| `result_str[:MAX_OBSERVATION_LENGTH] + f"... (Truncated from...)"` (当前 ~872-884) | **保留**截断逻辑，但**替换**截断方式 | 改为双缓冲区截断，raw_output 保留 200K |
| `full_observation = "\n".join(observations)` (当前 ~932) | **删除** | 改为新格式化逻辑 |
| `messages.append({"role":"user", "content": f"...{full_observation}"})` (当前 ~933) | **替换**为第 3.3 节的新格式化逻辑 | 结构化 → LLM 友好摘要 |
| 旧错误判断 (if "SyntaxError" in result 等) | **替换**为 `parse_errors()` + `ToolError` | 扩展为 7 类错误分类 |

> **原则**：只删已经**被新功能完全替代**的旧逻辑。数据结构升级是正常的架构演进，不是破坏。

---

## 8. 实施优先级

| 阶段 | 核心交付 | 预计工作量 |
|------|---------|-----------|
| P1 | 数据类 + Executor 结果结构化 + LLM 消息格式化 | 3-4h |
| P2 | core/parsers/ 模块 + 证据自动写入 | 4-6h |
| P3 | Web UI 详情面板 + 对话对话框 | 3-5h |
| P4 | 证据视图页面 + 因果链可视化 | 2-3h |

---

## 9. 注意事项

- **向后兼容**：StructuredObservation 序列化为 JSON 存入 `data['observation']` 字段，旧数据读取为纯文本时正常回退（见第 3.6 节兼容逻辑）
- **对话隔离**：`POST /api/task/{op_id}/chat` 使用独立的 LLM 会话，system prompt 不含 MCP 工具描述
- **截断保护**：raw_output 在 DB 层前先截断（200K chars），防止数据库过大
- **Web UI 更新**：所有 UI 变更追加到现有的 `web/static/app.js`，不引入前端框架依赖
- **旧代码删除**：实施 P1 时同步删除/替换第 7.3 节清单中的旧代码。数据结构升级是架构演进的正常过程，新代码完全覆盖旧功能后即可清理
