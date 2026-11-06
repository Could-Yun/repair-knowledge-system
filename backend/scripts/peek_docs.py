#!/usr/bin/env python3
"""只读诊断：查 knowledge_documents / knowledge_base / users 现状，定位"管理员看不到待审核文档"。
用法: python scripts/peek_docs.py"""
import sys, os, asyncio
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlalchemy import text
from app.database import engine


async def f():
    async with engine.begin() as c:
        print("=== users (账号与角色) ===")
        for r in (await c.execute(text("select username, role from users order by username"))).all():
            print("  ", r[0], "->", r[1])

        print("\n=== knowledge_documents 按状态计数 ===")
        rows = (await c.execute(text(
            "select status, count(*) from knowledge_documents group by status"))).all()
        if not rows:
            print("   (空表：一条文档都没有 → 说明上传根本没写进库)")
        for r in rows:
            print("   status=", r[0], " count=", r[1])

        print("\n=== 最近 10 条文档明细 ===")
        docs = (await c.execute(text(
            "select title, status, chunk_count, ingested_count, submitter_id, created_at "
            "from knowledge_documents order by created_at desc limit 10"))).all()
        if not docs:
            print("   (无)")
        for d in docs:
            print("   title=", d[0], "| status=", d[1], "| chunks=", d[2],
                  "| ingested=", d[3], "| submitter=", str(d[4])[:8], "| at=", d[5])

        print("\n=== knowledge_base 计数 ===")
        kb = (await c.execute(text("select count(*) from knowledge_base"))).scalar()
        print("   knowledge_base 行数:", kb)


asyncio.run(f())
