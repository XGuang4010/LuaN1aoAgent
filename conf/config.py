# conf/config.py
# 配置文件：存放API密钥、模型参数等核心配置项
# 注意：请勿将真实API密钥提交到版本控制系统

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# 从.env文件加载环境变量
load_dotenv()

# Python 3.11+ 内置 tomllib，无需额外依赖
if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None  # 无 TOML 支持时回退到默认值


def _load_scope_toml() -> dict:
    """从 conf/scope_defaults.toml 加载默认 scope 配置。"""
    defaults = {}
    if tomllib is not None:
        toml_path = Path(__file__).parent / "scope_defaults.toml"
        if toml_path.is_file():
            try:
                with open(toml_path, "rb") as f:
                    defaults = tomllib.load(f)
            except Exception:
                pass  # 解析失败时使用下方硬编码回退值
    return defaults

# ============================================================================
# 核心场景配置 (Scenario Configuration)
# ============================================================================

# 运行场景模式
# "general": 通用模式，适用于实战渗透、内网渗透等复杂环境（默认）
# "ctf": CTF模式，针对CTF夺旗赛优化（会禁用部分大规模扫描工具，启用特定Prompt优化）
SCENARIO_MODE = os.getenv("SCENARIO_MODE", "general").lower()

# ============================================================================
# 输出配置 (Output Configuration)
# ============================================================================

# 控制台输出模式: "simple", "default", "debug"
# "simple": 精简输出,只展示核心信息
# "default": 标准输出,提供正常调试所需信息
# "debug": 详细输出,等同于 --verbose,提供所有调试信息
OUTPUT_MODE = os.getenv("OUTPUT_MODE", "default").lower()

# 提示词语言 / Prompt Language: "zh" (中文), "en" (English)
PROMPT_LANGUAGE = os.getenv("PROMPT_LANGUAGE", "zh").lower()

# ============================================================================
# LLM API 配置
# ============================================================================

# 从环境变量读取配置，如果环境变量不存在则使用默认值
LLM_API_BASE_URL = os.getenv("LLM_API_BASE_URL", "https://api.openai.com/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY")  # 请在.env文件中设置
LLM_FALLBACK_API_KEY = os.getenv("LLM_FALLBACK_API_KEY")  # 备选API密钥，用于处理429错误


# ============================================================================
# LLM模型配置
# ============================================================================

# 为不同角色/模块定义语言模型
# 核心思想：允许为每个关键模块（规划、执行、反思）使用不同的模型，以平衡成本、速度和能力
# 例如，Planner可以使用最强大的模型来确保计划质量，而Executor可以使用速度更快、成本更低的模型
LLM_MODELS = {
    "default": os.getenv("LLM_DEFAULT_MODEL", "gpt-4o"),
    "planner": os.getenv("LLM_PLANNER_MODEL", "gpt-4o"),
    "executor": os.getenv("LLM_EXECUTOR_MODEL", "gpt-4o"),
    "reflector": os.getenv("LLM_REFLECTOR_MODEL", "gpt-4o"),
    "expert_analysis": os.getenv("LLM_EXPERT_MODEL", "gpt-4o"),
    "summarizer": os.getenv("LLM_SUMMARIZER_MODEL", os.getenv("LLM_DEFAULT_MODEL", "gpt-4o")),
    "reflector_validator": os.getenv("LLM_REFLECTOR_VALIDATOR_MODEL", os.getenv("LLM_REFLECTOR_MODEL", "gpt-4o")),
    "planner_crisis_expert": os.getenv("LLM_PLANNER_CRISIS_EXPERT_MODEL", os.getenv("LLM_PLANNER_MODEL", "gpt-4o")),
}

# 为不同角色设置独立的LLM温度参数
# 较高的温度(如0.7)增加输出多样性，适合创造性任务
# 较低的温度(如0.2)增加输出确定性，适合需要精确性的任务
LLM_TEMPERATURES = {
    "default": 0.3,
    "planner": 0.5,  # 规划器需要一定创造性来生成多样化策略
    "executor": 0.3,  # 执行器需要稳定可靠的工具调用
    "reflector": 0.2,  # 反思器需要精确的分析和判断
    "expert_analysis": 0.7,  # 专家分析需要更多创造性思维
    "summarizer": 0.2,  # 摘要需要稳定、简洁输出
    "reflector_validator": 0.1,  # 二值判定需要更高确定性
    "planner_crisis_expert": 0.4,  # 危机重规划需平衡稳定性与探索性
}

