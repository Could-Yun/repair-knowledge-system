#!/usr/bin/env python3
"""
知识图谱抽取脚本：从 knowledge_base 中抽取三元组写入 kg_entities + kg_relations
建议后台异步运行（耗时），仅处理 source_type='manual' 的条目

用法:
  python3 scripts/extract_kg.py --source manual --limit 100
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import argparse

async def extract(source_type: str, limit: int):
    from app.database import async_session
    from app.models.knowledge import KnowledgeBase
    from app.services.kg_service import KGService
    from sqlalchemy import select

    kg = KGService()
    async with async_session() as db:
        q = select(KnowledgeBase).where(KnowledgeBase.source_type == source_type).limit(limit)
        rows = (await db.execute(q)).scalars().all()
        print(f"[INFO] 共 {len(rows)} 条知识待抽取 KG")

    processed = 0
    for kb in rows:
        try:
            await kg.extract_and_store(kb.content, source_case_id=str(kb.source_id) if kb.source_id else None)
            processed += 1
            if processed % 10 == 0:
                print(f"[INFO] 已处理 {processed}/{len(rows)}")
        except Exception as e:
            print(f"[WARN] 抽取失败 kb_id={kb.id}: {e}")

    print(f"[DONE] KG 抽取完成，共处理 {processed} 条")

def main():
    parser = argparse.ArgumentParser(description="知识图谱三元组抽取")
    parser.add_argument("--source", default="manual", help="来源类型: manual|case")
    parser.add_argument("--limit",  type=int, default=200, help="最多处理条数")
    args = parser.parse_args()
    asyncio.run(extract(args.source, args.limit))

if __name__ == "__main__":
    main()
