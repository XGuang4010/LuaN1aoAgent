# Dirsearch Scan Cross-Platform Hardening Design

## 背景

当前 `dirsearch_scan` MCP 工具在真实任务执行中出现了工具级失败，直接导致执行节点 `subtask_1_step_dirscan_api` 失败。问题并非目标站点返回业务异常，而是工具层在当前运行环境下不稳健：

- `dirsearch` 可执行文件存在，但运行时缺少 `pkg_resources`
- Planner 传入的 `-w /usr/share/wordlists/dirb/common.txt` 为 Linux 词典路径，在 Windows 环境下不存在
- 工具内部通过 shell 字符串拼接命令，跨平台参数解析和错误诊断都不够稳定
- 上层 Agent 最终只收到模糊的 `Error executing tool:`，不利于 Reflector 进行准确归因

本次工作目标是以“稳健包装层”的方式修复 `dirsearch_scan`，保持上层 MCP 接口不变，同时提升跨平台可用性、错误可解释性和可测试性。

## 目标

- 保持 `dirsearch_scan(url, extensions, extra_args)` 的接口和返回 JSON 结构兼容
- 在 Windows/Linux 环境下更稳健地执行 `dirsearch`
- 对缺失依赖、无效词典路径、不兼容参数等场景给出明确错误类型和修复建议
- 避免因 shell 字符串拼接导致的参数转义和平台差异问题
- 为该工具补充最小但有效的自动化测试

## 非目标

- 不改动 Planner / Executor 的提示词和任务方法学
- 不重写为纯 Python 自研目录扫描器
- 不扩展到其他安全工具的统一重构
- 不修改任务图谱或 Web 展示逻辑

## 范围

本次仅修改以下区域：

- `tools/mcp_service.py`
- 新增 `tests/tools/test_mcp_service_dirsearch.py`
- 如有必要，补充与 `dirsearch` 运行依赖相关的依赖声明或说明

## 已知根因

### 1. 运行依赖缺失

当前环境中 `dirsearch.exe` 可以被发现，但执行时实际报错：

```text
ModuleNotFoundError: No module named 'pkg_resources'
```

这说明工具不属于“未安装”，而是“安装存在但运行时依赖不完整”。

### 2. 词典路径是 Linux 固定路径

Planner 生成的参数中包含：

```text
-w /usr/share/wordlists/dirb/common.txt
```

该路径在当前 Windows 环境不存在，会进一步导致执行失败或不稳定行为。

### 3. 当前实现直接拼接 shell 命令

现有实现使用：

```python
cmd = f"dirsearch -u {url} -e {extensions} -q"
process = await asyncio.create_subprocess_shell(cmd, ...)
```

这种方式存在以下问题：

- Windows 与 POSIX shell 语义不同
- 参数中一旦出现空格、引号、特殊字符，行为不可控
- 词典路径、URL、额外参数都容易受 shell 解析影响
- 不利于做单元测试和错误分类

## 方案选择

采用“稳健包装层”方案：

- 保持 MCP 工具名与外部调用方式不变
- 在工具内部增加参数规范化、环境探测、错误分类和平台兼容
- 将原本的黑盒 shell 执行改为显式参数列表执行

这是最符合当前项目边界的修复方式：既不破坏 Agent 上层逻辑，也能真正解决当前跨平台问题。

## 设计原则

- **兼容优先**：保持工具接口不变，尽量不影响上层 Agent
- **跨平台优先**：避免依赖 Linux 路径和 shell 特性
- **少即是多**：只增加最小必要的探测与归类，不做无关架构重写
- **错误可解释**：失败时必须给上层清晰结论，而不是空报错

## 详细设计

### 1. 拆分为小型辅助函数

在 `tools/mcp_service.py` 内部，为 `dirsearch_scan` 增加若干小型私有辅助函数，职责清晰、便于测试：

- `_normalize_dirsearch_args(...)`
  - 解析 `extra_args`
  - 处理不兼容参数
  - 识别并处理词典路径参数
- `_resolve_dirsearch_executable()`
  - 定位 `dirsearch` 可执行文件
  - 在找不到时返回明确错误
- `_classify_dirsearch_failure(output: str, return_code: int)`
  - 将 stderr/stdout 中的错误分类为结构化错误类型

这样可以把“参数清洗”“可执行文件发现”“失败原因解释”从主流程中分离出来。

### 2. 从 shell 字符串改为显式参数执行