# ============================================================================
# LLM高级配置
# ============================================================================

# 是否启用OpenAI兼容接口的extra_body字段，用于传递供应商自定义参数（如思考模式thinking）
# 设置为True后，如果下方LLM_THINKING为非off，将在请求payload中注入{"extra_body": {"thinking": "hidden|visible"}}
LLM_EXTRA_BODY_ENABLED = os.getenv("LLM_EXTRA_BODY_ENABLED", "false").lower() == "true"

# 为不同角色配置是否开启“思考模式”（extra_body.thinking）
# 取值说明：
# - off: 不启用思考模式（不注入extra_body）
# - hidden: 启用但不在最终输出中显示思考过程（由具体供应商决定具体行为）
# - visible: 启用并在最终输出中返回思考过程（例如返回reasoning_content或思维链）
# 注意：该参数仅在OpenAI兼容API且供应商支持extra_body.thinking时生效
LLM_THINKING = {
    "default": os.getenv("LLM_DEFAULT_THINKING", "off"),
    "planner": os.getenv("LLM_PLANNER_THINKING", os.getenv("LLM_DEFAULT_THINKING", "off")),
    "executor": os.getenv("LLM_EXECUTOR_THINKING", os.getenv("LLM_DEFAULT_THINKING", "off")),
    "reflector": os.getenv("LLM_REFLECTOR_THINKING", os.getenv("LLM_DEFAULT_THINKING", "off")),
    "expert_analysis": os.getenv("LLM_EXPERT_THINKING", os.getenv("LLM_DEFAULT_THINKING", "off")),
    "summarizer": os.getenv("LLM_SUMMARIZER_THINKING", os.getenv("LLM_DEFAULT_THINKING", "off")),
    "reflector_validator": os.getenv("LLM_REFLECTOR_VALIDATOR_THINKING", os.getenv("LLM_DEFAULT_THINKING", "off")),
    "planner_crisis_expert": os.getenv(
        "LLM_PLANNER_CRISIS_EXPERT_THINKING", os.getenv("LLM_DEFAULT_THINKING", "off")
    ),
}

# ============================================================================
# LLM提供商配置
# ============================================================================

# LLM Provider: "openai"或"anthropic"
# 支持使用不同的LLM提供商，可根据需求切换
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai")

# Anthropic API配置（如使用Claude模型）
ANTHROPIC_API_BASE_URL = os.getenv("ANTHROPIC_API_BASE_URL", "https://api.anthropic.com/v1/messages")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", LLM_API_KEY)  # 默认使用主API密钥
ANTHROPIC_FALLBACK_API_KEY = os.getenv("ANTHROPIC_FALLBACK_API_KEY", LLM_FALLBACK_API_KEY)
ANTHROPIC_VERSION = os.getenv("ANTHROPIC_VERSION", "2023-06-01")

# Anthropic模型映射
ANTHROPIC_MODELS = {
    "default": os.getenv("ANTHROPIC_DEFAULT_MODEL", "claude-3-5-sonnet-20240620"),
    "planner": os.getenv("ANTHROPIC_PLANNER_MODEL", "claude-3-5-sonnet-20240620"),
    "executor": os.getenv("ANTHROPIC_EXECUTOR_MODEL", "claude-3-5-sonnet-20240620"),
    "reflector": os.getenv("ANTHROPIC_REFLECTOR_MODEL", "claude-3-5-sonnet-20240620"),
    "expert_analysis": os.getenv("ANTHROPIC_EXPERT_MODEL", "claude-3-5-sonnet-20240620"),
    "summarizer": os.getenv("ANTHROPIC_SUMMARIZER_MODEL", os.getenv("ANTHROPIC_DEFAULT_MODEL", "claude-3-5-sonnet-20240620")),
    "reflector_validator": os.getenv(
        "ANTHROPIC_REFLECTOR_VALIDATOR_MODEL",
        os.getenv("ANTHROPIC_REFLECTOR_MODEL", "claude-3-5-sonnet-20240620"),
    ),
    "planner_crisis_expert": os.getenv(
        "ANTHROPIC_PLANNER_CRISIS_EXPERT_MODEL",
        os.getenv("ANTHROPIC_PLANNER_MODEL", "claude-3-5-sonnet-20240620"),
    ),
}

