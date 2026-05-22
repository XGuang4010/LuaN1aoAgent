# LuaN1ao Agent 系统稳定性与用户体验优化设计

> **日期**: 2026-05-22
> **状态**: 已审阅修订，待确认
> **基于分析**: api.dxmpay.com 任务运行日志与 P1-P4 输出表征优化复盘

---

## 1. 背景与问题概述

### 1.1 当前已完成的优化（P1-P4）

| 阶段 | 内容 | 状态 |
|------|------|------|
| P1 | 结构化观测数据（StructuredObservation / ToolFinding / ToolError） | ✅ 已提交 `cca8506` |
| P2 | 工具输出解析器（7 个 parser + 注册表） | ✅ 已提交 `2d7b2f1` |
| P2 | 解析器集成到 Executor + GraphManager.add_evidence() | ✅ 已提交 `7f262ff` / `82e9ead` |
| P3 | DAG 节点 5 标签详情面板 + 任务级对话对话框 | ✅ 已提交 `76c92b7` |
| P4 | 证据浏览器 + 因果链可视化 | ✅ 已提交 `76c92b7` |

### 1.2 日志暴露的核心问题

基于 `api.dxmpay.com` 实际任务运行（`task_1779375297_ab6783f9`）的日志分析：

| # | 问题 | 影响 | 日志证据 |
|---|------|------|----------|
| 1 | **Agent 异常退出无恢复** | 任务在第 2 步准备阶段终止，`end_time=null`，深度探测未执行 | `metrics.json` 中 `end_time: null`，`total_time_seconds: 36.25s` |
| 2 | **外部工具缺失仅 Warning** | `searchsploit` 未安装，但任务继续，工具实际失效 | `console_output.log: "WARNING - searchsploit not found"` |
| 3 | **Web Server 后台运行不稳定** | Windows Git Bash 下 `python -m web.server` 约 2 分钟后自动退出 | 端口 8000 失去监听，需手动重启 |
| 4 | **任务无法断点续传** | 进程重启后需从头开始，已消耗 Token 和时间浪费 | 无 checkpoint 机制 |

---

## 2. 优化总体架构

```
优化方向
├── 系统稳定性层（System Stability）
│   ├── Agent 异常熔断与自动恢复
│   ├── 启动前环境校验（工具/模型/配置）
│   ├── 进程启动方式标准化（Web Server / Agent）
│   └── 任务断点续传（Checkpoint & Resume）
│
├── 功能增强层（Feature Enhancement）
│   ├── 实时因果链动画（DAG 可视化升级）
│   ├── DAG 节点重启与增量执行
│   ├── 任务完成自动报告生成
│   ├── 实时日志过滤与搜索（Web UI）
│   ├── 启动向导（首次使用配置引导）
│   ├── 任务模板库（常见场景预设）
│   └── 假设验证追踪面板
│
└── 体验细节层（UX Polish）
    ├── 多任务管理台（Web UI 左侧栏）
    ├── 异常告警通知（Webhook/钉钉）
    └── 移动端适配（响应式布局）
```

---

## 3. 系统稳定性层设计

### 3.1 Agent 异常熔断与自动恢复

**目标**：Agent 进程在任意步骤崩溃后，能够保存状态并支持从中断点恢复。

**现状问题**：
- `agent.py` 主循环无全局 `try/except`，异常直接退出
- `finally` 块只保存日志，不保存执行上下文
- 进程重启后无法识别之前 `running` 状态的任务

**设计方案**：

```python
# agent.py 主入口增强
async def run_agent_with_recovery(args):
    """带异常恢复的主运行函数。"""
    try:
        await run_agent(args)
    except Exception as e:
        logger.critical(f"Agent 异常退出: {e}", exc_info=True)
        # 保存异常状态到 DB
        graph_manager.update_node(args.op_id, {
            "status": "crashed",
            "crash_reason": str(e),
            "crash_timestamp": time.time(),
        })
        raise

# 启动时检查是否有 crashed / running 但未完成的任务
async def resume_pending_tasks():
    """查询数据库中状态为 running 但无活跃进程的任务，尝试恢复。"""
    pending = await db.query(
        select(SessionModel).where(
            SessionModel.status.in_(["running", "crashed"])
        )
    )
    for task in pending:
        if not is_agent_process_alive(task.op_id):
            logger.info(f"检测到中断任务 {task.op_id}，准备恢复...")
            await resume_task(task.op_id)
```

