#!/usr/bin/env python3
"""只读诊断：查 knowledge_base 是否有重复入库（按 source_id / title 分组）。
用法: python scripts/peek_kb.py"""
import sys, os, asyncio
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlalchemy import text
from app.database import engine


async def f():
    async with engine.begin() as c:
        total = (await c.execute(text("select count(*) from knowledge_base"))).scalar()
        print("knowledge_base 总行数:", total)

        distinct_titles = (await c.execute(text("select count(distinct title) from knowledge_base"))).scalar()
        print("distinct 标题数:", distinct_titles, " (若 总行数 = N × distinct → 重复入库 N 次)")

        print("\n=== 按 source_id 分组（每个来源文档入库多少行）===")
        for r in (await c.execute(text(
            "select source_id, count(*) from knowledge_base group by source_id order by count(*) desc"))).all():
            print("   source_id=", str(r[0])[:8] if r[0] else None, " 行数=", r[1])

        print("\n=== 重复最多的标题 Top5（>1 即重复入库）===")
        for r in (await c.execute(text(
            "select title, count(*) c from knowledge_base group by title order by c desc limit 5"))).all():
            print("   x", r[1], " ", (r[0] or "")[:40])


asyncio.run(f())
