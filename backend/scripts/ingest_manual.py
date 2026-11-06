#!/usr/bin/env python3
"""
手册入库脚本：将 parse_manual.py 输出的 JSON 批量写入 knowledge_base 表
包含：向量化（BGE-base-zh-v1.5）+ 写入 PostgreSQL

用法:
  python3 scripts/ingest_manual.py \
      --input /tmp/chapters.json \
      --device-type "摩托车发动机"
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import asyncio
import argparse
import uuid

async def ingest(input_path: str, device_type_name: str):
    from app.database import async_session, engine, Base
    from app.models.knowledge import KnowledgeBase
    from app.models.device import DeviceType
    from app.services.embedding import EmbeddingService
    from sqlalchemy import select, text

    # 初始化数据库
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"'))
        await conn.run_sync(Base.metadata.create_all)

    with open(input_path, "r", encoding="utf-8") as f:
        chunks: list[dict] = json.load(f)
    print(f"[INFO] 加载 {len(chunks)} 段落块")

    emb = EmbeddingService()
    emb._load()

    async with async_session() as db:
        # 查找或创建设备类型
        result = await db.execute(select(DeviceType).where(DeviceType.name == device_type_name))
        device = result.scalar_one_or_none()
        if not device:
            device = DeviceType(name=device_type_name, category="摩托车", manufacturer="通用")
            db.add(device)
            await db.flush()
            print(f"[INFO] 创建设备类型: {device_type_name} ({device.id})")
        device_id = device.id

        # 批量入库（每批 16 条向量化）
        batch_size = 16
        total_inserted = 0
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]
            texts = [c["content"] for c in batch]
            vecs  = await emb.encode_batch(texts)

            for chunk, vec in zip(batch, vecs):
                # 检查是否已存在（幂等入库）
                existing = await db.execute(
                    select(KnowledgeBase).where(
                        KnowledgeBase.source_type == "manual",
                        KnowledgeBase.title == chunk["title"],
                        KnowledgeBase.device_type_id == device_id,
                    )
                )
                if existing.scalar_one_or_none():
                    continue

                kb = KnowledgeBase(
                    source_type="manual",
                    title=chunk["title"],
                    content=chunk["content"],
                    content_vector=vec,
                    image_urls=chunk.get("images") or None,
                    device_type_id=device_id,
                    device_model=chunk.get("device_model"),
                    tags=["摩托车发动机", "维修手册"],
                )
                db.add(kb)
                total_inserted += 1

            await db.commit()
            print(f"[INFO] 已处理 {min(i + batch_size, len(chunks))}/{len(chunks)} 块，累计入库 {total_inserted} 条")

    print(f"[DONE] 手册入库完成，共写入 {total_inserted} 条知识")

def main():
    parser = argparse.ArgumentParser(description="摩托车维修手册入库")
    parser.add_argument("--input",       default="/tmp/chapters.json")
    parser.add_argument("--device-type", default="摩托车发动机")
    args = parser.parse_args()
    asyncio.run(ingest(args.input, args.device_type))

if __name__ == "__main__":
    main()
