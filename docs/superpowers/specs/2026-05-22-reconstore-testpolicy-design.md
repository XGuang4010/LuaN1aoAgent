# ReconStore + TestPolicy 设计文档

**日期**: 2026-05-22  
**状态**: Draft  
**作者**: LuaN1ao Agent Team  

---

## 1. 背景与目标

### 1.1 问题陈述

当前 LuaN1ao Agent 的 Planner 输出图编辑指令（`ADD_NODE` / `UPDATE_NODE` / `DEPRECATE_NODE`）动态生成 subtask，无硬编码阶段枚举。Planner 自由生成 subtask，没有阶段意识。渗透测试过程中产生的信息（域名、子域名、IP、端口、接口、技术栈、凭证等）散落在各 subtask 的日志中，无法系统化查询和复用。

同时，不同 SRC（安全应急响应中心）平台对渗透测试有不同的规范要求（如 SSRF 验证必须使用指定回调地址、禁止上传 webshell 等），当前缺乏将这些约束注入到测试执行中的机制。

### 1.2 设计目标

1. **系统化信息采集**：建立统一的信息采集仓库（ReconStore），对渗透测试全过程中发现的信息进行分类持久化存储。
2. **可查询、可复用**：提供按目标（域名/IP）查询的 Web UI 和 API，做到随时可查。
3. **测试守则动态注入**：支持在 Task 创建时传入测试规范文档，由 AI 自动解析后注入到对应漏洞类型的 subtask 中。
4. **不破坏现有架构**：ReconStore 和 TestPolicy 作为独立模块，以钩子方式集成到现有 P-E-R 循环中。

### 1.3 设计原则

- **增强而非替换**：保留现有 Plan-on-Graph 动态规划架构，新增模块作为支撑层。
- **阶段意识软引导**：Planner 提示词增加 recon 相关信息采集示例，引导 Planner 在适当时候生成信息收集类 subtask，但不强制阶段门控。
- **扁平化存储**：ReconStore 采用单表 + JSON value 设计，避免 schema 变更成本。
- **文档驱动策略**：TestPolicy 采用自然语言文档输入，AI 解析为结构化约束，而非硬编码规则引擎。

---

## 2. 整体架构

```
┌─────────────────────────────────────────────────────────┐
│  LuaN1ao Agent (现有 P-E-R 架构)                         │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌──────────┐  │
│  │ Planner │→│Executor │→│Reflector│→│GraphManager│ │
│  └─────────┘  └────┬────┘  └─────────┘  └──────────┘  │
│                    │                                    │
│         ┌──────────┴──────────┐                        │
│         │  MCP Tool Execution │                        │
│         └─────────────────────┘                        │
└─────────────────────────────────────────────────────────┘
                          │
         ┌────────────────┼────────────────┐
         ▼                ▼                ▼
   ┌──────────┐   ┌──────────────┐   ┌─────────────┐
   │ReconStore│   │ TestPolicy   │   │ Web UI API  │
   │(信息采集) │   │ (测试守则)    │   │ (查询接口)   │
   └──────────┘   └──────────────┘   └─────────────┘
         │                │                │
         └────────────────┴────────────────┘
                          │
                    ┌─────┴─────┐
                    │ SQLite DB │  ← 复用现有数据库
                    │  (+ recon │     新增 recon_records
                    │   tables) │     和 task_policies 表
                    └───────────┘
```

### 2.1 集成点（仅 3 处）

| 集成点 | 位置 | 行为 |
|--------|------|------|
| 信息采集 | Executor 执行完成后 | 从 tool_output 提取结构化信息，写入 ReconStore |
| 策略注入 | Planner 生成 ADD_NODE 时 | 匹配漏洞类型，将约束注入 subtask 节点 |
| 查询展示 | Web Server | 新增 `/recon/*` 路由，提供 API 和页面 |

所有集成均为**钩子式**，不阻塞现有执行流。ReconStore 或 TestPolicy 故障时，渗透测试继续运行。

