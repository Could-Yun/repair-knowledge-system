"""
知识图谱服务：三元组抽取 → 写入 kg_entities + kg_relations
创新点 B（GraphRAG）：query_subgraph 让知识图谱参与故障诊断推理并可视化。
"""
from typing import Optional
from app.database import async_session
from app.models.kg import KgEntity, KgRelation
from app.utils.logger import logger
from sqlalchemy import select, or_, text
import uuid as uuid_mod


# 谓词 → 可读中文（用于推理路径文本与前端图例）
PREDICATE_ZH = {
    "has_component": "包含部件",
    "symptom_of":    "是其症状",
    "caused_by":     "由…引起",
    "solved_by":     "可通过…解决",
    "requires_tool": "需要工具",
    "part_of":       "属于",
    "related_to":    "相关于",
}


class KGService:
    async def extract_and_store(self, text: str, source_case_id: Optional[str] = None):
        from app.services.llm_service import LLMService
        llm = LLMService()
        triplets = await llm.extract_triplets(text)
        if not triplets:
            return

        async with async_session() as db:
            for t in triplets:
                if t.get("confidence", 0) < 0.6:
                    continue
                try:
                    subj_id = await self._upsert_entity(db, t["subject"], t.get("subject_type", "component"), source_case_id)
                    obj_id  = await self._upsert_entity(db, t["object"],  t.get("object_type",  "component"), source_case_id)
                    pred    = t.get("predicate", "related_to")
                    # 合法谓词校验
                    valid_preds = {"has_component","symptom_of","caused_by","solved_by","requires_tool","related_to","part_of"}
                    if pred not in valid_preds:
                        pred = "related_to"

                    # 关系去重（ON CONFLICT DO NOTHING）
                    exists = (await db.execute(
                        select(KgRelation).where(
                            KgRelation.subject_id == subj_id,
                            KgRelation.predicate   == pred,
                            KgRelation.object_id   == obj_id,
                        )
                    )).scalar_one_or_none()
                    if not exists:
                        rel = KgRelation(
                            subject_id=subj_id, predicate=pred, object_id=obj_id,
                            confidence=t.get("confidence", 0.8),
                            source_case_id=source_case_id,
                        )
                        db.add(rel)
                except Exception as e:
                    logger.warning(f"KG 三元组写入失败: {t} | {e}")

            await db.commit()
            logger.info(f"KG 抽取完成: source={source_case_id} triplets={len(triplets)}")

    # ------------------------------------------------------------------
    # 创新点 B：GraphRAG —— 按故障查询命中图谱实体并做一跳邻居扩展
    # ------------------------------------------------------------------
    async def query_subgraph(self, query: str, max_seeds: int = 6, max_edges: int = 30) -> dict:
        """
        根据故障描述在知识图谱中检索关联子图：
          1. 找出"名字出现在查询文本里"的种子实体（症状/部件/设备等）；
          2. 沿关系做一跳扩展，得到可能原因/处置/工具；
          3. 返回 {entities, relations, context}。context 为可注入 LLM 的推理线索文本。
        图谱为空或无命中时返回空结构（诊断照常进行，graceful degrade）。
        """
        q = (query or "").strip()
        if len(q) < 2:
            return {"entities": [], "relations": [], "context": ""}
        try:
            async with async_session() as db:
                # 1) 种子实体：实体名是查询文本的子串（中文子串匹配，无需分词）
                seed_rows = (await db.execute(
                    text("""
                        SELECT id, entity_type, name
                        FROM kg_entities
                        WHERE position(name in :q) > 0 AND char_length(name) >= 2
                        ORDER BY char_length(name) DESC
                        LIMIT :lim
                    """),
                    {"q": q, "lim": max_seeds},
                )).mappings().all()
                if not seed_rows:
                    return {"entities": [], "relations": [], "context": ""}

                seed_ids = [r["id"] for r in seed_rows]

                # 2) 一跳扩展：取与种子相连的关系
                rels = (await db.execute(
                    select(KgRelation).where(
                        or_(KgRelation.subject_id.in_(seed_ids),
                            KgRelation.object_id.in_(seed_ids))
                    ).limit(max_edges)
                )).scalars().all()

                # 收集所有涉及到的实体 id（种子 + 邻居）
                ent_ids = set(seed_ids)
                for r in rels:
                    ent_ids.add(r.subject_id)
                    ent_ids.add(r.object_id)

                ents = (await db.execute(
                    select(KgEntity).where(KgEntity.id.in_(list(ent_ids)))
                )).scalars().all()
                name_of = {e.id: e.name for e in ents}
                seed_id_set = set(seed_ids)

            entities = [
                {"id": str(e.id), "type": e.entity_type, "name": e.name,
                 "is_seed": e.id in seed_id_set}
                for e in ents
            ]
            relations = []
            context_lines = []
            for r in rels:
                s_name = name_of.get(r.subject_id, "?")
                o_name = name_of.get(r.object_id, "?")
                pred_zh = PREDICATE_ZH.get(r.predicate, r.predicate)
                relations.append({
                    "subject": str(r.subject_id), "object": str(r.object_id),
                    "predicate": r.predicate, "predicate_zh": pred_zh,
                    "subject_name": s_name, "object_name": o_name,
                })
                context_lines.append(f"{s_name} —[{pred_zh}]→ {o_name}")

            context = "\n".join(dict.fromkeys(context_lines))  # 去重保序
            logger.info(f"KG query_subgraph | seeds={len(seed_rows)} edges={len(relations)}")
            return {"entities": entities, "relations": relations, "context": context}
        except Exception as e:
            logger.warning(f"KG 子图检索失败（诊断将不使用图谱）: {e}")
            return {"entities": [], "relations": [], "context": ""}

    @staticmethod
    async def _upsert_entity(db, name: str, entity_type: str, source_case_id: Optional[str]) -> uuid_mod.UUID:
        valid_types = {"device","component","symptom","cause","solution","tool","part"}
        if entity_type not in valid_types:
            entity_type = "component"

        result = await db.execute(
            select(KgEntity).where(KgEntity.entity_type == entity_type, KgEntity.name == name)
        )
        existing = result.scalar_one_or_none()
        if existing:
            return existing.id

        entity = KgEntity(entity_type=entity_type, name=name, source_case_id=source_case_id)
        db.add(entity)
        await db.flush()  # 获取 id（不 commit，由调用方统一 commit）
        return entity.id
