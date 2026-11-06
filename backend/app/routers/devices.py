from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from typing import Optional
from app.database import get_db
from app.models.device import DeviceType
from app.models.user import User
from app.utils.deps import get_current_user, get_current_admin

router = APIRouter(prefix="/api/devices", tags=["devices"])

@router.get("")
async def list_devices(
    page: int = 1,
    size: int = 100,
    has_knowledge: bool = False,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """设备类型列表。
    has_knowledge=True 时（问题 #5）只返回知识库中确有知识的设备——诊断"以知识库为准"，
    故诊断页只暴露有知识可依的设备；上传/管理等场景仍用全量（默认 False）。
    """
    base = select(DeviceType)
    count_q = select(func.count()).select_from(DeviceType)
    if has_knowledge:
        from app.models.knowledge import KnowledgeBase
        sub = select(KnowledgeBase.device_type_id).where(
            KnowledgeBase.device_type_id.isnot(None)
        ).distinct()
        base = base.where(DeviceType.id.in_(sub))
        count_q = select(func.count()).select_from(DeviceType).where(DeviceType.id.in_(sub))
    q = base.order_by(DeviceType.name).offset((page-1)*size).limit(size)
    items = (await db.execute(q)).scalars().all()
    total = (await db.execute(count_q)).scalar()
    return {"items": [{"id": str(d.id), "name": d.name, "model_no": d.model_no, "category": d.category, "manufacturer": d.manufacturer, "created_at": d.created_at.isoformat()} for d in items], "total": total}

@router.get("/search")
async def search_devices(
    keyword: str,
    limit: int = 10,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(DeviceType).where(
        or_(DeviceType.name.ilike(f"%{keyword}%"), DeviceType.model_no.ilike(f"%{keyword}%"))
    ).limit(limit)
    items = (await db.execute(q)).scalars().all()
    return [{"id": str(d.id), "name": d.name, "model_no": d.model_no} for d in items]

@router.post("")
async def create_device(
    name: str,
    category: Optional[str] = None,
    model_no: Optional[str] = None,
    manufacturer: Optional[str] = None,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    d = DeviceType(name=name, category=category, model_no=model_no, manufacturer=manufacturer)
    db.add(d)
    await db.commit()
    await db.refresh(d)
    return {"id": str(d.id), "name": d.name}