> **注意**：当前 MCP 工具实际为 `think`、`complete_mission`、`formulate_hypotheses`、`reflect_on_failure`、`expert_analysis`、`retrieve_knowledge`、`distill_knowledge`、`web_search`、`shell_exec`。本文档中涉及的 `http_request`、`python_exec`、`info_extract`、`query_causal_graph` 均为**新增或待确认的工具**，需在 `mcp.json` 中注册并在 `tools/mcp_service.py` 中实现。

---

## 3. ReconStore 模块设计

### 3.1 数据模型

采用**单表 + JSON value**的扁平设计，避免信息类型扩展时频繁修改 schema。

#### 核心表：`recon_records`

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PK | 自增主键 |
| `task_id` | STRING, INDEX | 所属渗透任务 ID |
| `record_type` | STRING, INDEX | 信息类型（见下表） |
| `target` | STRING, INDEX | 聚合键，主域名或 IP，如 `example.com` 或 `1.2.3.4` |
| `value` | JSON | 结构化详情，按类型有不同 schema |
| `source_step_id` | STRING | 来源 step ID（Executor 为每个工具调用生成的唯一标识），可追溯 |
| `confidence` | FLOAT | 置信度。工具直接输出的填 1.0，LLM 提取的填 0.8（初始经验值，后续可根据准确率校准） |
| `created_at` | DATETIME | 创建时间 |

#### 信息类型（record_type）

| 类型 | 说明 | 示例 |
|------|------|------|
| `domain` | 域名/子域名 | `api.example.com` |
| `ip` | IP 地址 | `1.2.3.4` |
| `port` | 开放端口 | `443/tcp open` |
| `endpoint` | URL 路由/接口 | `GET /api/v1/users` |
| `service` | 服务类型及版本 | `nginx 1.18.0` |
| `tech` | 技术栈/框架 | `Spring Boot` |
| `credential` | 凭证（Token/Cookie/密码） | `jwt_token: eyJ...` |
| `sensitive` | 敏感信息泄露 | `api_key exposed in JS` |
| `auth` | 认证信息 | `login_required: true, login_url: /login` |
| `file` | 目录/文件发现 | `/admin/ (200 OK)` |

#### Value Schema 示例

```python
# domain
{"name": "api.example.com", "is_subdomain": true, "parent": "example.com"}

# ip
{"address": "1.2.3.4", "type": "ipv4", "cdn": false}

# port
{"number": 443, "protocol": "tcp", "state": "open", "service_hint": "https"}

# endpoint
{
  "url": "https://api.example.com/v1/users",
  "method": "GET",
  "status_code": 200,
  "content_type": "application/json",
  "auth_required": false,
  "parameters": [{"name": "id", "type": "int"}]
}

# service
{"name": "nginx", "version": "1.18.0", "banner": "Server: nginx/1.18.0"}

# tech
{"name": "Spring Boot", "category": "framework", "indicator": "X-Application-Context header"}

# credential
{"type": "jwt_token", "value": "eyJ...", "context": "found in response body", "scope": "api.example.com"}

# sensitive
{"type": "api_key", "value": "sk-...", "context": "exposed in JS bundle app.js"}

# auth
{
  "requires_auth": true,
  "login_url": "/login",
  "auth_type": "cookie",
  "registration_available": true,
  "registration_url": "/register"
}

# file
{"path": "/admin/", "type": "directory", "status_code": 200, "interesting": true, "note": "exposes admin panel"}
```

### 3.2 去重策略

#### 单通道去重
同一 `task_id` + `record_type` + `target` + `value` 的核心标识字段（如 `value.name`、`value.address`、`value.url`）视为重复。

- 发现重复时：更新 `confidence` 取最高值，更新 `source_step_id` 为最新来源，不新增记录。
- 无核心标识字段时：使用 `value` JSON 全内容做 MD5 哈希比对。

#### 跨通道去重
通道 1（工具规范化）和通道 2（LLM 提取）可能产生同一信息的重复记录。跨通道去重规则：

- `ip` 类型：`value.address` 相同视为重复，保留 `confidence` 更高者（通常为通道 1 的 1.0）
- `port` 类型：`value.number` + `value.protocol` 相同视为重复
- `endpoint` 类型：`value.url` 相同视为重复
- `domain` 类型：`value.name` 相同视为重复
- 其他类型：使用 `value` JSON 核心字段做 MD5 比对

