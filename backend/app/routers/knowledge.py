from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
import time
from app.database import get_db
from app.models.user import User
from app.models.knowledge import KnowledgeBase, SearchLog
from app.utils.deps import get_current_user

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])

@router.post("/search")
async def search_knowledge(
    query:          str = Form(...),
    device_model:   Optional[str] = Form(None),
    device_type_id: Optional[str] = Form(None),
    top_k:          int = Form(5),
    image: Optional[UploadFile] = File(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not query.strip():
        # 空 query（登录后页面自动探测 / 驾驶舱"最新知识"等）直接返回空结果，
        # 不再抛 400，避免前端弹"不支持纯图片检索"提示
        return {"items": [], "total": 0, "query": "", "search_time": 0}

    t0 = time.time()
    orig_query = query.strip()   # 记录用户原始检索词（不含图片描述增强）

    # 图片辅助理解：VL 模型生成描述
    if image:
        try:
            from app.services.llm_service import LLMService
            from app.services.file_service import FileService
            fs = FileService()
            llm = LLMService()
            path = await fs.save_upload(image, current_user.id, related_type="search")
            desc = await llm.describe_images([path])
            query = f"{query}\n[图片描述] {desc}"
        except Exception:
            pass

    from app.services.vector_store import VectorStore
    vs = VectorStore()
    results = await vs.hybrid_search(
        query=query,
        top_k=top_k,
        device_model=device_model,
        device_type_id=device_type_id,
    )

    # 记录检索历史（best-effort，失败不影响检索结果）
    try:
        db.add(SearchLog(
            user_id=current_user.id,
            query=orig_query[:1000],
            device_type_id=device_type_id or None,
            result_count=len(results),
            has_image=bool(image),
        ))
        await db.commit()
    except Exception:
        await db.rollback()

    return {
        "items": results,
        "total": len(results),
        "query": query,
        "search_time": round(time.time() - t0, 3),
    }


@router.get("/history")
async def search_history(
    page: int = 1, size: int = 20,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """当前用户的知识检索历史（最新在前）。"""
    from sqlalchemy import func as _func
    from app.models.device import DeviceType
    q = (
        select(SearchLog, DeviceType.name)
        .outerjoin(DeviceType, SearchLog.device_type_id == DeviceType.id)
        .where(SearchLog.user_id == current_user.id)
        .order_by(SearchLog.created_at.desc())
        .offset((page - 1) * size).limit(size)
    )
    rows = (await db.execute(q)).all()
    total = (await db.execute(
        select(_func.count()).select_from(SearchLog).where(SearchLog.user_id == current_user.id)
    )).scalar()
    return {
        "items": [{
            "id": str(s.id),
            "query": s.query,
            "device_type_name": dname,
            "result_count": s.result_count,
            "has_image": s.has_image,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        } for s, dname in rows],
        "total": total,
        "page": page, "size": size,
    }


@router.get("/{kb_id}")
async def get_kb_item(
    kb_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    kb = (await db.execute(select(KnowledgeBase).where(KnowledgeBase.id == kb_id))).scalar_one_or_none()
    if not kb: raise HTTPException(404, "知识条目不存在")
    return kb

@router.get("/{kb_id}/kg")
async def get_kg_for_kb(
    kb_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """返回与该知识条目相关的知识图谱节点和关系"""
    from app.models.kg import KgEntity, KgRelation
    kb = (await db.execute(select(KnowledgeBase).where(KnowledgeBase.id == kb_id))).scalar_one_or_none()
    if not kb: raise HTTPException(404, "知识条目不存在")

    # 通过 source_id 关联案例的知识图谱
    entities = []
    relations = []
    if kb.source_id:
        ents = (await db.execute(select(KgEntity).where(KgEntity.source_case_id == kb.source_id))).scalars().all()
        entities = [{"id": str(e.id), "type": e.entity_type, "name": e.name} for e in ents]
        if ents:
            ent_ids = [e.id for e in ents]
            from sqlalchemy import or_
            rels = (await db.execute(select(KgRelation).where(
                or_(KgRelation.subject_id.in_(ent_ids), KgRelation.object_id.in_(ent_ids))
            ))).scalars().all()
            relations = [{"subject": str(r.subject_id), "predicate": r.predicate, "object": str(r.object_id)} for r in rels]

    return {"entities": entities, "relations": relations}
