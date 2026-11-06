#!/usr/bin/env python3
"""
创建数据库索引（SKILL 02 §3）— 幂等，可重复运行

包含：
  - 向量 IVFFlat 索引（content_vector，cosine）——建议在数据导入后运行效果最佳
  - 中文全文检索 GIN 索引（按 settings.FTS_CONFIG 选择 chinese / simple）
  - pg_trgm 设备型号模糊索引
  - 各业务表 / 知识图谱表 btree 索引

用法:
  python3 scripts/create_indexes.py          # 用 .env 的 FTS_CONFIG
  python3 scripts/create_indexes.py --lists 100

注意:
  - IVFFlat 在空表上可创建但需有数据后才有意义；seed 完成后重跑本脚本即可。
  - 全文 GIN 索引的解析配置必须与 vector_store 查询时一致（都读 settings.FTS_CONFIG）。
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import argparse


def build_statements(fts_cfg: str, lists: int) -> list[tuple[str, str]]:
    """返回 (说明, SQL) 列表；全部 CREATE INDEX IF NOT EXISTS 幂等"""
    return [
        # ---------------- knowledge_base ----------------
        ("知识库向量 IVFFlat(cosine)",
         f"CREATE INDEX IF NOT EXISTS idx_kb_vector ON knowledge_base "
         f"USING ivfflat (content_vector vector_cosine_ops) WITH (lists = {lists})"),
        ("知识库内容全文 GIN",
         f"CREATE INDEX IF NOT EXISTS idx_kb_content_fts ON knowledge_base "
         f"USING gin (to_tsvector('{fts_cfg}', content))"),
        ("知识库设备型号 btree",
         "CREATE INDEX IF NOT EXISTS idx_kb_device_model ON knowledge_base (device_model)"),
        ("知识库设备型号 trgm",
         "CREATE INDEX IF NOT EXISTS idx_kb_device_model_trgm ON knowledge_base "
         "USING gin (device_model gin_trgm_ops)"),
        ("知识库设备类型 btree",
         "CREATE INDEX IF NOT EXISTS idx_kb_device_type ON knowledge_base (device_type_id)"),
        # ---------------- cases ----------------
        ("案例状态 btree",
         "CREATE INDEX IF NOT EXISTS idx_cases_status ON cases (status)"),
        ("案例设备类型 btree",
         "CREATE INDEX IF NOT EXISTS idx_cases_device ON cases (device_type_id)"),
        # ---------------- repair_records ----------------
        ("检修记录工人 btree",
         "CREATE INDEX IF NOT EXISTS idx_records_worker ON repair_records (worker_id)"),
        # ---------------- feedbacks ----------------
        ("反馈已采纳 btree",
         "CREATE INDEX IF NOT EXISTS idx_feedback_adopted ON feedbacks (is_adopted)"),
        # ---------------- workflow_templates ----------------
        ("作业模板设备+等级 btree",
         "CREATE INDEX IF NOT EXISTS idx_wf_device_level ON workflow_templates (device_type_id, repair_level)"),
        # ---------------- kg_entities / kg_relations ----------------
        ("KG 实体类型 btree",
         "CREATE INDEX IF NOT EXISTS idx_kg_entities_type ON kg_entities (entity_type)"),
        ("KG 实体名全文 GIN",
         f"CREATE INDEX IF NOT EXISTS idx_kg_entities_name_gin ON kg_entities "
         f"USING gin (to_tsvector('{fts_cfg}', name))"),
        ("KG 关系 subject btree",
         "CREATE INDEX IF NOT EXISTS idx_kg_rel_subject ON kg_relations (subject_id)"),
        ("KG 关系 object btree",
         "CREATE INDEX IF NOT EXISTS idx_kg_rel_object ON kg_relations (object_id)"),
    ]


async def create_indexes(lists: int):
    from app.database import engine
    from app.config import settings
    from sqlalchemy import text

    fts_cfg = settings.FTS_CONFIG or "simple"
    print(f"[INFO] FTS_CONFIG = {fts_cfg} | IVFFlat lists = {lists}")

    stmts = build_statements(fts_cfg, lists)
    ok, fail = 0, 0
    async with engine.begin() as conn:
        # trgm 索引需要 pg_trgm 扩展
        try:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        except Exception as e:
            print(f"[WARN] pg_trgm 扩展启用失败（trgm 索引可能跳过）: {_short(e)}")

        for desc, sql in stmts:
            try:
                await conn.execute(text(sql))
                print(f"[OK]   {desc}")
                ok += 1
            except Exception as e:
                # GIN(chinese) 在无 zhparser 环境会失败 → 自动降级 simple 重试
                if "to_tsvector('" + fts_cfg + "'" in sql and fts_cfg != "simple":
                    try:
                        await conn.execute(text(sql.replace(f"'{fts_cfg}'", "'simple'")))
                        print(f"[OK*]  {desc}（chinese 不可用，降级 simple）")
                        ok += 1
                        continue
                    except Exception as e2:
                        e = e2
                print(f"[FAIL] {desc}: {_short(e)}")
                fail += 1

    print(f"\n[DONE] 索引创建完成：成功 {ok}，失败 {fail}")
    print("[TIP]  IVFFlat 建议在种子数据导入后重跑本脚本，使聚类中心覆盖真实数据分布。")


def _short(e: Exception, n: int = 160) -> str:
    s = str(e).strip().splitlines()[0]
    return (s[:n] + "...") if len(s) > n else s


def main():
    parser = argparse.ArgumentParser(description="创建数据库索引（SKILL 02 §3）")
    parser.add_argument("--lists", type=int, default=100, help="IVFFlat 聚类数（默认 100）")
    args = parser.parse_args()
    asyncio.run(create_indexes(args.lists))


if __name__ == "__main__":
    main()
