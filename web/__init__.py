#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LuaN1ao Web可视化模块.

本包提供基于FastAPI的Web可视化服务，
用于实时监控任务执行进度和图谱演化。

主要功能:
    - 任务图谱可视化
    - 因果图谱展示
    - 实时执行日志
    - SSE事件推送
    - 指标统计展示

使用方式:
    python agent.py --goal "目标" --task-name "任务" --web --web-port 8000
    然后访问: http://localhost:8000
"""

def create_app():
    from .server import create_app as _create_app

    return _create_app()


__all__ = ["create_app"]

__version__ = '1.0.0'
