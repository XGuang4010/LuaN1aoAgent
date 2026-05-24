# 服务管理
**运行环境**：venv环境

# LuaN1ao Agent 架构文档

## 项目概述

**LuaN1ao**（鸾鸟）是基于大语言模型的自主渗透测试智能体，采用 **P-E-R (Planner-Executor-Reflector)** 架构与因果图谱推理技术。

### 核心特性

- 🎯 **战略规划**：基于全局态势动态规划攻击路径
- 🔍 **证据驱动**：构建"证据-假设-验证"逻辑链
- 🔄 **持续进化**：从失败中学习，自主调整策略
- 🧠 **认知闭环**：规划-执行-反思完整循环

---

## 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                     用户目标 (User Goal)                         │
└──────────────────────────────────┬──────────────────────────────┘
                                   │
┌──────────────────────────────────▼──────────────────────────────┐
│              P-E-R 认知层 (Cognitive Layer)                     │
│  ┌──────────┐     ┌──────────┐     ┌──────────┐             │
│  │ Planner  │────▶│ Executor │────▶│Reflector │             │
│  └──────────┘     └──────────┘     └──────────┘             │
│       │                 │                 │                       │
│       └─────────────────┴─────────────────┘                   │
└──────────────────────────────────┬──────────────────────────────┘
                                   │
┌──────────────────────────────────▼──────────────────────────────┐
│                   核心引擎 (Core Engine)                        │
│  • GraphManager: 任务图谱(DAG)管理、状态跟踪、并行调度        │
│  • Database: SQLite 持久化层                                  │
│  • EventBroker: 组件间事件通信                                 │
└──────────────────────────────────┬──────────────────────────────┘
                                   │
┌──────────────────────────────────▼──────────────────────────────┐
│                能力支撑层 (Capability Layer)                     │
│  • RAG Knowledge Service: FAISS 向量检索                      │
│  • MCP Tool Server: http_request/shell_exec/python_exec 等     │
└─────────────────────────────────────────────────────────────────┘
```

---

## 核心模块

| 模块 | 文件 | 职责 |
|------|------|------|
| **Planner** | `core/planner.py` | 战略目标分解、动态重规划、并行调度 |
| **Executor** | `core/executor.py` | 工具调用、上下文压缩、假设持久化 |
| **Reflector** | `core/reflector.py` | 审计分析、失败归因、终止控制 |
| **GraphManager** | `core/graph_manager.py` | 任务图谱/DAG管理、因果图谱、置信度传播 |
| **ReconStore** | `core/recon_store.py` | 信息收集仓库，支持去重和查询 |
| **TestPolicy** | `core/test_policy.py` | 测试策略解析与约束 enforcement |
| **EventBroker** | `core/events.py` | 事件发布/订阅 |

### 因果图谱推理

```
Evidence ──▶ Hypothesis ──▶ Vulnerability ──▶ Exploit
          支持/置信度      验证            利用
```

**核心原则**：证据先行 → 置信度量化 → 可追溯性 → 防止幻觉

### Plan-on-Graph (PoG)

动态演进的 DAG 替代静态任务列表，支持拓扑自动排序和并行路径识别。

---

## 目录结构

```
LuaN1aoAgent/
├── agent.py      # 主控入口，P-E-R 循环
├── mcp.json      # MCP 工具配置
├── conf/         # 配置 (config.py, i18n.py)
├── core/         # 核心引擎
│   ├── prompts/  # 提示词模板 (en/zh)
│   └── database/ # SQLAlchemy 模型
├── llm/          # LLM 抽象层
├── rag/          # RAG 知识增强
├── tools/        # MCP 工具实现
├── web/          # Web 可视化 (FastAPI + SSE)
└── tests/        # 测试套件
```

---

## 配置 (`.env`)

```ini
LLM_API_KEY=sk-xxx
LLM_API_BASE_URL=https://api.openai.com/v1
LLM_DEFAULT_MODEL=gpt-4o
OUTPUT_MODE=default   # simple/default/debug
TOOLS_HOME=D:\Tools\PentestWorkspace
```

---

## 外部工具规范

第三方工具统一安装到 `TOOLS_HOME` 下，按 `工具名/工具名.exe` 约定放置。

解析优先级：单工具环境变量 > `TOOLS_HOME` 约定路径 > 报错

---

## 技术栈

Python 3.10+ · NetworkX · OpenAI API · FAISS · FastAPI+SSE · SQLite+SQLAlchemy · MCP · Vanilla JS

---

## 安全声明

⚠️ 仅供授权安全测试和教育目的。须取得系统所有者书面同意后在隔离环境中运行。

## 许可证

Apache License 2.0