**验收标准**：
- [ ] 手动 `kill -9` Agent 进程后，重启可自动恢复到最后一个执行周期
- [ ] 异常退出时 DB 中任务状态变为 `crashed`，并记录异常信息
- [ ] 恢复后 Executor 的 `messages` 列表保持连续性

> **注**：用户已明确将通过更换 LLM 渠道解决此问题，此优化项从本次实施计划中移除，不纳入任何 Phase。

### 3.2 启动前环境校验

**目标**：Agent 启动前自动检查所有依赖，缺失时给出明确修复指引，而不是运行时才发现。

**设计方案**：

```python
# agent.py 启动流程新增校验步骤
async def preflight_check() -> list[CheckResult]:
    """启动前环境校验。"""
    checks = []
    
    # 1. LLM API 连通性
    checks.append(await check_llm_connectivity())
    
    # 2. 工具可执行文件存在性（从 mcp.json 动态读取注册工具，避免硬编码）
    tools = load_registered_tools_from_mcp_config()
    for tool in tools:
        checks.append(check_tool_available(tool))
    
    # 3. RAG 知识服务健康
    checks.append(await check_knowledge_service())
    
    # 4. 数据库可写
    checks.append(await check_database_writable())
    
    # 5. Web Server 可达（如果 --web）
    checks.append(await check_web_server_reachable())
    
    return checks

def print_preflight_report(checks: list[CheckResult]):
    """打印校验报告，失败项标红并给出修复命令。"""
    for c in checks:
        status = "✅" if c.passed else "❌"
        print(f"{status} {c.name}: {c.message}")
        if not c.passed and c.fix_hint:
            print(f"   修复: {c.fix_hint}")
```

**Web UI 对应展示**：
- 在 `#sidebar` 顶部新增 **环境状态面板**，实时显示各组件健康度
- 工具缺失时显示红色警告 + 一键安装按钮（链接到安装脚本）

**验收标准**：
- [ ] 启动时输出 5 项校验结果，总耗时 < 3 秒
- [ ] `searchsploit` 缺失时提示：从 GitHub 下载 `exploitdb` 并配置 `SEARCHSPLOIT_PATH`，或 `apt install exploitdb`（Kali/Linux）
- [ ] 任意校验失败时，Agent 可选择 `--skip-preflight` 强制启动

### 3.4 进程启动方式标准化

**目标**：解决 Windows Git Bash 下后台进程自动退出的问题，提供跨平台稳定启动方案。

**现状问题**：
- Windows Git Bash 中 `python -m web.server` 作为后台 job 运行时，约 2 分钟后随 shell session 退出
- 这不是进程 crash，而是 shell job control 的行为，自建 Python watchdog 同样会被杀死

**设计方案**：

**方案 A（推荐）—— 直接使用 uvicorn（已验证有效）：**

```bash
# 正确的启动方式（不依赖 shell job control）
python -m uvicorn web.server:app --host 127.0.0.1 --port 8000 --reload

# Windows 后台（使用 pythonw.exe 避免控制台窗口）
pythonw -m uvicorn web.server:app --host 127.0.0.1 --port 8000
```

**方案 B — 系统级守护（生产环境）：**

提供配置模板，不自建 watchdog：

- **Windows**: 提供 `scripts/supervise-agent.ps1`（循环检测进程 + 日志轮转）
- **Linux/macOS**: 提供 `scripts/luan1ao-agent.service`（systemd 配置）
- **通用**: 推荐使用 `supervisor` / `pm2` 等成熟进程管理工具

