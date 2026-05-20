# 项目级本地工具环境变量统一设计

## 文档信息

| 字段 | 值 |
|------|-----|
| 标题 | 项目级本地工具环境变量统一设计 |
| 日期 | 2026-05-20 |
| 状态 | 已实现，待验收 |
| 范围 | 工具路径解析环境来源收口 |

---

## 1. 背景

当前项目已经完成工具路径解析环境来源收口，规则已经统一为只支持项目根目录 `.env`。

在收口之前，项目曾存在以下问题：

- `tools/mcp_service.py` 与 `domain_scanner.py` 的工具环境来源不完全一致
- 现有实现一度保留了对系统环境变量和 `PATH` 的回退能力
- 项目本地 `.env` 与进程环境注入混用，导致运行行为不可预测

这会带来两个问题：

- 行为不一致：不同入口对项目本地 `.env` 的依赖程度不同
- 运维不受控：一旦回退到系统环境变量或 `PATH`，就会污染系统环境，且容易误命中错误工具

本次工作的目标是只解决这个问题本身，不扩展为完整配置系统重构。

---

## 2. 目标

统一项目内工具路径解析规则，并以当前实现为准：

- 只支持**项目级本地 `.env`**
- 拒绝依赖系统环境变量
- 拒绝依赖 `PATH` 兜底
- `mcp_service.py` 与 `domain_scanner.py` 行为一致

目标结果：

- 只要项目根目录 `.env` 配好，工具即可被稳定解析
- 若 `.env` 缺失或未配置，工具调用直接失败并给出明确错误
- 不再要求用户向系统环境变量写入 `TOOLS_HOME` 或单工具路径

---

## 3. 范围

### 本次纳入

- `tools/mcp_service.py`
- `domain_scanner.py`
- 项目级工具环境变量读取入口
- `.env.example`
- 根目录说明文档

### 本次不纳入

- LLM 配置来源重构
- Web 服务启动器改造
- 全项目所有 `os.getenv()` 统一治理
- 自动安装器、版本管理器、工具下载器

---

## 4. 项目级环境变量规则

### 主变量

```ini
TOOLS_HOME=D:\Tools\PentestWorkspace
```

### 单工具变量

```ini
SQLMAP_PATH=
DIRSEARCH_PATH=
NUCLEI_PATH=
SUBFINDER_PATH=
PD_HTTPX_PATH=
SEARCHSPLOIT_PATH=
```

### 生效边界

- 以上变量只在项目根目录 `.env` 中生效
- 将这些变量配置到系统环境变量中，不属于支持范围
- 将工具放入系统 `PATH` 中，不属于支持范围

### 目录约定

```text
D:\Tools\PentestWorkspace\sqlmap\sqlmap.exe
D:\Tools\PentestWorkspace\dirsearch\dirsearch.exe
D:\Tools\PentestWorkspace\nuclei\nuclei.exe
D:\Tools\PentestWorkspace\subfinder\subfinder.exe
D:\Tools\PentestWorkspace\httpx\httpx.exe
D:\Tools\PentestWorkspace\searchsploit\searchsploit.exe
```

---

## 5. 设计原则

- **项目级优先**：只从项目根目录 `.env` 读取工具配置
- **拒绝系统兜底**：不依赖系统环境变量，不依赖 `PATH`
- **显式失败**：缺配置时直接报错，不做模糊猜测
- **最小改动**：只收口工具路径来源，不顺手改其它配置模块
- **统一行为**：`mcp_service.py` 与 `domain_scanner.py` 使用同一套解析规则

---

## 6. 最终采用方案

当前实现采用统一的项目级本地环境加载入口：

- 新增一个小型工具环境辅助模块，负责：
  - 定位项目根目录 `.env`
  - 显式加载 `.env`
  - 只从项目本地配置中获取工具路径
- `mcp_service.py` 和 `domain_scanner.py` 都复用这个入口

落地结果：

- 规则单一
- 行为可预测
- 不依赖系统配置
- 不再允许系统环境变量或 `PATH` 参与工具解析

---

## 7. 统一加载逻辑

当前统一的项目级工具环境读取入口为：

