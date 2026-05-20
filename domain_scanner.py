#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
子域名发现和批量扫描管理工具
用于批量处理域名、发现子域名、导出导入数据
"""

import argparse
import asyncio
import json
import os
import subprocess
import sys
import tempfile
from typing import List, Dict, Any

# 添加项目根目录
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.database.utils import (
    init_db,
    create_domain_target,
    add_subdomain,
    get_domain_target,
    get_domain_target_by_id,
    get_all_domain_targets,
    get_subdomains,
    update_subdomain_status,
    update_domain_target_status,
    export_to_json,
    import_from_json,
    add_scan_result
)
from tools.tool_env import resolve_project_tool


def _resolve_project_tool(tool_name: str) -> str | None:
    """只通过项目根目录 .env 解析扫描依赖。"""
    mapping = {
        "subfinder": ("SUBFINDER_PATH", r"subfinder\subfinder.exe"),
        "httpx": ("PD_HTTPX_PATH", r"httpx\httpx.exe"),
    }
    env_var_name, tools_home_subpath = mapping[tool_name]
    return resolve_project_tool(
        tool_name=tool_name,
        env_var_name=env_var_name,
        tools_home_subpath=tools_home_subpath,
    )


async def cmd_add_domain(domain: str, description: str = None):
    """添加域名目标"""
    print(f"添加域名: {domain}")
    domain_target = await create_domain_target(domain, description)
    print(f"✓ 域名已添加，ID: {domain_target.id}")


async def cmd_list_domains():
    """列出所有域名"""
    domains = await get_all_domain_targets()
    if not domains:
        print("没有找到域名")
        return
    
    print(f"\n{'ID':<5} {'Domain':<30} {'Status':<10} {'Subdomains':<10} {'Created At'}")
    print("-" * 80)
    
    for dt in domains:
        subdomains = await get_subdomains(dt.id)
        created_str = dt.created_at.strftime("%Y-%m-%d %H:%M") if dt.created_at else "-"
        print(f"{dt.id:<5} {dt.domain:<30} {dt.status:<10} {len(subdomains):<10} {created_str}")


async def cmd_export(domain_id: int = None, output: str = "export.json"):
    """导出数据"""
    output_path = await export_to_json(domain_id, output)
    print(f"✓ 数据已导出到: {output_path}")


async def cmd_import(input_file: str):
    """导入数据"""
    imported = await import_from_json(input_file)
    print(f"✓ 成功导入 {len(imported)} 个域名")


async def cmd_scan_subdomains(domain: str, use_subfinder: bool = True):
    """扫描子域名"""
    domain_target = await get_domain_target(domain)
    if not domain_target:
        print(f"创建域名目标: {domain}")
        domain_target = await create_domain_target(domain)
    
    print(f"开始扫描子域名: {domain}")
    await update_domain_target_status(domain_target.id, "scanning")
    
    subdomains = []
    
    # 使用 subfinder 扫描
    if use_subfinder:
        subfinder_executable = _resolve_project_tool("subfinder")
        if not subfinder_executable:
            raise RuntimeError(
                "subfinder not configured. Checked SUBFINDER_PATH and "
                "TOOLS_HOME/subfinder/subfinder.exe from project .env only."
            )

        try:
            print("  使用 subfinder 扫描...")
            result = subprocess.run(
                [subfinder_executable, "-d", domain, "-silent"],
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if result.stdout:
                subdomains = [line.strip() for line in result.stdout.strip().split("\n") if line.strip()]
                print(f"  subfinder 发现 {len(subdomains)} 个子域名")
                
                # 保存到数据库
                for sd in subdomains:
                    await add_subdomain(domain_target.id, sd, source="subfinder")
        
        except FileNotFoundError:
            print("  ⚠ subfinder 未安装，请先安装: https://github.com/projectdiscovery/subfinder")
        except Exception as e:
            print(f"  ✗ subfinder 扫描失败: {e}")
    
    # 探测 HTTP 状态
    if subdomains:
        httpx_executable = _resolve_project_tool("httpx")
        if not httpx_executable:
            raise RuntimeError(
                "httpx not configured. Checked PD_HTTPX_PATH and "
                "TOOLS_HOME/httpx/httpx.exe from project .env only."
            )

        print("  使用 httpx 探测状态...")
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
                for sd in subdomains:
                    f.write(f"{sd}\n")
                temp_file = f.name
            
            result = subprocess.run(
                [httpx_executable, "-l", temp_file, "-sc", "-silent"],
                capture_output=True,
                text=True,
                timeout=300
            )
            
            # 解析 httpx 结果
            if result.stdout:
                from core.database.models import Subdomain
                from sqlalchemy import select
                from core.database.utils import AsyncSessionLocal
                
                async with AsyncSessionLocal() as session:
                    db_subdomains = await session.execute(
                        select(Subdomain).where(Subdomain.domain_target_id == domain_target.id)
                    )
                    subdomain_cache = {sd.subdomain: sd for sd in db_subdomains.scalars().all()}
                    
                    for line in result.stdout.strip().split("\n"):
                        if line.strip():
                            parts = line.split()
                            if parts:
                                url = parts[0]
                                if url.startswith("http://"):
                                    sd_name = url[7:]
                                elif url.startswith("https://"):
                                    sd_name = url[8:]
                                else:
                                    sd_name = url
                                
                                if "/" in sd_name:
                                    sd_name = sd_name.split("/", 1)[0]
                                if ":" in sd_name and not sd_name.endswith(("http", "https")):
                                    sd_name = sd_name.split(":", 1)[0]
                                
                                status_code = None
                                for part in parts:
                                    if len(part) == 3 and part.isdigit():
                                        status_code = int(part)
                                        break
                                
                                if sd_name in subdomain_cache:
                                    sd = subdomain_cache[sd_name]
                                    if status_code:
                                        sd.http_status = status_code
                                    sd.status = "tested"
                    
                    for sd in subdomain_cache.values():
                        await session.merge(sd)
                    await session.commit()
            
            os.unlink(temp_file)
            print("  httpx 探测完成")
        
        except FileNotFoundError:
            print("  ⚠ httpx 未安装，请先安装: https://github.com/projectdiscovery/httpx")
        except Exception as e:
            print(f"  ✗ httpx 探测失败: {e}")
    
    await update_domain_target_status(domain_target.id, "completed")
    print(f"\n✓ 扫描完成！共发现 {len(subdomains)} 个子域名")


async def cmd_info(domain_id: int = None, domain: str = None):
    """显示域名详细信息"""
    domain_target = None
    if domain_id:
        domain_target = await get_domain_target_by_id(domain_id)
    elif domain:
        domain_target = await get_domain_target(domain)
    
    if not domain_target:
        print("未找到该域名")
        return
    
    print(f"\n=== 域名详情: {domain_target.domain} ===")
    print(f"ID: {domain_target.id}")
    print(f"描述: {domain_target.description or '-'}")
    print(f"状态: {domain_target.status}")
    print(f"创建时间: {domain_target.created_at}")
    
    subdomains = await get_subdomains(domain_target.id)
    print(f"\n子域名列表 ({len(subdomains)}):")
    print(f"{'Subdomain':<40} {'Status':<15} {'HTTP':<10} {'Source'}")
    print("-" * 80)
    
    for sd in subdomains:
        http_str = str(sd.http_status) if sd.http_status else "-"
        print(f"{sd.subdomain:<40} {sd.status:<15} {http_str:<10} {sd.source or '-'}")


def main():
    parser = argparse.ArgumentParser(description="子域名发现和扫描管理工具")
    subparsers = parser.add_subparsers(title="命令", dest="command")
    
    # 添加域名
    add_parser = subparsers.add_parser("add", help="添加域名")
    add_parser.add_argument("domain", help="域名")
    add_parser.add_argument("--description", help="描述")
    
    # 列出域名
    list_parser = subparsers.add_parser("list", help="列出所有域名")
    
    # 扫描子域名
    scan_parser = subparsers.add_parser("scan", help="扫描子域名")
    scan_parser.add_argument("domain", help="域名")
    scan_parser.add_argument("--no-subfinder", action="store_true", help="不使用 subfinder")
    
    # 查看详情
    info_parser = subparsers.add_parser("info", help="查看域名详情")
    info_parser.add_argument("--id", type=int, help="域名ID")
    info_parser.add_argument("--domain", help="域名")
    
    # 导出
    export_parser = subparsers.add_parser("export", help="导出数据")
    export_parser.add_argument("--id", type=int, help="指定域名ID (可选)")
    export_parser.add_argument("--output", default="export.json", help="输出文件路径")
    
    # 导入
    import_parser = subparsers.add_parser("import", help="导入数据")
    import_parser.add_argument("input", help="输入JSON文件")
    
    args = parser.parse_args()
    
    # 初始化数据库
    asyncio.run(init_db())
    
    if args.command == "add":
        asyncio.run(cmd_add_domain(args.domain, args.description))
    elif args.command == "list":
        asyncio.run(cmd_list_domains())
    elif args.command == "scan":
        asyncio.run(cmd_scan_subdomains(args.domain, use_subfinder=not args.no_subfinder))
    elif args.command == "info":
        asyncio.run(cmd_info(args.id, args.domain))
    elif args.command == "export":
        asyncio.run(cmd_export(args.id, args.output))
    elif args.command == "import":
        asyncio.run(cmd_import(args.input))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