**为什么不用 Python watchdog：**
1. `subprocess.Popen` + `wait()` 会**阻塞 asyncio 事件循环**
2. Git Bash 下 watchdog 进程本身是 shell 子进程，session 结束同样退出
3. 新增 `psutil` 依赖，收益有限

**验收标准**：
- [ ] 更新 README/文档，明确记录正确的启动命令
- [ ] 提供 systemd service 配置文件模板
- [ ] Agent 异常退出后，DB 状态变为 `crashed`（由 3.1 负责），不依赖进程守护自动重启

### 3.5 任务断点续传（Checkpoint & Resume）

**目标**：Agent 每完成一个执行周期就保存 checkpoint，重启后从中断点续传。

**设计方案**：

```python
# core/checkpoint.py
import json
import os

CHECKPOINT_DIR = "logs/checkpoints"

async def save_checkpoint(op_id: str, cycle_num: int, context: dict):
    """保存执行上下文到 checkpoint 文件（JSON 格式，安全且可版本控制）。"""
    path = os.path.join(CHECKPOINT_DIR, f"{op_id}_cycle_{cycle_num}.json")
    os.makedirs(CHECKPOINT_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(context, f, ensure_ascii=False, indent=2)
    # 保留最近 5 个 checkpoint，删除旧的
    cleanup_old_checkpoints(op_id, keep=5)

async def load_latest_checkpoint(op_id: str) -> dict | None:
    """加载最新的 checkpoint。"""
    checkpoints = sorted(glob(f"{CHECKPOINT_DIR}/{op_id}_cycle_*.json"))
    if not checkpoints:
        return None
    with open(checkpoints[-1], "r", encoding="utf-8") as f:
        return json.load(f)

# 在 agent.py 主循环中每周期调用
# 不保存完整 messages（可能很大且含非 JSON 序列化对象），
# 只保存可重建状态：cycle_num、graph_state、summary、observations 元数据
context = {
    "version": 1,  # checkpoint 格式版本号，用于未来兼容
    "cycle_num": cycle_num,
    "graph_state": graph_manager.export_state(),
    "last_summary": last_compressed_summary,  # 压缩后的对话摘要
    "observation_metadata": [obs.to_dict() for obs in observations],
    "timestamp": time.time(),
}
await save_checkpoint(op_id, cycle_num, context)
```

**验收标准**：
- [ ] 每完成一个 P-E-R 周期自动生成 checkpoint（< 100ms）
- [ ] 重启 Agent 时检测到 checkpoint，提示用户是否恢复
- [ ] 恢复后从 `last_summary` 重建 LLM 上下文，不依赖完整 messages 列表
- [ ] checkpoint 文件为纯 JSON，可人工查看和调试

---

## 4. 功能增强层设计

### 4.1 实时因果链动画（DAG 可视化升级）

**目标**：在 Web UI 的 DAG 视图中，用动态 SVG 动画展示 "证据 → 假设 → 漏洞" 的推导过程。

**现状**：P4 已实现静态因果链可视化（证据浏览器中的 mini 因果图），但 DAG 主视图没有实时流动效果。

**设计方案**：

```javascript
// app.js: 在 drawForceGraph 中增加因果边动画
function drawCausalEdges(svg, causalEdges) {
    const links = svg.selectAll(".causal-link")
        .data(causalEdges)
        .enter()
        .append("path")
        .attr("class", "causal-link")
        .attr("stroke", "#4a9eff")
        .attr("stroke-width", 2)
        .attr("stroke-dasharray", "5,5")
        .attr("fill", "none");
    
    // 流动动画（使用 CSS animation，避免 JS 与 CSS 冲突）
    links.attr("stroke-dashoffset", 10)
         .style("animation", "flow 1s linear infinite");
}
```

**CSS**：
```css
.causal-link {
    opacity: 0.7;
    animation: flow 1s linear infinite;
}
@keyframes flow {
    from { stroke-dashoffset: 10; }
    to { stroke-dashoffset: 0; }
}
```

