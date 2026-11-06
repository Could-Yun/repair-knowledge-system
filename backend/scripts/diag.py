#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检索链路诊断脚本 —— 定位「检索返回空 / sources 为 0」的根因。

在 backend 目录下运行（需要能 import app.config）：
    python3 scripts/diag.py

它会依次检查：
  1. knowledge_base 表有多少行、多少行有向量、向量维度是多少
  2. 纯向量检索单独能不能返回结果
  3. 纯全文检索单独能不能返回结果
  4. 走 HTTP 打 /api/knowledge/search，打印**完整状态码与响应体**
     （之前 eval_quality.py 把非 200 当成了空结果，掩盖了真实错误）
  5. Embedding 后端实际用的是哪一路（llama.cpp / ONNX / DashScope / mock）
"""
import asyncio, os, sys, json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TEST_Q = ["火花塞间隙的标准值是多少", "气门间隙", "发动机怠速不稳，冷车启动困难"]


async def main():
    print("=" * 66)
    print("检索链路诊断")
    print("=" * 66)

    # ---------- 1. 数据库 ----------
    try:
        from sqlalchemy import text
        from app.database import async_session
        async with async_session() as db:
            q = await db.execute(text("""
                SELECT COUNT(*) AS total,
                       COUNT(content_vector) AS with_vec,
                       COUNT(*) FILTER (WHERE source_type='manual') AS manual,
                       COUNT(*) FILTER (WHERE source_type='case')   AS cases
                FROM knowledge_base"""))
            r = q.mappings().one()
            print("\n[1] knowledge_base")
            print("    总行数 %d   有向量 %d   手册块 %d   案例 %d"
                  % (r["total"], r["with_vec"], r["manual"], r["cases"]))
            if r["total"] == 0:
                print("    ✗ 知识库是空的！需要先跑 scripts/seed.sh 导入手册")
            elif r["with_vec"] == 0:
                print("    ✗ 有数据但**全部没有向量** → 向量检索必然返回空，")
                print("      只能靠全文检索兜底，这就是命中率低的根因")
            elif r["with_vec"] < r["total"]:
                print("    ⚠ 有 %d 行缺向量" % (r["total"] - r["with_vec"]))

            if r["with_vec"]:
                d = await db.execute(text(
                    "SELECT vector_dims(content_vector) AS d FROM knowledge_base "
                    "WHERE content_vector IS NOT NULL LIMIT 1"))
                dim = d.scalar()
                print("    向量维度 %s %s" % (dim, "✓" if dim == 768 else "✗ 应为 768，维度错配会导致检索失效"))

            # ---------- 1b. 存量向量是真是假 ----------
            if r["with_vec"] >= 10:
                print("\n[1b] 存量向量健康度（判断入库时用的是真实 Embedding 还是 MOCK 随机向量）")
                pair = await db.execute(text("""
                    WITH s AS (SELECT content_vector v FROM knowledge_base
                               WHERE content_vector IS NOT NULL LIMIT 40)
                    SELECT AVG(1 - (a.v <=> b.v)) AS avg_sim,
                           MIN(1 - (a.v <=> b.v)) AS min_sim,
                           MAX(1 - (a.v <=> b.v)) AS max_sim
                    FROM s a, s b WHERE a.v <> b.v"""))
                pr = pair.mappings().one()
                avg = float(pr["avg_sim"] or 0)
                print("    同库任意两条的余弦相似度：均值 %.3f  最小 %.3f  最大 %.3f"
                      % (avg, float(pr["min_sim"] or 0), float(pr["max_sim"] or 0)))
                if abs(avg) < 0.15:
                    print("    ✗ 均值接近 0 → 存量向量是 MOCK 随机向量，必须重算")
                    print("      （768 维随机向量两两近似正交，相似度必然≈0）")
                else:
                    print("    ✓ 均值显著大于 0 → 存量向量是真实 Embedding")
                    print("      （同一本手册的知识块语义相近，真实向量相似度通常 0.3~0.8）")
                    print("      → 只需修复**查询侧**的 Embedding，无需重算存量向量")

            # ---------- 1c. 存量向量是哪个模型生成的 ----------
            print("\n[1c] 存量向量的生成时间分布（用于判断当初用的是哪个 Embedding 模型）")
            days = await db.execute(text("""
                SELECT to_char(created_at,'YYYY-MM-DD') AS d, COUNT(*) AS n,
                       COUNT(content_vector) AS v
                FROM knowledge_base GROUP BY 1 ORDER BY 1"""))
            for x in days.mappings().all():
                print("    %s  入库 %3d 行，其中 %3d 行有向量" % (x["d"], x["n"], x["v"]))
            print("    ⚠ 请把上面的日期与启动日志里的 Embedding 模式对照：")
            print("      grep -h 'Embedding 模式' logs/app*.log | sort -u")
            print("      · 若入库时是 LOCAL_HTTP(llama.cpp/BGE) → 查询侧也必须用 BGE，")
            print("        换成云端 text-embedding-v3 会因**向量空间不同**而检索失效；")
            print("      · 若要改用云端，必须用 revectorize.py --apply 把存量向量整体重算。")

            # 索引
            ix = await db.execute(text(
                "SELECT indexname FROM pg_indexes WHERE tablename='knowledge_base'"))
            names = [x[0] for x in ix.fetchall()]
            print("    索引：%s" % ", ".join(names))

            # ---------- 2/3. 两路检索单独测 ----------
            print("\n[2] 纯向量检索 / [3] 纯全文检索（各取 Top-3）")
            from app.services.embedding import EmbeddingService
            from app.config import settings
            emb = EmbeddingService()
            for qq in TEST_Q:
                print("\n  查询：%s" % qq)
                try:
                    vec = await emb.encode(qq)
                    print("    embedding 维度 %d，前 3 维 %s" % (len(vec), [round(x, 4) for x in vec[:3]]))
                except Exception as e:
                    print("    ✗ embedding 失败：%s" % e); continue
                vs = "[" + ",".join(str(v) for v in vec) + "]"
                try:
                    rows = (await db.execute(text("""
                        SELECT title, 1-(content_vector <=> CAST(:qv AS vector)) AS s
                        FROM knowledge_base WHERE content_vector IS NOT NULL
                        ORDER BY content_vector <=> CAST(:qv AS vector) LIMIT 3"""),
                        {"qv": vs})).mappings().all()
                    print("    向量检索 %d 条：%s" % (len(rows),
                          [(x["title"][:16], round(x["s"], 3)) for x in rows]))
                except Exception as e:
                    print("    ✗ 向量检索报错：%s" % str(e)[:150])
                cfg = settings.FTS_CONFIG
                try:
                    rows = (await db.execute(text(f"""
                        SELECT title, ts_rank(to_tsvector('{cfg}', content),
                               plainto_tsquery('{cfg}', :q)) AS s
                        FROM knowledge_base
                        WHERE to_tsvector('{cfg}', content) @@ plainto_tsquery('{cfg}', :q)
                        ORDER BY s DESC LIMIT 3"""), {"q": qq})).mappings().all()
                    print("    全文检索(%s) %d 条：%s" % (cfg, len(rows),
                          [(x["title"][:16], round(x["s"], 4)) for x in rows]))
                except Exception as e:
                    print("    ✗ 全文检索报错(%s)：%s" % (cfg, str(e)[:150]))
    except Exception as e:
        print("  ✗ 数据库检查失败：%s" % e)

    # ---------- 4. HTTP ----------
    print("\n[4] HTTP 接口实际返回（含状态码）")
    try:
        import httpx
        BASE = os.environ.get("BENCH_BASE", "http://127.0.0.1:8000")
        async with httpx.AsyncClient(trust_env=False, timeout=120) as cli:
            t = (await cli.post(f"{BASE}/api/auth/login",
                 json={"username": os.environ.get("BENCH_USER", "worker"),
                       "password": os.environ.get("BENCH_PASS", "worker123")})).json()
            H = {"Authorization": "Bearer " + t["access_token"]}
            for qq in TEST_Q[:2]:
                r = await cli.post(f"{BASE}/api/knowledge/search", headers=H,
                                   data={"query": qq, "top_k": 3})
                print("\n  查询：%s" % qq)
                print("    HTTP %d" % r.status_code)
                body = r.text[:400]
                print("    响应：%s" % body)
            r = await cli.post(f"{BASE}/api/diagnosis/analyze", headers=H,
                               data={"description": TEST_Q[2]})
            j = r.json() if r.status_code == 200 else {}
            print("\n  诊断：HTTP %d，sources %d 条，kg 实体 %d"
                  % (r.status_code, len(j.get("sources") or []),
                     len((j.get("kg_graph") or {}).get("entities") or [])))
            if not (j.get("sources")):
                print("    ✗ sources 为空 → 结论里的 [来源N] 无所指，属于幻觉标注")
            # 5. LLM 健康
            ta = (await cli.post(f"{BASE}/api/auth/login",
                  json={"username": os.environ.get("ADMIN_USER", "admin"),
                        "password": os.environ.get("ADMIN_PASS", "admin123")})).json()
            AH = {"Authorization": "Bearer " + ta["access_token"]}
            h = await cli.get(f"{BASE}/api/admin/health/llm", headers=AH)
            print("\n[5] 大模型/向量通道健康：HTTP %d\n    %s" % (h.status_code, h.text[:300]))
    except Exception as e:
        print("  ✗ HTTP 检查失败：%s" % e)

    print("\n" + "=" * 66)
    print("把以上完整输出复制给我即可定位")
    print("=" * 66)


if __name__ == "__main__":
    asyncio.run(main())