- [tool_env.py](file:///d:/Projects/LuaN1aoAgent/tools/tool_env.py)

职责：

- 定位项目根目录
- 显式读取项目根目录 `.env`
- 读取 `TOOLS_HOME` 与单工具变量
- 只返回项目级配置结果

当前接口：

```python
def load_project_tool_env(
    dotenv_path: str | Path | None = None,
) -> dict[str, str]:
    ...


def resolve_project_tool(
    tool_name: str,
    env_var_name: str,
    tools_home_subpath: str,
) -> str | None:
    ...
```

核心行为：

1. 显式读取 `project_root/.env`
2. 优先读单工具变量
3. 再读 `TOOLS_HOME + 约定相对路径`
4. 不再调用 `shutil.which()`，也不读取系统环境变量
5. 找不到则返回 `None`

---

## 8. 失败策略

当工具未解析成功时：

- 不回退系统环境变量
- 不回退 `PATH`
- 直接报错

错误信息需要明确包含：

- 当前工具名
- 对应单工具变量名
- 查找的 `TOOLS_HOME` 子路径
- 提示“请在项目根目录 `.env` 中配置”

示例错误：

```json
{
  "success": false,
  "error_type": "TOOL_MISSING",
  "error": "nuclei not configured. Checked NUCLEI_PATH and TOOLS_HOME\\nuclei\\nuclei.exe from project .env only."
}
```

---

## 9. `httpx` 特殊规则

`httpx` 仍然需要区分 ProjectDiscovery `httpx` 与 Python `httpx` CLI。

在本方案下：

- 优先要求 `.env` 中显式指定 `PD_HTTPX_PATH`
- 若未指定，则尝试 `TOOLS_HOME\httpx\httpx.exe`
- 不再从 `PATH` 查找，也不接受系统环境变量注入的回退行为

因此第一版中：

- 可以保留兼容校验函数
- 但它只作为防御性检查
- 不再作为 PATH 回退的一部分

---

## 10. 代码改动边界

本次修改：

- [`tools/mcp_service.py`](file:///d:/Projects/LuaN1aoAgent/tools/mcp_service.py)
- [`domain_scanner.py`](file:///d:/Projects/LuaN1aoAgent/domain_scanner.py)
- 新增 `tools/tool_env.py`
- [`.env.example`](file:///d:/Projects/LuaN1aoAgent/.env.example)
- 根目录工具文档

不会扩散到：

- Planner
- Executor
- Reflector
- Web UI
- LLM 配置系统

---

## 11. 测试策略

测试只验证当前问题：

- 项目本地 `.env` 配置存在时，`mcp_service.py` 能解析工具
- 项目本地 `.env` 配置存在时，`domain_scanner.py` 能解析工具
- 缺少项目 `.env` 配置时，工具解析直接失败
- 不再触发 `shutil.which()` 或 `PATH` 兜底
- 系统环境变量即使存在，也不属于支持行为
- `httpx` 仍只接受 ProjectDiscovery 版本

建议测试文件：

- `tests/tools/test_tool_env.py`
- `tests/tools/test_mcp_service_tool_resolution.py`
- `tests/test_domain_scanner_tool_resolution.py`

---

## 12. 验收标准

满足以下条件即视为完成：

- `mcp_service.py` 与 `domain_scanner.py` 都只依赖项目本地 `.env`
- 工具解析不再依赖系统环境变量
- 工具解析不再依赖 `PATH`
- `.env` 配置完整时，当前 6 个工具可被正确解析
- `.env` 缺失或未配置时，错误信息明确可读

---

## 13. 风险

- 若用户忘记配置 `.env`，工具会全部直接失败
  - 这是本次方案的预期行为，不是副作用
- `searchsploit` 当前仍缺原生 Windows 二进制
  - 本次只统一环境来源，不扩展安装策略
- 若将来新增新的工具调用入口，必须复用统一读取模块，否则会再次出现行为分叉

---

## 14. 结论

本方案以最小范围统一了工具环境来源：

- 只支持项目级本地 `.env`
- 明确拒绝系统环境变量
- 明确拒绝 `PATH` 兜底
- 保证 `mcp_service.py` 与 `domain_scanner.py` 行为一致

文档、实现与测试都必须围绕这条规则保持一致，不再保留任何“系统环境变量也可用”或“PATH 可兜底”的表述。