**验收标准**：
- [ ] 因果边显示虚线流动动画
- [ ] 动画方向从 Evidence → Hypothesis → Vulnerability
- [ ] 置信度越高，线条越粗、流速越快

### 4.2 DAG 节点重启与增量执行

**目标**：DAG 中的任意子任务（subtask）或执行步骤（step）节点失败后，用户可单独重启该节点，无需重新创建整个 `op_id` 大任务。已成功的上游节点成果保留，仅重置该节点及其下游节点。

**现状问题**：
- 当前 `subtask_1` 失败后，用户只能新建一个 `op_id` 重新执行全部探测
- 已消耗 Token、时间和获取的上游情报全部浪费
- 无单节点级状态重置机制

**设计方案**：

#### A. 节点状态重置（后端）

```python
# core/graph_manager.py
class GraphManager:
    def restart_node(self, node_id: str, cascade: bool = True) -> list[str]:
        """重启指定节点，返回被重置的节点 ID 列表。
        
        Args:
            node_id: 要重启的节点 ID（subtask 或 step）
            cascade: 是否级联重置所有下游节点，默认 True
        
        Returns:
            被重置的节点 ID 列表
        """
        reset_ids = [node_id]
        
        # 1. 重置自身状态
        self.update_node(node_id, {
            "status": "pending",
            "observation": None,
            "findings": [],
            "errors": [],
            "evidence_ids": [],
            "observation_truncated": False,
            "raw_output": "",
            "completed_at": None,
        })
        
        # 2. 从因果图中删除该节点产生的证据
        evidence_ids = self.get_node_evidence_ids(node_id)
        for ev_id in evidence_ids:
            if self.causal_graph.has_node(ev_id):
                self.causal_graph.remove_node(ev_id)
        
        # 3. 级联重置下游节点
        if cascade:
            downstream = self._get_downstream_nodes(node_id)
            for down_id in downstream:
                self.update_node(down_id, {
                    "status": "pending",
                    "observation": None,
                    "findings": [],
                    "errors": [],
                    "evidence_ids": [],
                    "completed_at": None,
                })
                reset_ids.append(down_id)
        
        # 4. 同步到数据库
        for rid in reset_ids:
            self._sync_node(rid, 'execution')
        
        return reset_ids
    
    def _get_downstream_nodes(self, node_id: str) -> list[str]:
        """获取指定节点的所有下游节点（BFS，避免深图栈溢出）。"""
        downstream = []
        queue = [node_id]
        visited = {node_id}
        while queue:
            current = queue.pop(0)
            for _, target in self.execution_graph.out_edges(current):
                if target not in visited:
                    visited.add(target)
                    downstream.append(target)
                    queue.append(target)
        return downstream
```

#### B. 增量执行模式（Agent 调度）

当前 Agent 启动后执行所有 `pending` 节点，这天然支持增量执行。但需增加显式模式：

```python
# agent.py 主循环增强
async def run_agent(args):
    # ... 初始化 ...
    
    # 增量模式：只执行 pending 状态的节点
    pending_nodes = graph_manager.get_nodes_by_status("pending")
    if not pending_nodes:
        logger.info("无 pending 节点，任务已完成")
        return
    
    logger.info(f"发现 {len(pending_nodes)} 个 pending 节点，开始增量执行...")
    
    for node in pending_nodes:
        # 跳过上游有 failed 节点的子任务（除非用户显式重启了上游）
        if has_failed_upstream(node.id):
            logger.warning(f"节点 {node.id} 上游存在失败节点，跳过执行")
            continue
        
        await execute_node(node)
```

#### C. Web UI 交互

