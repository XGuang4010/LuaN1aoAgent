# 渗透边界控制 (Scope Boundary Control) 设计文档

> 创建日期: 2026-05-21 | 状态: 设计中 | 作者: Agent + davii

## 1. 问题陈述

当前 LuaN1ao Agent 缺少渗透测试边界控制机制：
- Executor 可调用 `shell_exec` / `python_exec` 执行任意系统命令
- MCP 工具可向任意目标发起 HTTP 请求，无 scope 检查
- 没有阻止扫描内网 IP（10.0.0.0/8 等）、敏感域名、私有地址的机制
- 存在测试范围越界的安全风险

## 2. 设计目标

1. **默认安全**：开箱即用的保守边界（禁止内网、默认端口受限）
2. **按需放开**：用户可在任务创建时逐项覆盖默认策略
3. **双重拦截**：Executor 层 + MCP 工具层各校验一次，防止 LLM 绕过 prompt 限制
4. **审计可追溯**：拦截事件持久化到 event_logs，违规行为可复盘
5. **与现有架构一致**：沿用 `conf/config.py` 全局默认 + HITL 逐任务覆盖模式

## 3. 架构设计

### 3.1 三层控制模型

```
┌─────────────────────────────────────────────────────────┐
│  层1: 默认策略  (conf/config.py)                        │
│     环境变量 + 硬编码默认值 → 加载为 SCOPE_CONFIG dict   │
│     变更需重启生效                                        │
├─────────────────────────────────────────────────────────┤
│  层2: 任务级边界  (agent.py + DB + Web UI)              │
│     任务创建时从默认值加载 scope 配置                     │
│     用户通过 Web UI / CLI 按需逐项覆盖                    │
│     以 ScopeRule 模型持久化到 SQLite                      │
├─────────────────────────────────────────────────────────┤
│  层3: 强制拦截  (core/boundary.py)                      │
│     每次工具调用前执行 BoundaryValidator.check()          │
│     Executor 侧拦截: 工具调用前的第一道防线               │
│     MCP 工具侧拦截: 第二道防线（防御纵深）                │
│     拦截事件写入 event_logs                               │
└─────────────────────────────────────────────────────────┘
```

### 3.2 数据流

```
.env / 环境变量
    │
    ▼
conf/config.py → 解析 SCOPE_CONFIG = {...}
    │
    ▼
Web UI "新建任务" 弹窗
    ├── 预填 ScopeConfig 默认值
    ├── 用户可修改任意字段
    └── "重置为默认" 按钮恢复出厂值
    │
    ▼
agent.py.__init__(..., scope_config=user_scope)
    │
    ▼
executor._execute_subtask()
    ├── 构造 prompt 时注入 scope 约束文本
    ├── _handle_local_tool() 调用前 fetch:
    │     boundary = BoundaryValidator(task_scope)
    │     ok, msg = boundary.validate_tool_call(tool, params)
    │     if not ok → 阻止执行 + 记录 event_log
    │
    └── 远程工具 (call_mcp_tool_async):
          params 中附加 X-Scope-Boundary header → mcp_service 二次校验
```

## 4. 控制维度

### 4.1 目标范围控制 (Target Scope)

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `allowed_targets` | `List[str]` | `["*"]` | 允许的目标 CIDR/域名/IP，空表示无限制 |
| `blocked_targets` | `List[str]` | RFC1918 + loopback + link-local | 禁止扫描的地址块 |
| `allowed_ports` | `List[int]` | `[80, 443, 8080, 8443]` | 允许扫描的端口，空表示无限制 |

默认 blocked：
- `10.0.0.0/8`、`172.16.0.0/12`、`192.168.0.0/16` (RFC1918)
- `127.0.0.0/8` (loopback)
- `169.254.0.0/16` (link-local)
- `0.0.0.0/8` (current network)

### 4.2 工具限制 (Tool Restrictions)

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `disabled_tools` | `List[str]` | `[]` | 全局禁用的工具名列表 |
| `tool_param_rules` | `Dict[str, Dict]` | `{}` | 各工具参数校验规则 |
| `disable_shell_exec` | `bool` | `false` | 建议生产环境设为 `true` |
| `disable_python_exec` | `bool` | `false` | 建议生产环境设为 `true` |

### 4.3 网络约束 (Network Constraints)

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `block_private_network` | `bool` | `true` | 禁止内网 IP 扫描 |
| `block_dns_rebinding` | `bool` | `true` | 禁止 DNS 重绑定攻击 |
| `enforce_tls_verification` | `bool` | `true` | 强制 TLS 证书校验 |

### 4.4 数据与速率限制 (Rate & Data Limits)

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `max_response_size` | `int` | `50000` | HTTP 响应最大字节数 |
| `rate_limit_requests_per_sec` | `float` | `10.0` | 每秒请求数上限 |
| `max_concurrent_connections` | `int` | `20` | 最大并发连接数 |

## 5. 数据结构

### 5.1 ScopeConfig (Python dataclass)

```python
@dataclass
class ScopeConfig:
    """单任务渗透边界配置"""
    # 目标范围
    allowed_targets: List[str] = field(default_factory=lambda: ["*"])
    blocked_targets: List[str] = field(default_factory=lambda: [
        "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
        "127.0.0.0/8", "169.254.0.0/16", "0.0.0.0/8"
    ])
    allowed_ports: List[int] = field(default_factory=lambda: [80, 443, 8080, 8443])

    # 工具限制
    disabled_tools: List[str] = field(default_factory=list)
    tool_param_rules: Dict[str, Any] = field(default_factory=dict)
    disable_shell_exec: bool = False
    disable_python_exec: bool = False

    # 网络约束
    block_private_network: bool = True
    block_dns_rebinding: bool = True
    enforce_tls_verification: bool = True

    # 数据与速率
    max_response_size: int = 50000
    rate_limit_requests_per_sec: float = 10.0
    max_concurrent_connections: int = 20

    @classmethod
    def from_global_config(cls, overrides: Optional[Dict] = None) -> 'ScopeConfig':
        """从 conf/config.py 加载默认值，并用 overrides 覆盖"""
        ...

    def to_dict(self) -> Dict: ...
    def to_prompt_context(self) -> str:
        """生成为 LLM prompt 中的约束描述文本"""
        ...
```

