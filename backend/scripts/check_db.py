#!/usr/bin/env python3
"""
数据库连接体检脚本 — 部署前必跑
检查项：
  1. 连通性 + 服务器版本
  2. pgvector / uuid-ossp / pg_trgm / zhparser 安装情况
  3. 文本搜索配置（simple / chinese）
  4. 向量类型测试（768 维往返）
  5. 表是否已建（如未建，提示运行 init_db.py）

用法:
  python scripts/check_db.py
返回码:
  0 = 全部 OK；非 0 = 至少一项致命失败
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from sqlalchemy import text


GREEN = "\033[92m"
RED   = "\033[91m"
YELL  = "\033[93m"
BLUE  = "\033[94m"
DIM   = "\033[2m"
END   = "\033[0m"

def ok(msg):    print(f"  {GREEN}[ OK ]{END} {msg}")
def fail(msg):  print(f"  {RED}[FAIL]{END} {msg}")
def warn(msg):  print(f"  {YELL}[WARN]{END} {msg}")
def info(msg):  print(f"  {BLUE}[INFO]{END} {msg}")
def section(t): print(f"\n{BLUE}━━━ {t} ━━━{END}")


async def main():
    from app.config   import settings
    from app.database import engine

    print(f"\n{BLUE}╔══════════════════════════════════════════════╗{END}")
    print(f"{BLUE}║   设备检修系统 · 数据库体检（check_db）       ║{END}")
    print(f"{BLUE}╚══════════════════════════════════════════════╝{END}")

    info(f"环境标识: APP_ENV={settings.APP_ENV}")
    info(f"目标 URL : {_mask(settings.DATABASE_URL)}")
    info(f"FTS_CONFIG={settings.FTS_CONFIG}  ENABLE_ZHPARSER={settings.ENABLE_ZHPARSER}")

    fatal = 0
    section("1. 连通性 & 服务器版本")
    try:
        async with engine.begin() as conn:
            ver = (await conn.execute(text("SELECT version()"))).scalar()
            ok(f"已连接 — {ver.split(',')[0]}")
    except Exception as e:
        fail(f"连接失败：{e}")
        print(f"\n{RED}请先按 docs/DATABASE_SETUP.md 启动 PostgreSQL 并创建数据库{END}")
        return 1

    # 2. 扩展
    section("2. 扩展安装情况")
    EXPECTED = [
        ("uuid-ossp", True),
        ("vector",    True),
        ("pg_trgm",   False),
        ("zhparser",  False),  # V11 必需，本地可缺
    ]
    installed = set()
    async with engine.begin() as conn:
        rows = (await conn.execute(text("SELECT extname FROM pg_extension"))).scalars().all()
        installed = set(rows)

    for ext, required in EXPECTED:
        if ext in installed:
            ok(f"{ext} 已安装")
        else:
            if required:
                fail(f"{ext} 未安装（必需扩展）")
                fatal += 1
            elif ext == "zhparser" and settings.ENABLE_ZHPARSER:
                fail(f"{ext} 未安装 — 但 ENABLE_ZHPARSER=true，请确认 V11 上已编译")
                fatal += 1
            else:
                warn(f"{ext} 未安装（本地开发可忽略）")

    # 3. 文本搜索配置
    section("3. 文本搜索配置")
    async with engine.begin() as conn:
        configs = (await conn.execute(text(
            "SELECT cfgname FROM pg_ts_config WHERE cfgname IN ('simple','chinese')"
        ))).scalars().all()
    if "simple" in configs:
        ok("simple parser 可用（PG 默认）")
    if "chinese" in configs:
        ok("chinese (zhparser) parser 可用")
    elif settings.FTS_CONFIG == "chinese":
        fail("FTS_CONFIG=chinese 但 chinese 配置不存在")
        fatal += 1
    else:
        warn("chinese parser 未配置（本地开发使用 simple，正常）")

    # 4. pgvector 端到端
    section("4. pgvector 端到端（768 维往返）")
    try:
        async with engine.begin() as conn:
            # 构造一个 768 维测试向量
            vec_str = "[" + ",".join(["0.1"] * 768) + "]"
            await conn.execute(text("DROP TABLE IF EXISTS __vector_smoke_test"))
            await conn.execute(text("CREATE TEMP TABLE __vector_smoke_test (id int, v vector(768))"))
            await conn.execute(text("INSERT INTO __vector_smoke_test VALUES (1, CAST(:v AS vector))"), {"v": vec_str})
            sim = (await conn.execute(text(
                "SELECT 1 - (v <=> CAST(:v AS vector)) FROM __vector_smoke_test WHERE id=1"
            ), {"v": vec_str})).scalar()
            assert abs(float(sim) - 1.0) < 1e-6, f"自相似应为 1，实际 {sim}"
        ok(f"pgvector 768 维测试通过（cosine self-sim = {sim:.6f}）")
    except Exception as e:
        fail(f"pgvector 测试失败：{_short(e)}")
        fatal += 1

    # 5. 业务表
    section("5. 业务表")
    async with engine.begin() as conn:
        tables = (await conn.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
        ))).scalars().all()
    expected_tables = {
        "users", "device_types", "cases", "knowledge_base",
        "workflow_templates", "repair_records", "feedbacks",
        "upload_files", "kg_entities", "kg_relations",
    }
    found = set(tables) & expected_tables
    if not found:
        warn("未发现业务表 — 请运行: python scripts/init_db.py")
    elif found == expected_tables:
        ok(f"全部 {len(expected_tables)} 张业务表已建")
    else:
        missing = expected_tables - found
        warn(f"已建 {len(found)}/{len(expected_tables)} 张表，缺失: {','.join(missing)}")

    # 6. 总结
    section("总结")
    if fatal == 0:
        print(f"{GREEN}✓ 数据库就绪，可以启动后端{END}\n")
        return 0
    print(f"{RED}✗ {fatal} 项致命失败，请按上述提示处理后重试{END}\n")
    return 1


def _mask(url: str) -> str:
    import re
    return re.sub(r'(://[^:]+:)[^@]+(@)', r'\1***\2', url)


def _short(e: Exception, n=180):
    s = str(e).strip().splitlines()[0]
    return (s[:n] + "...") if len(s) > n else s


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