```javascript
// app.js: 节点右键菜单和详情面板
function showNodeContextMenu(nodeId, event) {
    const menu = document.createElement('div');
    menu.className = 'node-context-menu';
    menu.innerHTML = `
        <button onclick="restartNode('${nodeId}', false)">仅重启此节点</button>
        <button onclick="restartNode('${nodeId}', true)">重启此节点及下游</button>
        <button onclick="viewNodeDetail('${nodeId}')">查看详情</button>
    `;
    document.body.appendChild(menu);
}

async function restartNode(nodeId, cascade) {
    const confirmed = confirm(
        cascade 
            ? `确定重启节点 ${nodeId} 及其所有下游节点？上游成果将保留。`
            : `确定仅重启节点 ${nodeId}？`
    );
    if (!confirmed) return;
    
    const resp = await fetch(`/api/node/${nodeId}/restart`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({cascade}),
    });
    const data = await resp.json();
    
    if (data.success) {
        alert(`已重置 ${data.reset_count} 个节点，Agent 将自动重新执行`);
        // 触发 SSE 刷新
    } else {
        alert(`重启失败: ${data.error}`);
    }
}
```

#### D. API 端点

```python
# web/server.py
@app.post("/api/node/{node_id}/restart")
async def restart_node(node_id: str, request: dict):
    """重启指定 DAG 节点及其下游节点。"""
    cascade = request.get("cascade", True)
    graph_manager = get_graph_manager()
    
    if not graph_manager.has_node(node_id):
        return {"success": False, "error": "Node not found"}
    
    node_status = graph_manager.get_node_status(node_id)
    if node_status not in ["failed", "completed", "deprecated"]:
        return {
            "success": False, 
            "error": f"Cannot restart node with status '{node_status}'. Only failed/completed/deprecated nodes can be restarted."
        }
    
    reset_ids = graph_manager.restart_node(node_id, cascade=cascade)
    
    # 发送事件通知 Agent 有新的 pending 节点
    await broker.emit("node.restarted", {
        "node_id": node_id,
        "reset_ids": reset_ids,
        "cascade": cascade,
    })
    
    return {
        "success": True,
        "reset_count": len(reset_ids),
        "reset_ids": reset_ids,
    }
```

**与断点续传的区别**：

| 特性 | 断点续传 | 节点重启 |
|------|----------|----------|
| 触发方式 | 自动（进程崩溃后） | 手动（用户点击） |
| 重置范围 | 整个任务状态 | 单节点及其下游 |
| 使用场景 | 系统异常恢复 | 用户修正错误后重试 |
| 上游数据 | 全部保留 | 全部保留 |

**关键注意事项 —— Executor Messages 同步**：

节点状态被清空后，`Executor` 维护的 `self.messages` 列表中仍包含该节点的旧观察结果，会导致 LLM 基于过期上下文做决策。必须在重启时同步清理：

```python
# core/executor.py
class Executor:
    def purge_messages_for_node(self, node_id: str):
        """从 messages 列表中删除与指定节点相关的 user/assistant 消息对。"""
        # 根据 node_id 标记过滤，保留系统消息和其他节点的上下文
        self.messages = [
            msg for msg in self.messages
            if msg.get("node_id") != node_id
        ]
```

**验收标准**：
- [ ] 右键点击 DAG 节点显示「仅重启此节点」和「重启此节点及下游」选项
- [ ] 重启后节点状态变为 `pending`，观察结果清空
- [ ] 上游节点（已完成的兄弟/父节点）状态和数据不受影响
- [ ] Agent 自动检测 pending 节点并执行，无需手动重启 Agent 进程
- [ ] 级联重置正确计算所有下游节点（通过拓扑排序验证）
- [ ] 重启后 Executor messages 中不包含该节点的旧 observation

### 4.3 任务完成自动报告生成

**目标**：任务结束后自动生成结构化渗透测试报告（Markdown / HTML）。

**设计方案**：

