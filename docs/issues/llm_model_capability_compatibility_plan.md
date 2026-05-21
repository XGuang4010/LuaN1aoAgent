# LLM 模型能力表与兼容层 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 OpenAI 兼容与 Anthropic 模型建立统一的能力表与兼容层，避免 `response_format`、`extra_body.thinking` 等供应商差异导致 Reflector/Planner/Executor 在运行时硬失败。

**Architecture:** 以 `conf/config.py` 维护一份轻量、可覆盖的模型能力表，`llm/llm_client.py` 只消费能力表，不再硬编码“OpenAI 兼容模型都支持某能力”的假设。调用链保持 `expect_json=True` 的上层契约不变，但底层根据模型能力决定是否启用原生结构化输出、是否注入 thinking 参数，以及是否在能力不兼容时报错前自动降级。

**Tech Stack:** Python 3.10+, httpx, dotenv, pytest

---

## 背景

本计划对应本次线上故障：

- 当前 `LLM_REFLECTOR_MODEL=glm-5.1` 时，Reflector 调用会因 `response_format.type=json_object` 不被支持而返回 400。
- 运行日志显示该错误并非业务子任务执行失败，而是反思阶段 LLM 参数不兼容导致的系统性失败。
- 当前代码在 [`llm_client.py`](file:///d:/Projects/LuaN1aoAgent/llm/llm_client.py) 中把 `expect_json=True` 直接等价成“总是发送 `response_format={"type":"json_object"}`”，这对 OpenAI 兼容接口并不成立。

当前关键代码位置：

- [`conf/config.py`](file:///d:/Projects/LuaN1aoAgent/conf/config.py)
- [`llm_client.py`](file:///d:/Projects/LuaN1aoAgent/llm/llm_client.py)

---

## 设计原则

- `AI Native`：保留上层角色与提示词的简单接口，不把模型兼容性细节泄漏到 Planner/Executor/Reflector。
- `Less is more`：第一版只抽象真实遇到的能力差异，不引入大而全的 provider SDK 适配层。
- `Base Abstract`：把问题拆成两个最小单元:
  - 模型是否支持某个请求能力
  - 当能力不支持时如何降级而不影响上层逻辑
- 兼容优先：优先保证任务不中断，其次才是追求某一供应商的原生高级能力。

---

## 范围

### 本次纳入

- 为模型增加统一能力表
- 把 `response_format` 注入改成能力驱动
- 把 `extra_body.thinking` 注入改成能力驱动
- 为 `response_format` 不兼容错误增加自动降级重试
- 增加最小测试覆盖
- 更新 `.env.example` / 文档，说明模型能力差异

### 本次不纳入

- 完整 provider 适配器重构
- tool call / vision / reasoning token 等尚未在当前链路使用的高级能力
- 动态在线探测模型能力并持久化缓存

---

## 文件地图

### 新增文件

- `docs/issues/llm_model_capability_compatibility_plan.md`
  - 当前实现计划文档。
- `tests/llm/test_llm_client_capabilities.py`
  - 覆盖能力表查找、payload 生成、能力降级与错误识别。

### 修改文件

- `conf/config.py`
  - 新增模型能力表、默认能力模板、环境变量覆盖入口。
- `llm/llm_client.py`
  - 根据能力表决定是否注入 `response_format` 与 `extra_body.thinking`，并处理不兼容错误的自动降级。
- `.env.example`
  - 增加能力覆盖配置示例。
- `README.md`
  - 说明 OpenAI 兼容模型不等于能力完全一致。
- `README_zh.md`
  - 同步中文说明。

---

## 目标能力模型

第一版能力表只保留当前真正需要消费的字段：

```python
{
    "supports_response_format_json_object": True,
    "supports_extra_body_thinking": False,
    "supports_native_json_output": True,
}
```

约束说明：

- `supports_response_format_json_object`
  - 是否允许注入 `response_format={"type":"json_object"}`。
- `supports_extra_body_thinking`
  - 是否允许注入 `extra_body={"thinking": ...}`。
- `supports_native_json_output`
  - 是否优先使用供应商原生 JSON 输出能力；若为 `False`，则只能走 prompt 约束 + 本地 JSON 解析。

建议的内置初始映射：

```python
{
    "gpt-4o": {
        "supports_response_format_json_object": True,
        "supports_extra_body_thinking": False,
        "supports_native_json_output": True,
    },
    "gpt-4o-mini": {
        "supports_response_format_json_object": True,
        "supports_extra_body_thinking": False,
        "supports_native_json_output": True,
    },
    "deepseek-v4-pro": {
        "supports_response_format_json_object": True,
        "supports_extra_body_thinking": True,
        "supports_native_json_output": True,
    },
    "deepseek-v4-flash": {
        "supports_response_format_json_object": True,
        "supports_extra_body_thinking": True,
        "supports_native_json_output": True,
    },
    "glm-5.1": {
        "supports_response_format_json_object": False,
        "supports_extra_body_thinking": False,
        "supports_native_json_output": False,
    },
    "claude-sonnet-4-5": {
        "supports_response_format_json_object": False,
        "supports_extra_body_thinking": False,
        "supports_native_json_output": False,
    },
}
```

未知模型的默认策略：

- `supports_response_format_json_object=False`
- `supports_extra_body_thinking=False`
- `supports_native_json_output=False`

也就是保守降级，而不是乐观假设。

---

## 任务分解

### Task 1: 在配置层引入模型能力表

**Files:**
- Modify: `conf/config.py`
- Test: `tests/llm/test_llm_client_capabilities.py`

- [ ] **Step 1: 写失败测试，固定能力表默认行为**

```python
from llm.llm_client import LLMClient


def test_unknown_model_uses_safe_capability_defaults():
    client = LLMClient()

    caps = client._get_model_capabilities("unknown-model")

    assert caps["supports_response_format_json_object"] is False
    assert caps["supports_extra_body_thinking"] is False
    assert caps["supports_native_json_output"] is False
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/llm/test_llm_client_capabilities.py::test_unknown_model_uses_safe_capability_defaults -v`
Expected: FAIL with `AttributeError: 'LLMClient' object has no attribute '_get_model_capabilities'`

- [ ] **Step 3: 在 `conf/config.py` 增加能力表配置**

```python
import json
import os
from copy import deepcopy
from dotenv import load_dotenv

load_dotenv()

DEFAULT_LLM_MODEL_CAPABILITIES = {
    "supports_response_format_json_object": False,
    "supports_extra_body_thinking": False,
    "supports_native_json_output": False,
}

LLM_MODEL_CAPABILITIES = {
    "gpt-4o": {
        "supports_response_format_json_object": True,
        "supports_extra_body_thinking": False,
        "supports_native_json_output": True,
    },
    "gpt-4o-mini": {
        "supports_response_format_json_object": True,
        "supports_extra_body_thinking": False,
        "supports_native_json_output": True,
    },
    "deepseek-v4-pro": {
        "supports_response_format_json_object": True,
        "supports_extra_body_thinking": True,
        "supports_native_json_output": True,
    },
    "deepseek-v4-flash": {
        "supports_response_format_json_object": True,
        "supports_extra_body_thinking": True,
        "supports_native_json_output": True,
    },
    "glm-5.1": {
        "supports_response_format_json_object": False,
        "supports_extra_body_thinking": False,
        "supports_native_json_output": False,
    },
    "claude-sonnet-4-5": {
        "supports_response_format_json_object": False,
        "supports_extra_body_thinking": False,
        "supports_native_json_output": False,
    },
}


def _merge_model_capabilities(base: dict, override: dict) -> dict:
    merged = deepcopy(base)
    for model_name, model_caps in override.items():
        if not isinstance(model_caps, dict):
            continue
        merged.setdefault(model_name, deepcopy(DEFAULT_LLM_MODEL_CAPABILITIES))
        merged[model_name].update(
            {
                "supports_response_format_json_object": bool(
                    model_caps.get("supports_response_format_json_object", merged[model_name]["supports_response_format_json_object"])
                ),
                "supports_extra_body_thinking": bool(
                    model_caps.get("supports_extra_body_thinking", merged[model_name]["supports_extra_body_thinking"])
                ),
                "supports_native_json_output": bool(
                    model_caps.get("supports_native_json_output", merged[model_name]["supports_native_json_output"])
                ),
            }
        )
    return merged


LLM_MODEL_CAPABILITIES_OVERRIDE_JSON = os.getenv("LLM_MODEL_CAPABILITIES_OVERRIDE_JSON", "").strip()
if LLM_MODEL_CAPABILITIES_OVERRIDE_JSON:
    try:
        LLM_MODEL_CAPABILITIES = _merge_model_capabilities(
            LLM_MODEL_CAPABILITIES,
            json.loads(LLM_MODEL_CAPABILITIES_OVERRIDE_JSON),
        )
    except json.JSONDecodeError:
        pass
```

- [ ] **Step 4: 在 `llm_client.py` 暴露能力查询方法**

```python
from conf.config import (
    DEFAULT_LLM_MODEL_CAPABILITIES,
    LLM_MODEL_CAPABILITIES,
    ...
)


def _clone_capabilities(self, source: dict) -> dict:
    return {
        "supports_response_format_json_object": bool(source.get("supports_response_format_json_object", False)),
        "supports_extra_body_thinking": bool(source.get("supports_extra_body_thinking", False)),
        "supports_native_json_output": bool(source.get("supports_native_json_output", False)),
    }


def _get_model_capabilities(self, model_name: str) -> dict:
    if model_name in LLM_MODEL_CAPABILITIES:
        return self._clone_capabilities(LLM_MODEL_CAPABILITIES[model_name])
    return self._clone_capabilities(DEFAULT_LLM_MODEL_CAPABILITIES)
```

- [ ] **Step 5: 运行测试确认通过**

Run: `pytest tests/llm/test_llm_client_capabilities.py::test_unknown_model_uses_safe_capability_defaults -v`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add conf/config.py llm/llm_client.py tests/llm/test_llm_client_capabilities.py
git commit -m "feat: add model capability registry"
```

---

### Task 2: 让 OpenAI 兼容 payload 构造改为能力驱动

**Files:**
- Modify: `llm/llm_client.py`
- Test: `tests/llm/test_llm_client_capabilities.py`

- [ ] **Step 1: 写失败测试，固定 `response_format` 与 `thinking` 的注入规则**

```python
from llm.llm_client import LLMClient


def test_glm_model_does_not_emit_response_format_or_thinking(monkeypatch):
    client = LLMClient()
    monkeypatch.setattr(client, "provider", "openai")

    headers, payload = client._prepare_openai_payload(
        current_messages=[{"role": "user", "content": "return json"}],
        model_name="glm-5.1",
        temperature=0.2,
        role="reflector",
        expect_json=True,
    )

    assert "response_format" not in payload
    assert "extra_body" not in payload


def test_deepseek_model_keeps_native_json_support(monkeypatch):
    client = LLMClient()
    monkeypatch.setattr(client, "provider", "openai")

    headers, payload = client._prepare_openai_payload(
        current_messages=[{"role": "user", "content": "return json"}],
        model_name="deepseek-v4-pro",
        temperature=0.2,
        role="reflector",
        expect_json=True,
    )

    assert payload["response_format"] == {"type": "json_object"}
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/llm/test_llm_client_capabilities.py::test_glm_model_does_not_emit_response_format_or_thinking -v`
Expected: FAIL because current payload always contains `response_format`

- [ ] **Step 3: 改造 `_prepare_openai_payload()`**

```python
def _prepare_openai_payload(
    self,
    current_messages: list,
    model_name: str,
    temperature: float,
    role: str,
    expect_json: bool,
    disable_native_json: bool = False,
) -> tuple[dict, dict]:
    headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model_name,
        "messages": current_messages,
        "temperature": temperature,
        "stream": False,
    }

    capabilities = self._get_model_capabilities(model_name)

    if LLM_EXTRA_BODY_ENABLED and capabilities["supports_extra_body_thinking"]:
        thinking_mode = LLM_THINKING.get(role, LLM_THINKING.get("default", "off")).lower()
        if thinking_mode in ["hidden", "visible"]:
            payload["extra_body"] = {"thinking": thinking_mode}

    can_use_native_json = (
        expect_json
        and not disable_native_json
        and capabilities["supports_native_json_output"]
        and capabilities["supports_response_format_json_object"]
    )
    if can_use_native_json:
        payload["response_format"] = {"type": "json_object"}

    return headers, payload
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/llm/test_llm_client_capabilities.py -k "emit_response_format or native_json_support" -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add llm/llm_client.py tests/llm/test_llm_client_capabilities.py
git commit -m "feat: drive payload generation by model capabilities"
```

---

### Task 3: 为 `response_format` 不兼容增加自动降级重试

**Files:**
- Modify: `llm/llm_client.py`
- Test: `tests/llm/test_llm_client_capabilities.py`

- [ ] **Step 1: 写失败测试，固定不兼容错误的降级行为**

```python
from llm.llm_client import LLMClient


def test_response_format_unsupported_error_is_detected():
    client = LLMClient()
    error = Exception(
        "LLM API请求失败: 400 {\"error\":{\"message\":\"`response_format.type` specified in the request are not valid: `json_object` is not supported by this model.\"}}"
    )

    assert client._is_response_format_unsupported_error(error) is True
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/llm/test_llm_client_capabilities.py::test_response_format_unsupported_error_is_detected -v`
Expected: FAIL with `AttributeError`

- [ ] **Step 3: 实现错误识别与自动降级**

```python
def _is_response_format_unsupported_error(self, error: Exception) -> bool:
    message = str(error)
    return (
        "response_format.type" in message
        and "json_object" in message
        and "not supported" in message
    )


async def send_message(
    self, messages: List[Dict[str, Any]], role: str = "default", expect_json: bool = True
) -> tuple[Dict | str | None, Dict | None]:
    model_name = self.models.get(role) or self.models.get("default")
    temperature = self.temperatures.get(role, self.temperatures.get("default", 0.2))
    disable_native_json = False

    while json_parsing_retries <= MAX_JSON_PARSE_RETRIES:
        try:
            if self.provider == "anthropic":
                headers, payload = self._prepare_anthropic_payload(current_messages, model_name)
            else:
                headers, payload = self._prepare_openai_payload(
                    current_messages=current_messages,
                    model_name=model_name,
                    temperature=temperature,
                    role=role,
                    expect_json=expect_json,
                    disable_native_json=disable_native_json,
                )
            ...
        except Exception as e:
            if (
                self.provider != "anthropic"
                and expect_json
                and not disable_native_json
                and self._is_response_format_unsupported_error(e)
            ):
                disable_native_json = True
                self._get_console().print(
                    "[bold yellow]模型不支持 response_format=json_object，自动降级为 prompt-only JSON 模式重试。[/bold yellow]"
                )
                continue
            ...
            raise e
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/llm/test_llm_client_capabilities.py::test_response_format_unsupported_error_is_detected -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add llm/llm_client.py tests/llm/test_llm_client_capabilities.py
git commit -m "fix: downgrade unsupported response_format automatically"
```

---

### Task 4: 增加端到端最小回归测试

**Files:**
- Create: `tests/llm/test_llm_client_capabilities.py`
- Modify: `llm/llm_client.py`

- [ ] **Step 1: 写端到端测试，模拟一次失败后降级成功**

```python
import json
import pytest

from llm.llm_client import LLMClient


class _FakeResponse:
    def __init__(self, status_code: int, text: str):
        self.status_code = status_code
        self.text = text


@pytest.mark.asyncio
async def test_send_message_retries_without_native_json_on_unsupported_response_format(monkeypatch):
    client = LLMClient()
    monkeypatch.setattr(client, "provider", "openai")
    monkeypatch.setattr(client, "models", {"default": "glm-5.1"})

    responses = [
        _FakeResponse(
            400,
            json.dumps(
                {
                    "error": {
                        "message": "`response_format.type` specified in the request are not valid: `json_object` is not supported by this model."
                    }
                }
            ),
        ),
        _FakeResponse(
            200,
            json.dumps(
                {
                    "choices": [
                        {
                            "message": {
                                "content": "{\"audit_result\": {\"status\": \"completed\", \"completion_check\": \"ok\"}}"
                            }
                        }
                    ],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 10},
                }
            ),
        ),
    ]

    async def _fake_post(*args, **kwargs):
        return responses.pop(0)

    monkeypatch.setattr(client.client, "post", _fake_post)

    data, metrics = await client.send_message(
        [{"role": "user", "content": "return json"}],
        role="default",
        expect_json=True,
    )

    assert data["audit_result"]["status"] == "completed"
    assert metrics["prompt_tokens"] == 10
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/llm/test_llm_client_capabilities.py::test_send_message_retries_without_native_json_on_unsupported_response_format -v`
Expected: FAIL before retry path is implemented correctly

- [ ] **Step 3: 校准实现直到回归测试通过**

```python
# send_message() 的关键约束:
# 1. 只在第一次遇到 response_format 不兼容时降级
# 2. 降级后仍保持 expect_json=True
# 3. 仍复用现有 _robust_json_parser() 逻辑
# 4. 429 / 网络错误 / JSON 解析错误重试逻辑不被破坏
```

- [ ] **Step 4: 运行完整测试**

Run: `pytest tests/llm/test_llm_client_capabilities.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add llm/llm_client.py tests/llm/test_llm_client_capabilities.py
git commit -m "test: cover model capability fallback flow"
```

---

### Task 5: 更新开发文档与环境示例

**Files:**
- Modify: `.env.example`
- Modify: `README.md`
- Modify: `README_zh.md`

- [ ] **Step 1: 在 `.env.example` 增加能力覆盖示例**

```ini
# 可选：按模型覆盖能力。适用于 OpenAI 兼容供应商能力不一致的场景。
# 示例：禁用 glm-5.1 的原生 JSON 输出能力。
LLM_MODEL_CAPABILITIES_OVERRIDE_JSON={"glm-5.1":{"supports_response_format_json_object":false,"supports_extra_body_thinking":false,"supports_native_json_output":false}}
```

- [ ] **Step 2: 在 README 中增加兼容性说明**

```md
### Model capability compatibility

OpenAI-compatible APIs do not guarantee identical support for `response_format`,
`extra_body.thinking`, or native JSON output. LuaN1ao uses a lightweight model
capability registry in `conf/config.py` so the runtime can safely downgrade when
a provider does not support a requested feature.
```

- [ ] **Step 3: 在中文 README 中同步说明**

```md
### 模型能力兼容性

OpenAI 兼容接口并不代表完全兼容 `response_format`、`extra_body.thinking`
或原生 JSON 输出。LuaN1ao 在 `conf/config.py` 中维护轻量能力表，并在运行时
根据模型能力自动降级，以避免因供应商差异导致 Reflector/Planner/Executor 硬失败。
```

- [ ] **Step 4: 提交**

```bash
git add .env.example README.md README_zh.md
git commit -m "docs: document model capability compatibility"
```

---

## 关键实现说明

### 为什么是能力表，而不是模型名 if-else

- if-else 只能解决单个现象，无法表达“同一模型支持 JSON 但不支持 thinking”的组合差异。
- 能力表把“模型名”与“功能能力”分离，后续接入新模型只需补配置，不必继续污染 `llm_client.py`。
- 这也为后续的“智能模型路由”提供基础数据，不会和总路线图冲突。

### 为什么默认保守

- 当前故障已经证明，对 OpenAI 兼容接口使用乐观假设风险很高。
- 对未知模型默认禁用原生高级能力，最坏结果只是退回 prompt-only JSON 模式，而不是整条子任务失败。

### 为什么保留 `expect_json=True`

- `Reflector`、`Planner`、`Executor` 当前都依赖结构化 JSON 契约。
- 上层语义不应因底层供应商差异而改变。
- 本方案只调整“如何让模型返回 JSON”，不调整“上层是否需要 JSON”。

---

## 验收标准

- 使用 `glm-5.1` 作为 `reflector` 时，不再因为 `response_format=json_object` 报 400。
- 使用 `deepseek-v4-pro` 时，仍保持原生 JSON 输出路径，不引入行为回退。
- `LLM_EXTRA_BODY_ENABLED=true` 时，只有能力表声明支持的模型才注入 `extra_body.thinking`。
- 未知模型默认进入保守兼容路径，不出现运行时硬失败。
- 相关测试通过：

```bash
pytest tests/llm/test_llm_client_capabilities.py -v
```

---

## 风险与回滚

- 风险 1：能力表初始映射写错，可能导致某模型没有启用本可使用的能力。
  - 处理：优先保证稳定，再通过文档与配置覆盖修正。
- 风险 2：字符串匹配错误文案过窄，无法识别某些供应商的报错。
  - 处理：第一版先覆盖已知报错文本，后续按日志扩充。
- 风险 3：过度扩展能力字段，反而让配置膨胀。
  - 处理：只保留当前实际消费的三个字段。

回滚方式：

- 若能力表实现引发新的回归，可先保留 `Task 1` 的静态能力表，但去掉 `Task 3` 的自动降级逻辑，退回显式配置兼容模式。

---

## 实施顺序建议

1. 先做 `Task 1 + Task 2`，把静态兼容行为跑通。
2. 再做 `Task 3`，补自动降级，解决运行时未声明模型的兼容问题。
3. 最后补 `Task 4 + Task 5`，收尾测试与文档。

---

## 自检结论

- 覆盖性：已覆盖配置、运行时、自动降级、测试与文档五个维度。
- 无占位符：所有任务均给出明确文件路径、命令与代码草案。
- 与现有架构兼容：不改 Planner/Executor/Reflector 的调用契约，只增强 `config.py` 与 `llm_client.py` 的边界能力。

---

Plan complete and saved to `docs/issues/llm_model_capability_compatibility_plan.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