### 5.2 数据库模型

```python
class ScopeRuleModel(Base):
    __tablename__ = "scope_rules"
    id: str          # UUID
    session_id: str  # FK→sessions
    scope_config: JSON  # ScopeConfig.to_dict() 的序列化结果
    created_at: DateTime
    updated_at: DateTime
```

### 5.3 校验结果

```python
@dataclass
class BoundaryCheckResult:
    allowed: bool
    reason: str       # 通过时为空，拦截时为具体原因
    rule_name: str    # 触发的规则名
    detail: Dict       # 额外上下文
```

## 6. BoundaryValidator 核心接口

```python
class BoundaryValidator:
    def __init__(self, scope: ScopeConfig):
        self.scope = scope

    def validate_tool_call(self, tool_name: str, params: Dict) -> BoundaryCheckResult:
        """验证单次工具调用是否在边界内"""
        # 1. 工具白名单/禁用检查
        # 2. 目标地址检查 (allowed_targets, blocked_targets, private_network)
        # 3. 端口检查 (allowed_ports)
        # 4. 参数合法性检查 (tool_param_rules)
        ...

    def validate_target(self, host: str, port: int = None) -> BoundaryCheckResult:
        """验证目标地址是否允许"""
        ...

    def get_blocked_reason_detail(self, host: str, rule: str):
        """获取详细的拦截原因，用于 event_log 记录"""
        ...

    def to_prompt_instruction(self) -> str:
        """将 scope 约束转为 LLM system prompt 注入文本"""
        ...
```

## 6.1 拦截逻辑优先序

1. `disabled_tools` → 直接拒绝（最高优先级）
2. `blocked_targets` → 直接拒绝
3. `block_private_network` → 检查目标IP是否为私有地址
4. `allowed_ports` → 检查端口是否在允许列表
5. `allowed_targets` → 检查是否为 `["*"]` 或匹配
6. 速率限制 → 令牌桶判断

拦截时：记录到 `event_logs`，返回结构化错误给 Executor。

## 7. 集成点

### 7.1 conf/config.py

```python
# 新增区块
SCOPE_DEFAULTS = {
    "blocked_targets": ["10.0.0.0/8", ...],
    "allowed_ports": [80, 443, 8080, 8443],
    "block_private_network": True,
    ...
}
# 每个字段均可通过环境变量覆盖: SCOPE_BLOCKED_TARGETS, SCOPE_ALLOWED_PORTS 等
```

### 7.2 agent.py

```python
class LuaN1aoAgent:
    def __init__(self, ..., scope_config: Optional[ScopeConfig] = None):
        if scope_config is None:
            self.scope = ScopeConfig.from_global_config()
        else:
            self.scope = scope_config
        self.validator = BoundaryValidator(self.scope)
```

### 7.3 executor.py

```python
# _handle_local_tool / call_mcp_tool_async 调用前插入
result = validator.validate_tool_call(tool_name, params)
if not result.allowed:
    return {"error": f"边界拦截: {result.reason}", "rule": result.rule_name}
```

### 7.4 mcp_service.py (关键工具)

```python
# http_request 等工具内部增加二次校验
@mcp.tool()
def http_request(url: str, ...):
    # 从 params 获取 X-Scope-Boundary header
    # 解析 scope 并执行与 executor 相同的校验
```

### 7.5 web/server.py + app.js

- `POST /api/ops` 增加 `scope_config` 字段
- `PATCH /api/ops/{op_id}` 支持修改 scope
- 前端任务创建弹窗：scope 配置面板（默认值预填，可折叠）

## 8. 安全考量

- **双重防线**：LLM 可能忽略 prompt 中的 scope 指令，Executor 层在代码层硬性拦截
- **MCP 工具防线**：即使绕过 Executor 直接调用 MCP，工具内部仍有校验
- **默认拒绝**：未明确允许的一律拒绝，采用安全优先策略
- **日志可审计**：所有拦截事件记录 reason + rule + timestamp

## 9. 实施计划

| 序号 | 模块 | 内容 | 优先级 |
|------|------|------|--------|
| 1 | `conf/config.py` | 新增 `SCOPE_DEFAULTS` 配置块 | P0 |
| 2 | `core/boundary.py` | 新建 `BoundaryValidator` + `ScopeConfig` dataclass | P0 |
| 3 | `core/executor.py` | 工具调用前插入 `boundary.check()` | P0 |
| 4 | `agent.py` | 初始化时加载 scope，传递给 executor | P0 |
| 5 | `tools/mcp_service.py` | http_request 增加二次校验 | P1 |
| 6 | `core/database/models.py` | 新增 `ScopeRuleModel` 表 | P1 |
| 7 | `web/server.py` + `app.js` | 任务创建时 scope 配置 UI + API | P1 |

## 10. 回顾确认

- [x] 默认私有网络地址硬性拦截（可在任务中白名单放开）
- [x] shell_exec / python_exec 默认不禁用（生产环境建议手动开启）
- [x] 用户可在任务中临时添加 allowed_targets（如 `10.0.1.5`）
- [x] 与现有 HITL 模式和 InterventionManager 架构一致