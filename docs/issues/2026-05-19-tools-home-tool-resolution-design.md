# TOOLS_HOME 工具解析设计

## 文档信息

| 字段 | 值 |
|------|-----|
| 标题 | TOOLS_HOME 工具解析设计 |
| 日期 | 2026-05-19 |
| 状态 | 已根据源码复核修订 |
| 范围 | 当前外部工具定位问题的最小修复 |

---

## 1. 问题背景

当前项目中的外部安全工具主要在以下两处直接通过命令名调用，或通过 `shutil.which()` 从 `PATH` 中解析：

- [`tools/mcp_service.py`](file:///d:/Projects/LuaN1aoAgent/tools/mcp_service.py)
- [`domain_scanner.py`](file:///d:/Projects/LuaN1aoAgent/domain_scanner.py)

这带来三个现实问题：

- 工具安装位置受系统 `PATH` 约束，不利于项目级隔离
- 同名命令容易冲突，例如项目需要的是 ProjectDiscovery `httpx`，但机器上可能先命中 Python `httpx.exe`
- 工具迁移、备份、复现都不够稳定

本次只解决当前问题，不扩大为完整的工具管理系统。

---

## 2. 目标

为项目增加一个项目级工具目录入口：

- `TOOLS_HOME=D:\Tools\PentestWorkspace`

并让当前项目中当前会直接调用外部命令的代码路径优先从该目录解析，而不是强依赖系统 `PATH`。

目标结果：

- 工具可以统一安装到 `D:\Tools\PentestWorkspace`
- 项目在当前纳入范围内优先使用该目录下的工具
- 若显式指定单工具路径，则优先级高于 `TOOLS_HOME`
- 若上述均未命中，再回退到现有 `PATH`

---

## 3. 纳入范围

本次纳入的外部工具固定为 6 个：

- `sqlmap`
- `dirsearch`
- `nuclei`
- `subfinder`
- `httpx`
- `searchsploit`

其中：

- `httpx` 明确指 **ProjectDiscovery httpx**
- 不接受 Python `httpx.exe` 替代

---

## 4. 不纳入范围

本次不处理以下内容：

- `requirements.txt` 中的 Python 依赖管理
- `mcp` / `fastmcp` / `httpx` Python 库的安装策略
- Web 服务、Agent 服务的启动方式重构
- 完整的工具注册中心
- 动态工具能力探测
- 下载器、自动更新器、版本锁定系统

说明：

- 本次目标不是“整个仓库所有未来外部命令都自动受控”，而是让**当前源码中已经存在的直接工具调用点**支持项目级环境变量导航。

---

## 5. 目录约定

默认使用如下工具目录布局：

- `D:\Tools\PentestWorkspace\sqlmap\sqlmap.exe`
- `D:\Tools\PentestWorkspace\dirsearch\dirsearch.exe`
- `D:\Tools\PentestWorkspace\nuclei\nuclei.exe`
- `D:\Tools\PentestWorkspace\subfinder\subfinder.exe`
- `D:\Tools\PentestWorkspace\httpx\httpx.exe`
- `D:\Tools\PentestWorkspace\searchsploit\searchsploit.exe`

说明：

- 第一版只约定 `.exe` 入口
- 如果某工具是脚本型封装，允许后续通过单工具环境变量覆盖

---

## 6. 环境变量设计

统一入口：

- `TOOLS_HOME`

单工具覆盖变量：

- `SQLMAP_PATH`
- `DIRSEARCH_PATH`
- `NUCLEI_PATH`
- `SUBFINDER_PATH`
- `PD_HTTPX_PATH`
- `SEARCHSPLOIT_PATH`

推荐 `.env` 示例：

```ini
TOOLS_HOME=D:\Tools\PentestWorkspace

# 可选覆盖
# SQLMAP_PATH=D:\Tools\PentestWorkspace\sqlmap\sqlmap.exe
# DIRSEARCH_PATH=D:\Tools\PentestWorkspace\dirsearch\dirsearch.exe
# NUCLEI_PATH=D:\Tools\PentestWorkspace\nuclei\nuclei.exe
# SUBFINDER_PATH=D:\Tools\PentestWorkspace\subfinder\subfinder.exe
# PD_HTTPX_PATH=D:\Tools\PentestWorkspace\httpx\httpx.exe
# SEARCHSPLOIT_PATH=D:\Tools\PentestWorkspace\searchsploit\searchsploit.exe
```

---

## 7. 解析顺序

运行时按以下顺序解析工具路径：

1. 单工具环境变量
2. `TOOLS_HOME` 下约定路径
3. `PATH`

这条规则适用于本次纳入的 6 个外部工具。

---

## 8. 代码改动边界

本次修改：

- [`tools/mcp_service.py`](file:///d:/Projects/LuaN1aoAgent/tools/mcp_service.py)
- [`domain_scanner.py`](file:///d:/Projects/LuaN1aoAgent/domain_scanner.py)

可选同步补充：

- [`conf/config.py`](file:///d:/Projects/LuaN1aoAgent/conf/config.py)
- [`.env.example`](file:///d:/Projects/LuaN1aoAgent/.env.example)

不会扩散到 Planner、Executor、Reflector、Web UI 等模块。

---

## 9. 设计方案

在 `tools/mcp_service.py` 中增加统一的工具解析函数，例如：

- `_resolve_external_tool(tool_name, env_var_name, tools_home_subpath, fallback_names=None)`

职责：

- 先读单工具环境变量
- 再读 `TOOLS_HOME`
- 最后再调用 `shutil.which()`
- 只返回“真实存在且可执行”的候选路径

然后把当前 6 个工具的调用入口统一改为该解析函数。

必须覆盖的调用点：

- `sqlmap_tool()`
- `_resolve_dirsearch_executable()` / `dirsearch_scan()`
- `nuclei_scan()`
- `nuclei_list_templates()`
- `subfinder_scan()`
- `httpx_probe()`
- `_search_exploitdb()`
- `view_exploit()`
- `domain_scanner.cmd_scan_subdomains()`

示意逻辑：

```python
def _resolve_external_tool(
    tool_name: str,
    env_var_name: str,
    tools_home_subpath: str,
    fallback_names: list[str] | None = None,
) -> str | None:
    explicit = os.getenv(env_var_name, "").strip()
    if explicit and os.path.exists(explicit):
        return explicit

    tools_home = os.getenv("TOOLS_HOME", "").strip()
    if tools_home:
        candidate = os.path.join(tools_home, tools_home_subpath)
        if os.path.exists(candidate):
            return candidate

    for name in [tool_name, *(fallback_names or [])]:
        resolved = shutil.which(name)
        if resolved:
            return resolved

    return None
```

调用方责任：

- 若返回 `None`，调用方应输出清晰错误，包含：
  - 使用了哪个环境变量
  - 查找了哪个 `TOOLS_HOME` 子路径
  - 是否尝试过 `PATH`
- 不应返回一个并不存在的伪路径再让下游黑盒失败。

---

## 10. 特殊规则

### 10.1 `httpx`

`httpx` 需要特殊处理：

- 环境变量名固定为 `PD_HTTPX_PATH`
- `TOOLS_HOME` 默认路径固定为 `httpx\httpx.exe`
- 不接受 Python `httpx` 作为项目默认探测工具

如果回退到 `PATH`，必须做一层最小校验：

- 执行 `httpx --help`
- 若输出明显为 Python HTTPX CLI，则视为不兼容

第一版规则固定为：

- `PD_HTTPX_PATH` 命中：直接使用
- `TOOLS_HOME\httpx\httpx.exe` 命中：直接使用
- `PATH` 命中：必须通过 help 文本校验为 ProjectDiscovery `httpx`
- 若校验失败：视为未找到兼容工具，并返回明确错误

### 10.2 `dirsearch`

`dirsearch` 当前已有 `_resolve_dirsearch_executable()`，本次不保留单独逻辑，应并入统一入口，避免出现两套解析规则。

---

## 11. 测试策略

采用最小测试驱动方式，只验证当前问题：

- 当设置单工具环境变量时，优先返回环境变量路径
- 当未设置单工具变量但设置了 `TOOLS_HOME` 时，返回 `TOOLS_HOME` 约定路径
- 当以上都未命中时，回退到 `shutil.which()`
- `dirsearch` 仍能正确解析
- `httpx` 使用 `PD_HTTPX_PATH`
- `httpx` 若只从 `PATH` 命中 Python HTTPX CLI，应判定为不兼容
- `create_subprocess_exec()` / `subprocess.run()` 接收到的是解析后的绝对路径，而不是原始命令名
- `domain_scanner.py` 的 `subfinder` / `httpx` 直接调用点也接入相同解析逻辑

测试文件建议新增：

- `tests/tools/test_mcp_service_tool_resolution.py`
- `tests/test_domain_scanner_tool_resolution.py`

---

## 12. 安装策略

本次工具安装目标目录固定为：

- `D:\Tools\PentestWorkspace`

安装完成后的目标文件：

- `D:\Tools\PentestWorkspace\sqlmap\sqlmap.exe`
- `D:\Tools\PentestWorkspace\dirsearch\dirsearch.exe`
- `D:\Tools\PentestWorkspace\nuclei\nuclei.exe`
- `D:\Tools\PentestWorkspace\subfinder\subfinder.exe`
- `D:\Tools\PentestWorkspace\httpx\httpx.exe`
- `D:\Tools\PentestWorkspace\searchsploit\searchsploit.exe`

若某工具在 Windows 原生环境下不便安装：

- 仍保留路径支持
- 但不在本次实现中扩展跨平台兼容系统

---

## 13. 验收标准

满足以下条件即视为完成：

- 设置 `TOOLS_HOME=D:\Tools\PentestWorkspace` 后，当前纳入范围内的工具调用点优先从该目录解析工具
- 单工具环境变量优先级高于 `TOOLS_HOME`
- 未配置时仍可回退到 `PATH`
- 当前 6 个工具的调用入口都接入统一解析逻辑
- `mcp_service.py` 与 `domain_scanner.py` 中现有直接工具调用点都不再绕过该解析逻辑
- `httpx` 的解析结果不允许误命中 Python `httpx.exe`

---

## 14. 风险

- `searchsploit` 在 Windows 下可能不具备理想可执行形态
- `httpx` 同名冲突若实现遗漏 help 校验，仍可能误命中 Python 版本
- 若 `TOOLS_HOME` 下文件名与实际安装产物不一致，需要依赖单工具环境变量覆盖

这些风险不阻塞本次最小修复，因为第一版已经提供显式路径覆盖能力。

---

## 15. 结论

本方案以最小修改满足以下目标：

- 保持现有工具调用接口基本不变
- 增加项目级工具目录能力
- 不强依赖系统 `PATH`
- 让当前源码中已存在的直接调用点真正受项目级环境变量控制
- 为后续工具集中管理预留扩展空间

下一步应基于本设计编写实现计划，并按 TDD 实施。