跨通道重复时，优先保留通道 1（工具规范化）的记录，因为置信度更高。

### 3.3 查询接口

复用现有 FastAPI Web Server，新增路由：

```
GET  /api/recon/{task_id}              → 列表查询（支持 ?type=endpoint&target=xxx 过滤）
GET  /api/recon/{task_id}/summary      → 按类型聚合统计
GET  /api/recon/{task_id}/targets      → 所有主 target 去重列表
GET  /api/recon/{task_id}/timeline     → 按时间线查看发现过程
POST /api/recon/{task_id}/query        → 复杂过滤（JSON body：{type:["endpoint"], target:"example.com"}）
GET  /recon                             → HTML 查询页面
```

---

## 4. 信息采集机制（双通道）

### 4.1 通道 1：工具输出规范化（确定性采集）

各扫描工具（nmap、httpx 等）在执行后，除原始输出外，**新增** `structured_findings` 字段，按统一 schema 输出结构化数据。ReconStore 直接消费该字段，**无需 LLM 介入**。

> **实现方案**：不为 nmap/httpx 改造 `shell_exec` 的通用返回格式（避免影响所有 shell 命令），而是为 nmap/httpx 创建**专用的 MCP 工具封装**（如 `nmap_scan`、`httpx_scan`），在封装层解析原始输出并生成 `structured_findings`。

#### 4.1.1 nmap_scan structured_findings

```json
{
  "hosts": [
    {
      "ip": "192.168.1.1",
      "hostname": "router.local",
      "mac": "00:11:22:33:44:55",
      "vendor": "TP-LINK",
      "os": {
        "name": "Linux 5.4",
        "family": "linux",
        "accuracy": 95
      },
      "ports": [
        {
          "number": 80,
          "protocol": "tcp",
          "state": "open",
          "reason": "syn-ack",
          "service": {
            "name": "http",
            "product": "nginx",
            "version": "1.18.0",
            "extrainfo": "Ubuntu",
            "cpe": ["cpe:/a:nginx:nginx:1.18.0"]
          },
          "scripts": [
            {
              "id": "http-title",
              "output": "Welcome to nginx!"
            }
          ]
        }
      ]
    }
  ],
  "summary": {
    "total_hosts": 1,
    "up_hosts": 1,
    "total_open_ports": 3,
    "scan_type": "syn",
    "scan_duration_seconds": 15.2
  }
}
```

**映射到 ReconStore**：
- `host.ip` → `record_type: ip`
- `host.hostname` → `record_type: domain`
- `port` → `record_type: port`
- `port.service` → `record_type: service`
- `script.output` → `record_type: tech`

#### 4.1.2 httpx_scan structured_findings

```json
{
  "endpoints": [
    {
      "url": "https://api.example.com/v1/users",
      "scheme": "https",
      "host": "api.example.com",
      "port": 443,
      "path": "/v1/users",
      "status_code": 200,
      "title": "User API",
      "content_length": 2048,
      "content_type": "application/json",
      "technologies": ["Swagger UI", "Express", "React"],
      "webserver": "nginx",
      "headers": {
        "Server": "nginx/1.18.0",
        "X-Powered-By": "Express",
        "X-Frame-Options": "DENY"
      },
      "favicon": {
        "path": "/favicon.ico",
        "hash": "12345678",
        "hash_md5": "abcdef123456"
      },
      "tls": {
        "subject": "CN=api.example.com",
        "issuer": "CN=Let's Encrypt Authority X3",
        "not_before": "2024-01-01",
        "not_after": "2025-12-01",
        "cipher": "TLS_AES_256_GCM_SHA384"
      },
      "response_time_ms": 45,
      "chain": [
        {"url": "http://api.example.com/v1/users", "status_code": 301},
        {"url": "https://api.example.com/v1/users", "status_code": 200}
      ]
    }
  ],
  "summary": {
    "total_urls": 100,
    "successful": 85,
    "failed": 15,
    "duration_seconds": 23.5
  }
}
```

**映射到 ReconStore**：
- `endpoint.url` → `record_type: endpoint`
- `endpoint.technologies` → `record_type: tech`
- `endpoint.tls` → `record_type: service`
- `endpoint.headers.Server` → `record_type: service`