```python
# core/report_generator.py
class PentestReportGenerator:
    def __init__(self, graph_manager: GraphManager, task_id: str):
        self.gm = graph_manager
        self.task_id = task_id
    
    def generate(self) -> str:
        """生成 Markdown 格式报告。"""
        sections = [
            self._generate_header(),
            self._generate_executive_summary(),
            self._generate_target_fingerprint(),
            self._generate_findings_table(),
            self._generate_evidence_list(),
            self._generate_causal_chains(),
            self._generate_recommendations(),
        ]
        return "\n\n".join(sections)
    
    def _generate_findings_table(self) -> str:
        findings = self.gm.get_all_findings()
        rows = []
        for f in findings:
            rows.append(f"| {f.category} | {f.key} | {f.value} | {f.confidence} |")
        return "### 发现汇总\n\n| 分类 | 键 | 值 | 置信度 |\n|---|---|---|---|\n" + "\n".join(rows)
```

**报告输出位置**：`logs/{task_name}/{timestamp}/report.md`

**验收标准**：
- [ ] 任务结束后自动在日志目录生成 `report.md`
- [ ] 报告包含：目标指纹、发现列表、证据链、修复建议
- [ ] 报告可被 Web UI 下载查看

### 4.4 实时日志过滤与搜索（Web UI）

**目标**：右侧 `#llm-stream` 面板支持按关键词搜索和按事件类型过滤。

**设计方案**：

```javascript
// app.js: 在 subscribe() 中增加过滤层
let logFilters = {
    search: "",
    types: new Set(["executor", "planner", "reflector", "system"]),
};

function renderLogEntry(event, data) {
    const entry = formatLogEntry(event, data);
    
    // 过滤逻辑
    if (!logFilters.types.has(event.category)) return;
    if (logFilters.search && !entry.text.includes(logFilters.search)) return;
    
    appendToLogPanel(entry);
}

// HTML 增加过滤控件
// <input id="log-search" placeholder="搜索日志...">
// <select id="log-type-filter" multiple>
//   <option value="executor">执行器</option>
//   <option value="planner">规划器</option>
//   <option value="reflector">反思器</option>
// </select>
```

**验收标准**：
- [ ] 输入关键词实时过滤日志（防抖 300ms）
- [ ] 可按类型勾选显示/隐藏（如只看 executor 错误）
- [ ] 过滤后支持导出当前视图

### 4.5 环境配置检查脚本

**目标**：提供一个非交互式的环境检查命令，供用户在启动前快速验证配置和依赖。

**设计方案**：

```python
# core/preflight.py（替代原 onboarding.py，无交互）
def run_env_check() -> list[CheckResult]:
    """非交互式环境检查，输出报告后退出。"""
    checks = []
    
    # 1. LLM API Key 是否存在
    checks.append(check_env_var("LLM_API_KEY"))
    
    # 2. LLM API 连通性（发一条轻量请求）
    checks.append(check_llm_connectivity())
    
    # 3. 工具可执行文件（从 mcp.json 动态读取）
    for tool in load_registered_tools_from_mcp_config():
        checks.append(check_tool_available(tool))
    
    # 4. 数据库可写
    checks.append(check_database_writable())
    
    # 5. RAG 服务可达
    checks.append(check_knowledge_service())
    
    return checks

# 使用方式（CLI 一次性检查）
# python -m agent --check-env
```

**为什么不使用交互式向导**：
- 目标用户是安全工程师/开发者，`input()` 式向导过于"傻瓜化"
- `input()` 在异步事件中会阻塞 asyncio 事件循环
- 写 `.env` 需要解析/重写逻辑，增加维护成本
- 非交互式脚本更适合 CI/CD 和自动化部署

**Web UI 对应**：保留首次打开时的配置引导模态框（仅展示，不强制交互），作为文档补充。

**验收标准**：
- [ ] `python -m agent --check-env` 输出 5 项检查结果，总耗时 < 3 秒
- [ ] 检查失败时返回非 0 退出码，方便脚本判断
- [ ] 不阻塞、不写文件、不改配置，只读检查

### 4.6 任务模板库

**目标**：提供常见渗透测试场景的预设模板，用户一键选择即可开始。

**设计方案**：

