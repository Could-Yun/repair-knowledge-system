from fastapi import APIRouter, Depends, HTTPException, Body, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from datetime import datetime
from typing import Optional
from app.database import get_db, async_session
from app.models.user import User
from app.models.case import Case
from app.models.device import DeviceType
from app.utils.deps import get_current_admin
from app.utils.logger import logger

router = APIRouter(prefix="/api/audit", tags=["audit"])


async def _ingest_case_bg(case_id: str):
    """后台把已通过案例向量化入库 + 抽知识图谱（embedding/LLM 较慢，放后台避免阻塞审核请求）。"""
    try:
        async with async_session() as db:
            c = (await db.execute(select(Case).where(Case.id == case_id))).scalar_one_or_none()
            if c:
                from app.services.vector_store import VectorStore
                await VectorStore().ingest_case(c)
                logger.info(f"案例后台入库完成 case={case_id}")
    except Exception as e:
        logger.error(f"案例后台入库失败 case={case_id}: {e}")

@router.get("/pending")
async def list_audit(
    page:    int = 1,
    size:    int = 10,
    status:  Optional[str] = "pending",
    keyword: Optional[str] = None,
    admin:   User = Depends(get_current_admin),
    db:      AsyncSession = Depends(get_db),
):
    conds = []
    if status:
        conds.append(Case.status == status)
    if keyword:
        conds.append(or_(Case.title.ilike(f"%{keyword}%"), Case.fault_phenomenon.ilike(f"%{keyword}%")))

    q = select(Case, DeviceType.name.label("dname"), User.username.label("uname")).outerjoin(
        DeviceType, Case.device_type_id == DeviceType.id
    ).outerjoin(
        User, Case.submitter_id == User.id
    ).where(and_(*conds) if conds else True).order_by(Case.created_at.desc()).offset((page-1)*size).limit(size)
    rows = (await db.execute(q)).all()
    total_q = await db.execute(select(func.count()).select_from(Case).where(and_(*conds) if conds else True))

    items = []
    for row in rows:
        c = row[0]
        items.append({
            "id": str(c.id), "title": c.title,
            "fault_phenomenon": c.fault_phenomenon, "fault_reason": c.fault_reason,
            "solution": c.solution, "tools_used": c.tools_used, "images": c.images,
            "status": c.status, "review_comment": c.review_comment,
            "created_at": c.created_at.isoformat(),
            "device_type_name": row[1], "submitter_name": row[2],
        })
    return {"items": items, "total": total_q.scalar(), "page": page, "size": size}

@router.post("/{case_id}/approve")
async def approve(
    case_id: str,
    background: BackgroundTasks,
    comment: str = Body("", embed=True),
    admin:   User = Depends(get_current_admin),
    db:      AsyncSession = Depends(get_db),
):
    c = (await db.execute(select(Case).where(Case.id == case_id))).scalar_one_or_none()
    if not c: raise HTTPException(404, "案例不存在")
    # 幂等：已通过的重复点击直接返回成功，不再报 400（避免"操作失败"误报）
    if c.status == "approved":
        return {"ok": True, "case_id": case_id, "idempotent": True}
    if c.status != "pending":
        raise HTTPException(400, "案例已被拒绝，无法通过")

    c.status = "approved"
    c.reviewer_id = admin.id
    c.review_comment = comment
    c.reviewed_at = datetime.utcnow()
    await db.commit()

    # 向量化入库 + 知识图谱抽取放后台执行（慢操作不阻塞审核响应，秒回）
    background.add_task(_ingest_case_bg, str(c.id))

    return {"ok": True, "case_id": case_id}

@router.post("/{case_id}/reject")
async def reject(
    case_id: str,
    comment: str = Body(..., embed=True),
    admin:   User = Depends(get_current_admin),
    db:      AsyncSession = Depends(get_db),
):
    c = (await db.execute(select(Case).where(Case.id == case_id))).scalar_one_or_none()
    if not c: raise HTTPException(404, "案例不存在")
    if c.status != "pending": raise HTTPException(400, "案例已审核")

    c.status = "rejected"
    c.reviewer_id = admin.id
    c.review_comment = comment
    c.reviewed_at = datetime.utcnow()
    await db.commit()
    return {"ok": True}

@router.get("/{case_id}")
async def get_case_detail(
    case_id: str,
    admin:   User = Depends(get_current_admin),
    db:      AsyncSession = Depends(get_db),
):
    c = (await db.execute(select(Case).where(Case.id == case_id))).scalar_one_or_none()
    if not c: raise HTTPException(404, "案例不存在")
    return c