### 4.2 通道 2：LLM 提取（非结构化采集）

通用工具（`http_request`（新增）、`python_exec`（新增））的输出不确定，无法预设 schema，走 LLM 提取通道。

#### 4.2.1 Executor 自动提取（无感采集）——**新增功能**

**触发时机**：工具状态为 `completed` 后、Reflector 之前。

**流程**：
```
tool_output → 检查是否有 structured_findings
    ├─ 有 → 直接入库，跳过 LLM
    └─ 无 → 轻量 LLM 提取 → ReconStore 写入
```

**提取模型**：使用配置中便宜的模型（如 `gpt-4o-mini` 或本地小模型），降低成本。

**输入**：tool_name + tool_params + result_str（前 4000 token）。

**输出格式**：
```json
{
  "records": [
    {
      "type": "endpoint",
      "target": "example.com",
      "value": {"url": "...", "method": "GET"},
      "confidence": 0.9
    }
  ]
}
```

**容错**：提取失败不阻塞主流程，静默丢弃。

#### 4.2.2 info_extract 专用工具（主动采集）——**新增 MCP 工具**

需在 `mcp.json` 中注册，并在 `tools/mcp_service.py` 中实现。供 Executor 显式调用：

```json
{
  "tool": "info_extract",
  "params": {
    "text": "<原始响应或页面内容>",
    "context": "从 nmap 扫描结果中提取开放端口和服务"
  }
}
```

**用途**：
- 自动提取遗漏时，Executor 主动补充。
- 分析大段文本（如 JS 源码、HTML 页面）时专门调用。
- 用户人工干预时，手动分析任意文本。

---

## 5. TestPolicy 模块设计

### 5.1 核心理念

不靠硬编码规则引擎，采用**文档解析 + 动态注入**：

1. 用户传入自然语言测试规范文档。
2. 轻量级 LLM 解析为按漏洞类型分类的结构化约束。
3. Planner 生成漏洞测试 subtask 时，自动将对应约束注入该 subtask 的上下文。
4. Executor 生成脚本时，约束出现在 prompt 中，影响 LLM 行为。

### 5.2 文档输入方式

Task 创建时 3 种入口：

```bash
# 1. 命令行直接传文本
python agent.py --target example.com --policy "SQL注入只允许sleep验证"

# 2. 文件路径（支持 .md / .txt）
python agent.py --target example.com --policy-file ./src_policy.md

# 3. 环境变量（自动化场景）
export TEST_POLICY='{"raw":"SSRF验证使用 https://your-burpcollab.net"}'
```

### 5.3 文档解析流程

```
原始 policy 文档（自然语言）
        ↓
轻量 LLM 解析
        ↓
结构化约束 JSON（按漏洞类型分类）
        ↓
存入 SQLite task_policies 表
```

#### task_policies 表结构

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PK | 自增主键 |
| `task_id` | STRING, UNIQUE | 所属任务 ID，一对一关联 |
| `raw_policy` | TEXT | 原始 policy 文档全文 |
| `parsed_policy` | JSON | LLM 解析后的结构化约束 JSON |
| `parse_status` | STRING | `success` / `failed` / `partial` |
| `parse_error` | TEXT | 解析失败时的错误信息（如有） |
| `created_at` | DATETIME | 创建时间 |
| `updated_at` | DATETIME | 更新时间 |

**解析失败降级策略**：

- 若 LLM 解析返回非法 JSON 或为空：降级为**全文注入** —— 将原始 policy 文档全文拼接到所有漏洞测试 subtask 的 prompt 中，而非按类型注入结构化约束。
- 若解析结果遗漏关键约束（如检测到 policy 文档提到了"SSRF"但解析结果无 `ssrf` 键）：记录警告日志，仍使用解析结果，但追加免责声明："部分约束可能未正确解析，请同时参考测试守则原文"。

