from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from typing import Optional, List
from app.database import get_db
from app.models.user import User
from app.models.case import Case
from app.models.device import DeviceType
from app.utils.deps import get_current_user

router = APIRouter(prefix="/api/cases", tags=["cases"])

@router.post("")
async def create_case(
    title:            str = Form(...),
    fault_phenomenon: str = Form(...),
    solution:         str = Form(...),
    fault_reason:     Optional[str] = Form(None),
    device_type_id:   Optional[str] = Form(None),
    tools_used:       List[str] = Form(default=[]),
    images:           List[UploadFile] = File(default=[]),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.services.file_service import FileService
    fs = FileService()
    image_paths = []
    for img in images:
        path = await fs.save_upload(img, current_user.id, related_type="case")
        image_paths.append(path)

    case = Case(
        submitter_id=current_user.id,
        device_type_id=device_type_id,
        title=title,
        fault_phenomenon=fault_phenomenon,
        fault_reason=fault_reason,
        solution=solution,
        tools_used=tools_used if tools_used else None,
        images=image_paths if image_paths else None,
        status="pending",
    )
    db.add(case)
    await db.commit()
    await db.refresh(case)
    return {"id": str(case.id), "status": case.status}

@router.get("/my")
async def my_cases(
    status:   Optional[str] = None,
    page:     int = 1,
    size:     int = 10,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    conds = [Case.submitter_id == current_user.id]
    if status:
        conds.append(Case.status == status)

    q = select(Case, DeviceType.name.label("device_type_name")).outerjoin(
        DeviceType, Case.device_type_id == DeviceType.id
    ).where(and_(*conds)).order_by(Case.created_at.desc()).offset((page-1)*size).limit(size)
    rows = (await db.execute(q)).all()

    total = (await db.execute(select(func.count()).select_from(Case).where(and_(*conds)))).scalar()
    items = []
    for row in rows:
        c = row[0]
        items.append({
            "id": str(c.id), "title": c.title,
            "fault_phenomenon": c.fault_phenomenon, "solution": c.solution,
            "tools_used": c.tools_used, "images": c.images,
            "status": c.status, "review_comment": c.review_comment,
            "reviewed_at": c.reviewed_at.isoformat() if c.reviewed_at else None,
            "created_at": c.created_at.isoformat(),
            "device_type_name": row[1],
        })
    return {"items": items, "total": total, "page": page, "size": size}

@router.get("/{case_id}")
async def get_case(
    case_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(Case).where(Case.id == case_id)
    c = (await db.execute(q)).scalar_one_or_none()
    if not c:
        raise HTTPException(404, "案例不存在")
    if str(c.submitter_id) != str(current_user.id) and current_user.role != "admin":
        raise HTTPException(403, "无权访问")
    return c

@router.delete("/{case_id}")
async def delete_case(
    case_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    c = (await db.execute(select(Case).where(Case.id == case_id))).scalar_one_or_none()
    if not c:
        raise HTTPException(404, "案例不存在")
    if str(c.submitter_id) != str(current_user.id):
        raise HTTPException(403, "无权删除")
    if c.status != "pending":
        raise HTTPException(400, "已审核的案例不能删除")
    await db.delete(c)
    await db.commit()
    return {"ok": True}
