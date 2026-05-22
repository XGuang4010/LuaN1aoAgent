#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Checkpoint & Resume - 任务断点续传模块.

提供轻量级的 P-E-R 循环断点保存与恢复功能，基于 JSON 序列化。
"""

import asyncio
import json
import os
import glob
import time
from datetime import datetime
from typing import Dict, Any, Optional

CHECKPOINT_DIR = "logs/checkpoints"


def _ensure_checkpoint_dir() -> str:
    """确保 checkpoint 目录存在并返回路径."""
    os.makedirs(CHECKPOINT_DIR, exist_ok=True)
    return CHECKPOINT_DIR


def _checkpoint_path(op_id: str, cycle_num: int) -> str:
    """生成 checkpoint 文件路径."""
    return os.path.join(_ensure_checkpoint_dir(), f"{op_id}_cycle_{cycle_num}.json")


def _list_checkpoints(op_id: str) -> list:
    """列出指定 op_id 的所有 checkpoint 文件，按修改时间从新到旧排序."""
    pattern = os.path.join(_ensure_checkpoint_dir(), f"{op_id}_cycle_*.json")
    files = glob.glob(pattern)
    files.sort(key=lambda f: os.path.getmtime(f), reverse=True)
    return files


def _default_json_encoder(obj: Any) -> Any:
    """处理非标准 JSON 可序列化类型."""
    if isinstance(obj, set):
        return list(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


async def save_checkpoint(op_id: str, cycle_num: int, context: dict) -> None:
    """保存 checkpoint 到 JSON 文件.

    Args:
        op_id: 操作/会话 ID.
        cycle_num: 当前 P-E-R 循环计数.
        context: 上下文字典，必须包含 version, graph_state, last_summary,
                 observation_metadata, timestamp 等字段.
    """
    # 确保 timestamp 存在
    ctx = dict(context)
    if "timestamp" not in ctx:
        ctx["timestamp"] = time.time()

    path = _checkpoint_path(op_id, cycle_num)

    # 在后台线程中执行文件 I/O，避免阻塞事件循环
    def _write():
        with open(path, "w", encoding="utf-8") as f:
            json.dump(ctx, f, ensure_ascii=False, indent=2, default=_default_json_encoder)

    await asyncio.to_thread(_write)

    # 只保留最新的 5 个 checkpoint
    def _cleanup():
        files = _list_checkpoints(op_id)
        for old_file in files[5:]:
            try:
                os.remove(old_file)
            except OSError:
                pass

    await asyncio.to_thread(_cleanup)


def load_latest_checkpoint(op_id: str) -> Optional[dict]:
    """加载指定 op_id 最新的 checkpoint.

    Args:
        op_id: 操作/会话 ID.

    Returns:
        最新的 checkpoint 字典，如果不存在则返回 None.
    """
    files = _list_checkpoints(op_id)
    if not files:
        return None
    latest = files[0]
    with open(latest, "r", encoding="utf-8") as f:
        return json.load(f)