**实现概要**：
- 解析失败检测：对 LLM 输出做 `json.loads` 校验，失败则设置 `task_policies.parse_failed = true`
- 全文注入方式：在 `process_graph_commands` 中，若检测到 `parse_failed` 标志，将 `raw_policy_text` 附加到每个 subtask 的 `node_data["policy_context"]` 中（限制长度不超过 2000 token，超长则截取前 2000 token 并标注"已截断"）
- 免责声明追加：在 Executor 构建 system prompt 时，若 `policy_context` 类型为字符串（非结构化 JSON），自动在约束前添加免责声明前缀

**解析示例**：

输入（自然语言）：
> "SQL 注入验证只允许使用 sleep 和布尔盲注，禁止使用 update/delete/drop 语句。SSRF 验证请使用 https://your-burpcollab.net。不允许上传 webshell 或内存马。命令执行只允许读取文件（cat /etc/passwd），禁止反弹 shell。"

输出（结构化）：
```json
{
  "sql_injection": {
    "allowed_verification": ["sleep", "boolean_blind"],
    "forbidden_keywords": ["UPDATE", "DELETE", "DROP"]
  },
  "ssrf": {
    "callback_url": "https://your-burpcollab.net"
  },
  "file_upload": {
    "forbidden": ["webshell", "memory_shell"]
  },
  "command_execution": {
    "allowed": ["cat", "ls", "id", "whoami"],
    "forbidden": ["nc", "bash -i", "python -c 'import socket'"]
  }
}
```

### 5.4 约束注入机制（subtask 级别）

#### 5.4.1 注入时机 ——**新增功能**

Planner 生成 `ADD_NODE` 时，根据 `description` 自动匹配漏洞类型关键词：

```python
# 伪代码，位于 agent.py 的 process_graph_commands 中
# 注意：classify_vuln_type() 和 policy.get_constraints() 均为新增函数
# add_subtask_node() 需扩展支持 extra_data 参数以存储 policy_context
if node_data.get("description"):
    vuln_type = classify_vuln_type(node_data["description"])  # 新增：关键词匹配
    constraints = policy.get_constraints(vuln_type)           # 新增：从 task_policies 表取约束
    if constraints:
        # 实现方案：add_subtask_node 调用后，通过 update_node 注入 extra_data
        # 不修改 add_subtask_node 核心签名
        node_data["extra_data"] = {"policy_context": constraints}
```

#### 5.4.2 漏洞类型分类映射

| 关键词匹配 | 漏洞类型 | Policy 约束示例 |
|-----------|---------|----------------|
| `sql`, `sqli`, `注入` | `sql_injection` | 只允许 sleep/布尔盲注 |
| `ssrf`, `服务器请求伪造` | `ssrf` | 必须使用指定回调地址 |
| `rce`, `命令执行`, `cmd` | `command_execution` | 只允许读文件，禁止反弹 shell |
| `upload`, `文件上传` | `file_upload` | 禁止 webshell/内存马 |
| `xss`, `跨站` | `xss` | 只允许 alert(1) 验证 |
| `idor`, `越权` | `idor` | 测试范围限制在指定用户ID区间 |

#### 5.4.3 Executor 消费

Executor 构建 subtask 的 system prompt 时，如果 `policy_context` 存在，拼接到 prompt 中：

```
【任务描述】
测试 api.example.com 的 SQL 注入漏洞

【测试约束】
- SQL 注入验证只允许使用 sleep 和布尔盲注
- 禁止使用 UPDATE/DELETE/DROP 语句

【可用工具】...
```

约束**只对当前 subtask 生效**，不影响其他 subtask。

### 5.5 兜底安全机制

虽然主策略靠 AI 上下文注入，但保留一个最简硬的 denylist，仅在极端危险操作时拦截：

```python
HARD_DENYLIST = [
    "rm -rf /",
    "reboot",
    "poweroff",
    "mkfs",
    "dd if=/dev/zero",
    "iptables -F"
]
```

当 `shell_exec` 的命令/脚本匹配上述模式时直接拦截并返回错误；`python_exec`（待实现）在实现后同样受此限制。

> **局限性说明**：`HARD_DENYLIST` 仅做字面匹配，可被变量替换（`a="rm"; $a -rf /`）、编码、分段拼接等方式绕过。此为**临时兜底方案**，后续应升级为沙箱隔离或更完善的命令解析器。当前版本不承诺完全防绕过。

---