```yaml
# conf/task_templates.yaml
- name: "Web 应用信息收集"
  goal: "对 {target} 进行信息收集，获取开放端口、服务指纹、技术栈、子域名和目录结构"
  recommended_tools: ["nmap", "httpx", "subfinder", "dirsearch", "nuclei"]
  
- name: "API 安全评估"
  goal: "对 {target} 的 API 接口进行安全评估，发现未授权访问、注入漏洞和敏感信息泄露"
  recommended_tools: ["http_request", "nuclei", "sqlmap", "python_exec"]
  
- name: "内网横向移动"
  goal: "在已获得初始访问权限的情况下，进行内网资产发现和横向移动路径分析"
  recommended_tools: ["nmap", "shell_exec", "python_exec"]
```

**Web UI 对应**：创建任务时，下拉选择模板，自动填充 goal 和推荐工具。

**验收标准**：
- [ ] 提供 5 个以上内置模板
- [ ] 选择模板后 goal 和工具推荐自动填充
- [ ] 用户可保存自定义模板

### 4.7 假设验证追踪面板

**目标**：在 P3 详情面板中新增"假设"标签页，显示假设的置信度变化时间轴。

**设计方案**：

```javascript
// app.js: renderHypothesisTab
function renderHypothesisTab(d) {
    const hypotheses = d.hypotheses || [];
    let h = '<div class="hypothesis-timeline">';
    hypotheses.forEach(hyp => {
        const confidenceClass = hyp.confidence > 0.7 ? 'high' : 
                               hyp.confidence > 0.4 ? 'medium' : 'low';
        h += `
            <div class="hypothesis-item ${confidenceClass}">
                <div class="hypothesis-status">${hyp.status}</div>
                <div class="hypothesis-desc">${escapeHtml(hyp.description)}</div>
                <div class="confidence-timeline">
                    ${renderConfidenceSparkline(hyp.history)}
                </div>
            </div>
        `;
    });
    h += '</div>';
    return h;
}
```

**验收标准**：
- [ ] 假设按置信度排序显示
- [ ] 每个假设显示状态变迁历史（PENDING → SUPPORTED/FALSIFIED）
- [ ] 小型折线图展示置信度随时间变化

---

## 5. 体验细节层设计

### 5.1 多任务管理台

**目标**：Web UI 左侧任务列表支持同时查看多个任务状态，点击切换。

**设计方案**：
- 将 `#ops` 面板从单选列表改为任务卡片网格
- 每个卡片显示：任务名、目标、状态徽章、进度条、最近更新时间
- 点击卡片切换主视图到该任务的 DAG

**验收标准**：
- [ ] 同时显示 5+ 个任务卡片
- [ ] 状态实时刷新（SSE 推送）
- [ ] 支持按状态过滤（running / completed / crashed）

### 5.2 异常告警通知

**目标**：任务异常退出或发现高危漏洞时，发送外部通知。

**设计方案**：

```python
# core/notifier.py
class Notifier:
    def __init__(self, webhook_url: str | None = None):
        self.webhook_url = webhook_url
    
    async def send_alert(self, level: str, title: str, message: str):
        """发送告警通知。"""
        if not self.webhook_url:
            return
        payload = {
            "level": level,  # info / warning / critical
            "title": title,
            "message": message,
            "timestamp": time.time(),
        }
        async with httpx.AsyncClient() as client:
            await client.post(self.webhook_url, json=payload)
```

**支持渠道**：
- Webhook（通用）
- 钉钉（通过 webhook）
- 飞书（通过 webhook）
- 本地系统通知（Windows Toast / macOS Notification）

**验收标准**：
- [ ] 任务 `crashed` 时发送告警
- [ ] 发现 `critical` 级别漏洞时发送告警
- [ ] 通知内容包含任务 ID 和 Web 监控台链接

### 5.3 移动端适配

**目标**：在手机浏览器上也能查看任务状态和关键发现。

**设计方案**：
- 小屏（< 768px）时，DAG 视图切换为**简化列表视图**：
  - 按时间顺序显示节点列表（而非图谱）
  - 每个节点显示：状态图标、工具名、关键发现数
  - 点击展开详情（5 标签面板）