# ============================================================================
# 执行器行为配置
# ============================================================================

# 执行器最大步数限制
EXECUTOR_MAX_STEPS = int(os.getenv("EXECUTOR_MAX_STEPS", "8"))

# 消息历史压缩阈值
EXECUTOR_MESSAGE_COMPRESS_THRESHOLD = int(os.getenv("EXECUTOR_MESSAGE_COMPRESS_THRESHOLD", "12"))

# Token数量压缩阈值
EXECUTOR_TOKEN_COMPRESS_THRESHOLD = int(os.getenv("EXECUTOR_TOKEN_COMPRESS_THRESHOLD", "80000"))

# 无新产出物的耐心值（连续多少步无产出则终止）
# 必须小于 EXECUTOR_MAX_STEPS，否则该机制永远不会触发
EXECUTOR_NO_ARTIFACTS_PATIENCE = int(os.getenv("EXECUTOR_NO_ARTIFACTS_PATIENCE", "4"))

# 失败阈值（连续失败多少次触发策略切换）
EXECUTOR_FAILURE_THRESHOLD = int(os.getenv("EXECUTOR_FAILURE_THRESHOLD", "3"))

# 上下文压缩时保留的最近消息数
EXECUTOR_RECENT_MESSAGES_KEEP = int(os.getenv("EXECUTOR_RECENT_MESSAGES_KEEP", "6"))

# 最小压缩消息阈值
EXECUTOR_MIN_COMPRESS_MESSAGES = int(os.getenv("EXECUTOR_MIN_COMPRESS_MESSAGES", "5"))

# 执行轮次压缩间隔
EXECUTOR_COMPRESS_INTERVAL = int(os.getenv("EXECUTOR_COMPRESS_INTERVAL", "5"))

# 执行轮次压缩时的消息数阈值
EXECUTOR_COMPRESS_INTERVAL_MSG_THRESHOLD = int(os.getenv("EXECUTOR_COMPRESS_INTERVAL_MSG_THRESHOLD", "8"))

# 工具调用超时时间（秒）
EXECUTOR_TOOL_TIMEOUT = int(os.getenv("EXECUTOR_TOOL_TIMEOUT", "120"))

# 各工具独立超时映射（秒）。未列出的工具使用 EXECUTOR_TOOL_TIMEOUT 默认值。
# 重型扫描工具需要更长超时；轻量思考/检索工具应快速返回。
TOOL_TIMEOUTS: dict = {
    # 重型扫描工具
    "sqlmap_tool":       int(os.getenv("TOOL_TIMEOUT_SQLMAP",    "600")),
    "nuclei_scan":       int(os.getenv("TOOL_TIMEOUT_NUCLEI",    "300")),
    "dirsearch_scan":    int(os.getenv("TOOL_TIMEOUT_DIRSEARCH", "300")),
    "concurrency_test":  int(os.getenv("TOOL_TIMEOUT_CONCURRENCY", "180")),
    # 标准工具
    "http_request":      int(os.getenv("TOOL_TIMEOUT_HTTP",       "60")),
    "shell_exec":        int(os.getenv("TOOL_TIMEOUT_SHELL",      "120")),
    "python_exec":       int(os.getenv("TOOL_TIMEOUT_PYTHON",     "300")),
    "web_search":        int(os.getenv("TOOL_TIMEOUT_WEB_SEARCH", "30")),
    "search_exploit":    int(os.getenv("TOOL_TIMEOUT_SEARCH_EXPLOIT", "30")),
    # 轻量工具
    "think":                  int(os.getenv("TOOL_TIMEOUT_THINK",        "30")),
    "formulate_hypotheses":   int(os.getenv("TOOL_TIMEOUT_HYPOTHESES",   "30")),
    "reflect_on_failure":     int(os.getenv("TOOL_TIMEOUT_REFLECT",      "30")),
    "expert_analysis":        int(os.getenv("TOOL_TIMEOUT_EXPERT",       "60")),
    "retrieve_knowledge":     int(os.getenv("TOOL_TIMEOUT_RETRIEVE",     "15")),
    "distill_knowledge":      int(os.getenv("TOOL_TIMEOUT_DISTILL",      "20")),
}