当前：

```python
create_subprocess_shell("dirsearch ...")
```

改为：

```python
create_subprocess_exec(executable, *args)
```

收益：

- 不再依赖 shell 解析
- 跨平台行为更稳定
- 参数中有空格、URL、文件路径时更安全
- 更容易验证最终命令参数

### 3. 增强 `extra_args` 解析

`extra_args` 目前直接 `split()`，这对引号和路径并不稳妥。新设计使用更稳健的参数拆分方式，并执行以下规范化：

- 过滤已知不兼容参数
- 允许保留兼容参数
- 对 `-w` / `--wordlist` 参数做专门处理
- 记录被移除或替换的参数 warning

### 4. 词典路径跨平台处理

对 `-w` / `--wordlist` 参数进行显式识别：

- 如果路径存在：原样保留
- 如果路径不存在：
  - 不直接让工具黑盒失败
  - 记录 warning
  - 将该参数移除，继续执行默认扫描

这样做的原因是，目录扫描工具通常自带默认词典；当前最重要的是避免因 Linux 固定路径在 Windows 下导致整个工具不可用。

如后续需要，也可以在不改变接口的前提下加入默认候选词典路径列表，但本次不强行扩展。

### 5. 运行时健康检查与错误分类

在运行 `dirsearch` 后，对输出进行更细粒度分类：

- `MISSING_TOOL`
  - 找不到可执行文件
- `MISSING_RUNTIME_DEPENDENCY`
  - 命中 `No module named 'pkg_resources'`
  - 或类似运行依赖错误
- `MISSING_WORDLIST`
  - 指定词典文件不存在且工具明确报错
- `INVALID_ARGS`
  - 参数不兼容、参数格式错误
- `RUNTIME`
  - 其他运行错误

并继续返回统一的 JSON：

```json
{
  "success": false,
  "output": "...",
  "error_type": "...",
  "message": "...",
  "fix_suggestion": "..."
}
```

### 6. 输出 warning 信息

当发生以下场景时，应该把处理过的 warning 附加到返回值或输出中，供上层 LLM 理解：

- 移除了不存在的词典路径
- 替换了不兼容参数
- 找到了 `dirsearch` 可执行文件，但运行依赖缺失

目标不是让返回结构膨胀，而是让上层 Agent 能基于这些线索做策略回退。

### 7. 自动化测试

新增 `tests/tools/test_mcp_service_dirsearch.py`，重点覆盖辅助函数与失败分类，不依赖真实网络扫描。

至少包含：

- `dirsearch` 不存在时的分类
- 输出包含 `No module named 'pkg_resources'` 时归类为 `MISSING_RUNTIME_DEPENDENCY`
- Windows 下传入 `/usr/share/wordlists/dirb/common.txt` 时被安全移除
- 参数构造结果正确，不再依赖 shell 字符串

测试策略以“高价值、低耦合”为主，不去写需要真实安装 `dirsearch` 的脆弱集成测试。

## 风险与缓解

### 风险 1：不同版本 `dirsearch` 参数行为不同

缓解：

- 保留当前的不兼容参数过滤机制
- 将参数规范化集中到辅助函数
- 对未知参数仍透传，但失败时提供明确错误分类

### 风险 2：移除不存在词典路径后扫描结果变弱

缓解：

- 当前首要目标是“可运行且可归因”
- 即使使用默认词典，效果也优于直接工具崩溃
- 若后续需要更强扫描质量，可再单独补默认词典策略

### 风险 3：工具层测试引入对系统环境的耦合

缓解：

- 以辅助函数和输出分类测试为主
- 使用 mock 替代真实进程调用
- 不依赖本机是否真的安装 `dirsearch`

## 实施顺序

1. 为 `dirsearch_scan` 当前失败模式补回归测试
2. 拆分辅助函数并重构命令构造
3. 加入词典路径规范化与运行依赖分类
4. 更新错误返回结构与修复建议
5. 运行新增测试与现有关键测试
6. 用当前 Windows 环境做一次真实回归验证

## 验收标准

- `dirsearch_scan` 在 Windows 环境下不再因 `/usr/share/...` 词典路径直接黑盒失败
- `pkg_resources` 缺失时返回 `MISSING_RUNTIME_DEPENDENCY`
- 工具构造命令时不再使用 shell 字符串拼接
- 新增测试通过
- 现有 Web 与核心测试不因本次修改失败