- 隐藏左右侧边栏，改为底部导航栏
- 证据浏览器改为单栏垂直布局

**验收标准**：
- [ ] iPhone Safari 上可正常浏览任务列表
- [ ] 节点详情面板可上下滑动查看
- [ ] 不依赖鼠标悬停交互

---

## 6. 实施优先级

### Phase 1（本周内）—— 修复阻塞性问题

| 优先级 | 优化项 | 预计工时 | 影响 |
|--------|--------|----------|------|
| P0 | Agent 异常熔断与自动恢复 | 3-4h | 任务不再中途退出 |
| P0 | 启动前环境校验 | 2-3h | 提前发现工具缺失 |

### Phase 2（2 周内）—— 核心功能增强

| 优先级 | 优化项 | 预计工时 | 影响 |
|--------|--------|----------|------|
| P1 | 任务断点续传 | 4-5h | 异常后可恢复 |
| P1 | 进程启动方式标准化 | 1h | 服务稳定运行 |
| P1 | DAG 节点重启与增量执行 | 4h | 避免重建整个任务 |
| P1 | 实时日志过滤搜索 | 3h | 调试效率提升 |
| P1 | 任务完成自动报告 | 4h | 交付物自动化 |

### Phase 3（1 个月内）—— 体验提升

| 优先级 | 优化项 | 预计工时 | 影响 |
|--------|--------|----------|------|
| P2 | 环境配置检查脚本 | 1h | 快速验证环境 |
| P2 | 任务模板库 | 2h | 快速开始任务 |
| P2 | 假设验证追踪面板 | 3h | 因果推理可视化 |
| P2 | 实时因果链动画 | 4h | DAG 视觉升级 |
| P2 | 异常告警通知 | 3h | 及时响应问题 |
| P2 | 多任务管理台 | 4h | 并发任务管理 |
| P2 | 移动端适配 | 5h | 随时随地查看 |

---

## 7. 文件变更预估

### 新增文件
| 文件 | 说明 |
|------|------|
| `core/checkpoint.py` | 断点续传逻辑（JSON 格式） |
| `core/preflight.py` | 启动前环境校验 + `--check-env` 命令 |
| `core/notifier.py` | 告警通知 |
| `core/report_generator.py` | 自动报告生成 |
| `conf/task_templates.yaml` | 任务模板配置 |
| `scripts/supervise-agent.ps1` | Windows 进程守护脚本（PowerShell） |
| `scripts/luan1ao-agent.service` | Linux systemd 配置模板 |
| `tests/core/test_checkpoint.py` | 断点续传测试 |
| `tests/core/test_preflight.py` | 环境校验测试 |
| `tests/core/test_restart_node.py` | 节点重启与级联重置测试 |

### 修改文件
| 文件 | 改动 |
|------|------|
| `agent.py` | 主循环加 `try/except`，启动时调用 `preflight_check()`，结束时调用 `report_generator` |
| `core/executor.py` | 每周期结束调用 `save_checkpoint()`；新增 `purge_messages_for_node()` |
| `core/graph_manager.py` | 新增 `export_state()` / `import_state()`、`restart_node()` 方法 |
| `web/server.py` | 新增 `/api/report/{op_id}/download`、`/api/node/{node_id}/restart` 端点 |
| `web/static/app.js` | 日志过滤、假设面板、多任务管理、因果链动画、节点右键菜单（重启） |
| `web/templates/index.html` | 新增过滤控件、响应式 CSS |

---

## 8. 注意事项

- **向后兼容**：Checkpoint 使用 JSON 格式并包含 `version` 字段，未来格式升级时根据版本号做兼容处理
- **资源控制**：系统级进程守护（systemd/supervisor）应配置最大重启次数（5 次），避免无限循环
- **敏感信息**：自动报告生成时，日志中的 API Key、Token 需自动脱敏（`***` 替换）
- **通知降噪**：告警通知设置冷却时间（同一任务 5 分钟内不重复发送同类告警）