# 执行器观察结果的最大长度（字符），超过此长度将被截断
EXECUTOR_MAX_OUTPUT_LENGTH = int(os.getenv("EXECUTOR_MAX_OUTPUT_LENGTH", "50000"))

# 执行器观察结果的 DB 存储最大长度（字符），超过此长度时在 DB 层截断
EXECUTOR_DB_OUTPUT_LENGTH = int(os.getenv("EXECUTOR_DB_OUTPUT_LENGTH", "200000"))

# P-E-R 全局循环最大次数（防止无限循环）
GLOBAL_MAX_CYCLES = int(os.getenv("GLOBAL_MAX_CYCLES", "50"))

# 全局最大 Token 消耗限制（安全熔断器）
GLOBAL_MAX_TOKEN_USAGE = int(os.getenv("GLOBAL_MAX_TOKEN_USAGE", "5000000"))

# ============================================================================
# 上下文管理配置
# ============================================================================

# 规划历史保留窗口大小
PLANNER_HISTORY_WINDOW = int(os.getenv("PLANNER_HISTORY_WINDOW", "15"))

# 反思日志保留窗口大小
REFLECTOR_HISTORY_WINDOW = int(os.getenv("REFLECTOR_HISTORY_WINDOW", "15"))

# ============================================================================
# Ablation Configuration
# ============================================================================

# Execution mode
# "default": Standard P-E-R mode
# "linear": Linear mode (No Task Graph), disable dynamic branching
# "react": Pure ReAct mode (Executor Only), disable Planner/Reflector
EXECUTION_MODE = os.getenv("EXECUTION_MODE", "default").lower()

# Whether to disable causal graph
# "true": Disable Reflector's causal updates and Planner's causal reasoning
# "false": Default, use dual-graph
NO_CAUSAL_GRAPH = os.getenv("NO_CAUSAL_GRAPH", "false").lower() == "true"

# ============================================================================
# Web 服务配置
# ============================================================================

# Web UI 服务主机地址
WEB_HOST = os.getenv("WEB_HOST", "127.0.0.1")

# Web UI 服务端口
WEB_PORT = int(os.getenv("WEB_PORT", "8088"))

# ============================================================================
# 知识服务配置
# ============================================================================

# 知识服务端口
KNOWLEDGE_SERVICE_PORT = int(os.getenv("KNOWLEDGE_SERVICE_PORT", "8081"))

# 知识服务 Host
KNOWLEDGE_SERVICE_HOST = os.getenv("KNOWLEDGE_SERVICE_HOST", "127.0.0.1")

# 知识服务 URL
KNOWLEDGE_SERVICE_URL = os.getenv("KNOWLEDGE_SERVICE_URL", f"http://{KNOWLEDGE_SERVICE_HOST}:{KNOWLEDGE_SERVICE_PORT}")

# ============================================================================
# 人工协同 (HITL) 配置
# ============================================================================

# 是否开启人工介入模式
# 开启后，Agent在生成规划后会暂停，等待Web UI或CLI的人工审批
HUMAN_IN_THE_LOOP = os.getenv("HUMAN_IN_THE_LOOP", "false").lower() == "true"

