"""
向量检索服务：pgvector + PostgreSQL 全文检索三路融合
权重：向量相似度 0.7 + 全文检索 0.3
"""
from typing import List, Optional, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select
from app.database import async_session
from app.services.embedding import EmbeddingService
from app.utils.logger import logger
import time


class VectorStore:
    def __init__(self):
        self.emb = EmbeddingService()

    async def hybrid_search(
        self,
        query: str,
        top_k: int = 5,
        device_model: Optional[str] = None,
        device_type_id: Optional[str] = None,
    ) -> List[dict]:
        """三路融合检索：向量相似度 + 全文检索，应用层加权合并"""
        t0 = time.time()
        query_vec = await self.emb.encode(query)

        async with async_session() as db:
            # 路径 1：向量相似度检索
            vec_results = await self._vector_search(db, query_vec, top_k * 2, device_type_id)

            # 路径 2：全文检索（PostgreSQL tsquery，兼容 zhparser 分词）
            fts_results = await self._fulltext_search(db, query, top_k * 2, device_model, device_type_id)

        # 融合去重
        merged = self._merge_results(vec_results, fts_results, top_k, w_vec=0.7, w_fts=0.3)

        logger.info(f"hybrid_search | query_len={len(query)} | top_k={top_k} | latency={time.time()-t0:.3f}s | results={len(merged)}")
        return merged

    async def _vector_search(self, db: AsyncSession, query_vec: List[float], top_k: int, device_type_id: Optional[str]) -> List[dict]:
        vec_str  = "[" + ",".join(str(v) for v in query_vec) + "]"
        base_sql = """
            SELECT id, title, content, image_urls, device_model, tags, source_type, source_id, page_no, created_at,
                   1 - (content_vector <=> CAST(:qv AS vector)) AS score
            FROM knowledge_base
            WHERE content_vector IS NOT NULL
        """
        params: dict = {"qv": vec_str, "top_k": top_k}
        if device_type_id:
            base_sql += " AND device_type_id = :dtid"
            params["dtid"] = device_type_id
        base_sql += " ORDER BY content_vector <=> CAST(:qv AS vector) LIMIT :top_k"
        rows = (await db.execute(text(base_sql), params)).mappings().all()
        return [dict(r) for r in rows]

    async def _fulltext_search(self, db: AsyncSession, query: str, top_k: int, device_model: Optional[str], device_type_id: Optional[str]) -> List[dict]:
        """
        全文检索：
        - V11 生产环境：FTS_CONFIG='chinese' （zhparser，SKILL 02 §3）
        - 本地开发环境：FTS_CONFIG='simple'  （PG 默认，配合 ILIKE 兜底）
        """
        from app.config import settings
        fts_cfg = settings.FTS_CONFIG  # 'chinese' | 'simple'

        sql = f"""
            SELECT id, title, content, image_urls, device_model, tags, source_type, source_id, page_no, created_at,
                   ts_rank(to_tsvector('{fts_cfg}', content), plainto_tsquery('{fts_cfg}', :q)) AS score
            FROM knowledge_base
            WHERE to_tsvector('{fts_cfg}', content) @@ plainto_tsquery('{fts_cfg}', :q)
               OR content ILIKE :like_q
        """
        params: dict = {"q": query, "like_q": f"%{query[:50]}%", "top_k": top_k}
        if device_model:
            sql += " AND device_model ILIKE :dm"
            params["dm"] = f"%{device_model}%"
        if device_type_id:
            sql += " AND device_type_id = :dtid"
            params["dtid"] = device_type_id
        sql += " ORDER BY score DESC LIMIT :top_k"
        try:
            rows = (await db.execute(text(sql), params)).mappings().all()
            return [dict(r) for r in rows]
        except Exception as e:
            # zhparser 缺失时自动降级 simple（避免一次升级把所有请求打挂）
            if fts_cfg != "simple":
                logger.warning(f"全文检索（{fts_cfg}）失败，降级 simple: {e}")
                try:
                    fallback_sql = sql.replace(f"'{fts_cfg}'", "'simple'")
                    rows = (await db.execute(text(fallback_sql), params)).mappings().all()
                    return [dict(r) for r in rows]
                except Exception as e2:
                    logger.warning(f"simple 兜底也失败: {e2}")
            else:
                logger.warning(f"全文检索失败: {e}")
            return []

    @staticmethod
    def _merge_results(vec: List[dict], fts: List[dict], top_k: int, w_vec: float = 0.7, w_fts: float = 0.3) -> List[dict]:
        scores: dict[str, float] = {}
        items:  dict[str, dict]  = {}

        for r in vec:
            rid = str(r["id"])
            scores[rid] = scores.get(rid, 0) + w_vec * float(r.get("score") or 0)
            items[rid]  = r

        fts_max = max((float(r.get("score") or 0) for r in fts), default=1) or 1
        for r in fts:
            rid = str(r["id"])
            normalized = float(r.get("score") or 0) / fts_max
            scores[rid] = scores.get(rid, 0) + w_fts * normalized
            if rid not in items:
                items[rid] = r

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
        result = []
        for rid, score in ranked:
            item = dict(items[rid])
            item["score"] = round(score, 4)
            item["id"]    = str(item["id"])
            if item.get("source_id") is not None:
                item["source_id"] = str(item["source_id"])
            # 格式化时间
            if item.get("created_at"):
                item["created_at"] = item["created_at"].isoformat() if hasattr(item["created_at"], "isoformat") else str(item["created_at"])
            # ARRAY 字段
            item["image_urls"] = list(item.get("image_urls") or [])
            item["tags"]       = list(item.get("tags")       or [])
            result.append(item)
        return result

    async def rag_search(self, query: str, top_k: int = 3, device_type_id: Optional[str] = None) -> dict:
        """供诊断接口调用：返回 answer + sources"""
        sources = await self.hybrid_search(query, top_k=top_k, device_type_id=device_type_id)
        return {"sources": sources}

    @staticmethod
    async def build_feedback_context(limit: int = 5) -> str:
        """
        反馈闭环（SKILL 07 §5）：取近 30 天 is_adopted=TRUE 的人工修正，
        拼成可注入诊断 system prompt 的文本。无则返回空串。
        """
        sql = text("""
            SELECT original_output, user_correction, correction_type
            FROM feedbacks
            WHERE is_adopted = TRUE
              AND created_at >= NOW() - INTERVAL '30 days'
            ORDER BY created_at DESC
            LIMIT :limit
        """)
        try:
            async with async_session() as db:
                rows = (await db.execute(sql, {"limit": limit})).mappings().all()
        except Exception as e:
            logger.warning(f"读取反馈修正失败（非阻塞）: {e}")
            return ""
        if not rows:
            return ""
        parts = []
        for i, r in enumerate(rows, 1):
            parts.append(
                f"{i}. [类型:{r['correction_type']}] 修正：{(r['user_correction'] or '').strip()[:200]}"
            )
        return "\n".join(parts)

    async def ingest_case(self, case: Any):
        """审核通过案例 → 写入 knowledge_base + 向量化"""
        from app.models.knowledge import KnowledgeBase

        # 拼接内容（文本 + 图片描述合并向量化）
        content = f"{case.fault_phenomenon}\n{case.fault_reason or ''}\n{case.solution}"

        # 内容判重：正文完全相同则跳过，避免同义块反复占用 Top-K 名额（缺陷 D-04 的源头治理）。
        # 放在 encode 之前，命中时连向量计算一并省掉。
        async with async_session() as db:
            dup = (await db.execute(
                select(KnowledgeBase.id).where(KnowledgeBase.content == content).limit(1)
            )).scalar_one_or_none()
        if dup:
            logger.info(f"案例内容与已有知识完全相同，跳过入库: case_id={case.id} 命中 kb_id={dup}")
            return

        vec = await self.emb.encode(content)

        kb = KnowledgeBase(
            source_type="case",
            source_id=case.id,
            title=case.title,
            content=content,
            content_vector=vec,
            image_urls=case.images,
            device_type_id=case.device_type_id,
            tags=case.tools_used,
        )

        async with async_session() as db:
            db.add(kb)
            await db.commit()
            logger.info(f"案例入库: case_id={case.id} kb_id={kb.id}")

        # 触发 KG 抽取（异步，不阻塞审核响应）
        try:
            from app.services.kg_service import KGService
            kg = KGService()
            await kg.extract_and_store(content, source_case_id=case.id)
        except Exception as e:
            logger.warning(f"KG 抽取失败（非阻塞）: {e}")
