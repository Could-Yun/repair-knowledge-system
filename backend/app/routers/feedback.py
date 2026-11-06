from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.user import User
from app.models.feedback import Feedback
from app.schemas.feedback import FeedbackIn
from app.utils.deps import get_current_user, get_current_admin

router = APIRouter(prefix="/api/feedback", tags=["feedback"])

@router.post("")
async def submit_feedback(
    body: FeedbackIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    fb = Feedback(
        user_id=current_user.id,
        record_id=body.record_id,
        original_output=body.original_output,
        user_correction=body.user_correction,
        correction_type=body.correction_type,
    )
    db.add(fb)
    await db.commit()
    return {"ok": True, "id": str(fb.id)}

@router.get("")
async def list_feedback(
    page: int = 1,
    size: int = 20,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(Feedback).where(Feedback.user_id == current_user.id).order_by(Feedback.created_at.desc()).offset((page-1)*size).limit(size)
    items = (await db.execute(q)).scalars().all()
    return {"items": [{"id": str(f.id), "correction_type": f.correction_type, "user_correction": f.user_correction, "is_adopted": f.is_adopted, "created_at": f.created_at.isoformat()} for f in items], "total": len(items)}

@router.get("/pending")
async def list_pending_feedback(
    page: int = 1,
    size: int = 20,
    _admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """管理员查看待采纳反馈（反馈闭环 SKILL 07 §5）"""
    q = select(Feedback).where(Feedback.is_adopted == False).order_by(Feedback.created_at.desc()).offset((page-1)*size).limit(size)
    items = (await db.execute(q)).scalars().all()
    return {"items": [{"id": str(f.id), "correction_type": f.correction_type, "original_output": f.original_output, "user_correction": f.user_correction, "created_at": f.created_at.isoformat()} for f in items], "total": len(items)}

@router.post("/{feedback_id}/adopt")
async def adopt_feedback(
    feedback_id: str,
    _admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    管理员采纳反馈 → is_adopted=true，闭合反馈环：
    采纳后的修正会在后续诊断中注入 system prompt（SKILL 07 §5）
    """
    fb = (await db.execute(select(Feedback).where(Feedback.id == feedback_id))).scalar_one_or_none()
    if not fb:
        raise HTTPException(status_code=404, detail="反馈不存在")
    fb.is_adopted = True
    await db.commit()
    return {"ok": True, "id": str(fb.id), "is_adopted": True}