# ============================================================================
# 作用域配置 (Scope Configuration)
# ============================================================================
# 加载顺序: scope_defaults.toml (底层默认值) → .env 环境变量 (覆盖) → 任务级配置 (最高优先级)
#
# 每个字段对应一个同名环境变量，使用 SCOPE_ 前缀 + 大写下划线命名:
#   blocked_targets        → SCOPE_BLOCKED_TARGETS (逗号分隔字符串)
#   allowed_ports          → SCOPE_ALLOWED_PORTS (逗号分隔数字)
#   allowed_targets        → SCOPE_ALLOWED_TARGETS
#   disabled_tools         → SCOPE_DISABLED_TOOLS
#   disable_shell_exec     → SCOPE_DISABLE_SHELL_EXEC ("true"/"false")
#   disable_python_exec    → SCOPE_DISABLE_PYTHON_EXEC ("true"/"false")
#   block_private_network  → SCOPE_BLOCK_PRIVATE_NETWORK ("true"/"false")
#   block_dns_rebinding    → SCOPE_BLOCK_DNS_REBINDING ("true"/"false")
#   enforce_tls_verification → SCOPE_ENFORCE_TLS_VERIFICATION ("true"/"false")
#   max_response_size      → SCOPE_MAX_RESPONSE_SIZE
#   rate_limit_requests_per_sec → SCOPE_RATE_LIMIT_RPS
#   max_concurrent_connections  → SCOPE_MAX_CONCURRENT_CONNECTIONS

def _build_scope_defaults() -> dict:
    """组装 SCOPE_DEFAULTS: TOML defaults → 环境变量覆盖."""
    _toml = _load_scope_toml()

    # 硬编码回退值（当 TOML 缺失 / 无 tomllib 时使用）
    _fallback = {
        "blocked_targets": ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
                            "127.0.0.0/8", "169.254.0.0/16", "0.0.0.0/8"],
        "allowed_ports": [80, 443, 8080, 8443],
        "allowed_targets": ["*"],
        "disabled_tools": [],
        "disable_shell_exec": False,
        "disable_python_exec": False,
        "block_private_network": True,
        "block_dns_rebinding": True,
        "enforce_tls_verification": True,
        "max_response_size": 50000,
        "rate_limit_requests_per_sec": 10.0,
        "max_concurrent_connections": 20,
        "blocked_scan_types": ["udp_full", "tcp_full"],
    }

    def _merge_with_env(key, toml_val, fallback_val):
        """单个 key 的值合并: 环境变量优先 > TOML > fallback."""
        env_key = f"SCOPE_{key.upper()}"  # blocked_targets → SCOPE_BLOCKED_TARGETS
        env_val = os.getenv(env_key)

        if key in ("blocked_targets", "allowed_targets", "disabled_tools", "blocked_scan_types"):
            # 列表类: 环境变量用逗号分隔
            if env_val is not None:
                return [v.strip() for v in env_val.split(",") if v.strip()]
            if toml_val is not None:
                return list(toml_val)
            return list(fallback_val)

        if key == "allowed_ports":
            if env_val is not None:
                return [int(p.strip()) for p in env_val.split(",") if p.strip()]
            if toml_val is not None:
                return [int(p) for p in toml_val]
            return list(fallback_val)

        if key in ("disable_shell_exec", "disable_python_exec",
                   "block_private_network", "block_dns_rebinding",
                   "enforce_tls_verification"):
            # 布尔类
            if env_val is not None:
                return env_val.lower() == "true"
            if toml_val is not None:
                return bool(toml_val)
            return bool(fallback_val)

        if key == "rate_limit_requests_per_sec":
            if env_val is not None:
                return float(env_val)
            if toml_val is not None:
                return float(toml_val)
            return float(fallback_val)

        if key == "max_response_size":
            if env_val is not None:
                return int(env_val)
            if toml_val is not None:
                return int(toml_val)
            return int(fallback_val)

        if key == "max_concurrent_connections":
            if env_val is not None:
                return int(env_val)
            if toml_val is not None:
                return int(toml_val)
            return int(fallback_val)

        # 兜底
        if env_val is not None:
            return env_val
        if toml_val is not None:
            return toml_val
        return fallback_val

    result = {}
    for key in _fallback:
        result[key] = _merge_with_env(key, _toml.get(key), _fallback[key])

    return result


SCOPE_DEFAULTS = _build_scope_defaults()
