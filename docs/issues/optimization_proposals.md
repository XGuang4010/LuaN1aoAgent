# LuaN1ao Agent 当前版本优化建议

---

## 文档信息

| 字段 | 值 |
|------|-----|
| 标题 | LuaN1ao Agent 当前版本优化建议 |
| 版本 | v1.2 |
| 创建日期 | 2026-05-19 |
| 作者 | 二次开发团队 |
| 状态 | 仅保留当前版本必须做项 |

---

## 目录

1. [修订原则](#修订原则)
2. [当前版本必须做项](#当前版本必须做项)
   - [1. 智能模型路由](#1-智能模型路由)
   - [2. 漏洞链分析增强](#2-漏洞链分析增强)
   - [3. 上下文增强 RAG 重排](#3-上下文增强-rag-重排)
   - [4. 失败模式沉淀与根因分析增强](#4-失败模式沉淀与根因分析增强)
   - [5. 并行发现智能共享](#5-并行发现智能共享)
3. [从当前版本移除的方向](#从当前版本移除的方向)
4. [优先级矩阵](#优先级矩阵)
5. [实施路线图](#实施路线图)

---

## 修订原则

本版文档只保留“当前版本必须做”的优化项，筛选标准如下：

- 与现有 P-E-R、DAG、因果图、Reflector 审核闭环兼容
- 能直接解决当前版本的结构性短板
- 不会引入新的平行机制或高耦合副作用
- 不依赖尚未完成的经验层、记忆层或重型建模体系

以下基线能力已存在，因此不作为“当前版本必须做”的理由：

- Prompt 模板系统已存在，见 [manager.py](file:///d:/Projects/LuaN1aoAgent/core/prompts/manager.py)
- 因果图置信传播与攻击路径分析已存在，见 [graph_manager.py](file:///d:/Projects/LuaN1aoAgent/core/graph_manager.py)
- 混合检索式 RAG 已存在，见 [rag_client.py](file:///d:/Projects/LuaN1aoAgent/rag/rag_client.py)
- 共享公告板最小实现已存在，见 [graph_manager.py](file:///d:/Projects/LuaN1aoAgent/core/graph_manager.py)
- L0-L5 失败归因规范已存在，见 [core/prompts/templates/zh/common/failure_attribution_levels.jinja2](file:///d:/Projects/LuaN1aoAgent/core/prompts/templates/zh/common/failure_attribution_levels.jinja2)

---

## 当前版本必须做项

### 1. 智能模型路由

**为什么必须做**

- 当前模型选择仍主要依赖静态配置
- 不同角色虽支持不同模型，但缺少运行时调度
- 这是低侵入、高收益、与当前架构冲突最小的优化项

**当前短板**

- `planner / executor / reflector` 缺少基于任务复杂度和输出稳定性的动态路由
- `summarizer / reflector_validator` 这类低风险角色仍未充分利用轻量模型

**建议范围**

- 仅做角色级与复杂度级路由
- 明确 JSON 稳定模型白名单
- 增加失败回退与 provider fallback

**涉及文件**

- [config.py](file:///d:/Projects/LuaN1aoAgent/conf/config.py)
- [llm_client.py](file:///d:/Projects/LuaN1aoAgent/llm/llm_client.py)

---

### 2. 漏洞链分析增强

**为什么必须做**

- 当前已具备攻击路径分析基础，但对多阶段漏洞链的表达仍不足
- 这是当前因果图谱最直接的能力放大器
- 不需要推翻现有实现，只需增强排序、约束和解释能力

**当前短板**

- 对多漏洞组合链的显式分析较弱
- 缺少前置条件冲突检查
- 缺少更明确的链路可执行性排序

**建议范围**

- 复用现有 `AttackGoal`、`joint_threat_score`、attack path 机制
- 增加链路约束验证
- 输出明确的组合链解释

**涉及文件**

- [graph_manager.py](file:///d:/Projects/LuaN1aoAgent/core/graph_manager.py)

---

### 3. 上下文增强 RAG 重排

**为什么必须做**

- 当前 RAG 已有混合检索，但还未显式利用因果图上下文进行重排
- 这是增强知识质量、且不会破坏现有 evidence-first 原则的优化项
- 相比语义缓存，它更符合现有架构职责边界

**当前短板**

- 检索结果尚未明显绑定当前因果图状态
- Planner 的 `retrieved_experience` 入口尚未真正打通

**建议范围**

- 只做 graph-aware rerank
- 不在当前版本引入漏洞知识图谱大工程
- 先补齐 Planner 的真实检索接入

**涉及文件**

- [rag_client.py](file:///d:/Projects/LuaN1aoAgent/rag/rag_client.py)
- [planner.py](file:///d:/Projects/LuaN1aoAgent/core/planner.py)

---

### 4. 失败模式沉淀与根因分析增强

**为什么必须做**

- 当前已有 L0-L5 归因规则，但缺少跨任务沉淀与复用
- Reflector 是现有架构中的关键审计点，这项增强直接强化认知闭环
- 该方向比“经验库”或“强化学习”更现实、更贴近现状

**当前短板**

- 缺少失败模式聚类
- 缺少 remediation 模板复用
- 历史反思摘要消费链路不完整

**建议范围**

- 统一反思上下文渲染入口
- 增加失败模式归档、聚类和修复建议复用
- 保持 Reflector 审核为唯一可信沉淀入口

**涉及文件**

- [reflector.py](file:///d:/Projects/LuaN1aoAgent/core/reflector.py)
- [manager.py](file:///d:/Projects/LuaN1aoAgent/core/prompts/manager.py)

---

### 5. 并行发现智能共享

**为什么必须做**

- 当前共享公告板已存在，但能力过于粗粒度
- 这是并行子任务价值能否真正释放的核心约束
- 改造边界明确，短期收益高

**当前短板**

- 仍是 append-only list
- 缺少优先级、TTL、简单去重
- 缺少共享消费策略优化

**建议范围**

- 第一阶段只做 `priority + TTL + type filter + 简单去重`
- 暂不在当前版本引入完整语义去重与复杂冲突仲裁

**涉及文件**

- [graph_manager.py](file:///d:/Projects/LuaN1aoAgent/core/graph_manager.py)

---

## 从当前版本移除的方向

以下方向不是“完全否定”，而是**不属于当前版本必须做项**，因此已从当前版本目标中移除：

| 方向 | 移除原因 |
|------|----------|
| 受控语义缓存 | 与 RAG、经验、DAG、因果图、公告板、Reflector 审核边界冲突过大，当前阶段不应接入主推理链 |
| 上下文压缩增强 | 有价值，但不是当前最核心瓶颈，可在后续迭代处理 |
| 提示词样例增强 | 属于效果优化，不是当前结构性短板 |
| 多模态扩展 | 价值存在，但不属于当前主线收敛问题 |
| 经验复用机制增强 | 与反思沉淀链路高度相关，应在失败模式沉淀完成后再推进 |
| 因果图谱推理规则增强 | 当前机制可用，短期不是核心瓶颈 |
| 漏洞知识图谱 | 工程量大，不适合当前版本 |
| 贝叶斯推理引擎 | 与现有溯因式框架冲突较大，且收益不确定 |
| 强化学习集成 | 当前完全不具备实施条件 |
| 全局 CoT 注入 | 与现有模板和结构化 schema 冲突，且收益不稳定 |

---

## 优先级矩阵

| 序号 | 优化项 | 实现难度 | 收益评估 | 优先级 |
|------|--------|---------|---------|--------|
| 1 | 智能模型路由 | 中 | 高 | **P0** |
| 2 | 漏洞链分析增强 | 中高 | 高 | **P0** |
| 3 | 并行发现智能共享 | 中 | 高 | **P0** |
| 4 | 上下文增强 RAG 重排 | 中 | 中高 | **P1** |
| 5 | 失败模式沉淀与根因分析增强 | 中 | 中高 | **P1** |

---

## 实施路线图

### 第一阶段（1-2 周）

**目标**：先补齐当前版本最关键的结构能力

| 任务 | 模块 | 时间估算 |
|------|------|---------|
| 实现智能模型路由 | LLM / 配置 | 3-4 天 |
| 升级共享公告板第一阶段能力 | 图谱模块 | 3 天 |
| 实现 graph-aware RAG 重排 | RAG / Planner | 3-4 天 |

### 第二阶段（2-3 周）

**目标**：增强漏洞链表达与失败闭环

| 任务 | 模块 | 时间估算 |
|------|------|---------|
| 漏洞链分析增强 | 图谱模块 | 5-7 天 |
| 失败模式沉淀与根因分析增强 | Reflector | 4-5 天 |

---

**文档结束**