## 6. Web UI 查询设计

复用现有 `web/server.py`，新增 `/recon` 路由组。

### 6.1 API 端点

```
GET  /api/recon/{task_id}?type=endpoint&target=api.example.com&limit=50
GET  /api/recon/{task_id}/summary
GET  /api/recon/{task_id}/targets
GET  /api/recon/{task_id}/timeline
POST /api/recon/{task_id}/query        → JSON body 复杂过滤
GET  /recon                             → HTML 查询页面
```

### 6.2 页面布局（极简）

```
┌─────────────────────────────────────────┐
│  Task: default_task    [刷新]           │
├──────────┬──────────────────────────────┤
│ 过滤     │  结果列表                     │
│ ─────────┤                              │
│ Type:    │  api.example.com/v1/users    │
│ ☑ domain │  └─ type: endpoint, 200 OK   │
│ ☑ ip     │                              │
│ ☑ port   │  192.168.1.1:3306            │
│ ☑ endpoint│ └─ type: port, mysql open   │
│ ☐ tech   │                              │
│ ☐ cred   │  [nginx 1.18.0]              │
│ ─────────┤  └─ type: service            │
│ Target:  │                              │
│ [example]│                              │
│ .com ▼   │                              │
└──────────┴──────────────────────────────┘
```

---

## 7. 数据流

### 7.1 信息采集数据流

```
[工具执行]
    │
    ├─ nmap / httpx ──→ structured_findings ──→ ReconStore（直接入库）
    │
    └─ shell_exec / python_exec(新增) / http_request(新增) ──→ tool_output
                                          │
                                          ├─ 有 structured_findings? → 直接入库
                                          │
                                          └─ 无? → LLM 提取 ──→ ReconStore
```

### 7.2 策略注入数据流

```
[Task 创建]
    │
    ├─ policy 文档输入
    │       │
    │       └─ LLM 解析 ──→ 结构化约束 JSON ──→ SQLite task_policies 表
    │
[Planner 循环]
    │
    └─ 生成漏洞测试 subtask
            │
            └─ classify_vuln_type(description)
                    │
                    └─ 匹配到约束? ──→ 注入 policy_context ──→ subtask 节点
```

---

## 8. 试点范围

本次实现**只覆盖 nmap 和 httpx**两个工具的 `structured_findings` 改造，作为试点验证机制可行性。

**试点实现方案**：
1. 在 `tools/mcp_service.py` 中新增 `nmap_scan` 和 `httpx_scan` MCP 工具（专用封装）
2. 在 `mcp.json` 中注册上述工具
3. 封装层内部调用 `shell_exec` 执行实际命令，解析输出后生成 `structured_findings`
4. ReconStore 消费 `structured_findings` 并入库

其他工具（dirsearch、sqlmap、subfinder 等）在试点成功后按相同模式批量改造。

---

## 9. 非目标（明确不做什么）

1. **不改 Planner 核心逻辑**：Planner 仍然自由生成 subtask，不强制阶段流水线。
2. **不做图谱可视化**：ReconStore 查询页面为列表式，不做 NetworkX 图谱渲染。
3. **不做实时同步**：ReconStore 写入不阻塞主流程（同线程顺序写入，非异步 IO），不保证秒级实时查询。同一任务内后续 subtask 查询 ReconStore 时，已写入的数据立即可见。
4. **不做复杂权限控制**：Web UI 查询暂不做认证授权，假设为单用户本地使用。

---

## 10. 验收标准

| 验收项 | 标准 |
|--------|------|
| nmap_scan 结构化输出 | 执行后 `structured_findings` 包含 host/port/service 信息 |
| httpx_scan 结构化输出 | 执行后 `structured_findings` 包含 endpoint/tech/header 信息 |
| ReconStore 入库 | nmap/httpx 执行后，对应记录可在 SQLite 中查询到 |
| Web UI 查询 | 打开 `/recon` 页面，可按类型和 target 过滤查看结果 |
| Policy 注入 | 传入 policy 文档后，Planner 生成的 SQLi subtask 包含约束上下文 |
| 不影响现有功能 | 关闭 ReconStore/TestPolicy 后，Agent 行为与改造前完全一致 |
