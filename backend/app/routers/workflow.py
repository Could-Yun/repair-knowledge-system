from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime
from typing import Optional, Any
from app.database import get_db
from app.models.user import User
from app.models.device import DeviceType
from app.models.workflow import WorkflowTemplate, RepairRecord, WorkflowRequest
from app.schemas.workflow import WorkflowTemplateIn
from app.utils.deps import get_current_user, get_current_admin
from app.utils.logger import logger

router = APIRouter(prefix="/api/workflow", tags=["workflow"])

@router.get("/recommend")
async def recommend(
    device_type_id: str,
    repair_level:   str,
    diagnosis_text: Optional[str] = None,
    top_k:          int = 3,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # 精确匹配
    q = select(WorkflowTemplate).where(
        WorkflowTemplate.device_type_id == device_type_id,
        WorkflowTemplate.repair_level == repair_level,
    ).order_by(WorkflowTemplate.updated_at.desc())
    candidates = list((await db.execute(q)).scalars().all())

    # 不足时回退到同设备其他等级
    if len(candidates) < top_k:
        level_order = {"major": 1, "minor": 2, "emergency": 3, "daily": 4}
        fallback = list((await db.execute(
            select(WorkflowTemplate).where(
                WorkflowTemplate.device_type_id == device_type_id,
                WorkflowTemplate.repair_level != repair_level,
            )
        )).scalars().all())
        fallback.sort(key=lambda w: level_order.get(w.repair_level, 5))
        candidates.extend(fallback[:top_k - len(candidates)])

    return [{"id": str(w.id), "name": w.name, "repair_level": w.repair_level, "steps": w.steps, "estimated_duration": w.estimated_duration} for w in candidates[:top_k]]

@router.get("/templates")
async def list_templates(
    device_type_id: Optional[str] = None,
    repair_level:   Optional[str] = None,
    page: int = 1,
    size: int = 20,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    conds = []
    if device_type_id: conds.append(WorkflowTemplate.device_type_id == device_type_id)
    if repair_level:   conds.append(WorkflowTemplate.repair_level == repair_level)
    from sqlalchemy import and_
    q = select(WorkflowTemplate, DeviceType.name.label("device_type_name")).outerjoin(
        DeviceType, WorkflowTemplate.device_type_id == DeviceType.id
    ).where(and_(*conds) if conds else True).order_by(WorkflowTemplate.updated_at.desc()).offset((page-1)*size).limit(size)
    rows = (await db.execute(q)).all()
    items = [{"id": str(r[0].id), "name": r[0].name, "repair_level": r[0].repair_level, "steps": r[0].steps, "estimated_duration": r[0].estimated_duration, "device_type_name": r[1], "created_at": r[0].created_at.isoformat()} for r in rows]
    total = (await db.execute(select(func.count()).select_from(WorkflowTemplate))).scalar()
    return {"items": items, "total": total, "page": page, "size": size}

@router.get("/templates/{tid}")
async def get_template(tid: str, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    w = (await db.execute(select(WorkflowTemplate).where(WorkflowTemplate.id == tid))).scalar_one_or_none()
    if not w: raise HTTPException(404, "模板不存在")
    return w

@router.post("/templates")
async def create_template(body: WorkflowTemplateIn, admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    w = WorkflowTemplate(**body.dict(), created_by=admin.id)
    db.add(w)
    await db.commit()
    await db.refresh(w)
    return w

@router.put("/templates/{tid}")
async def update_template(tid: str, body: WorkflowTemplateIn, admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    w = (await db.execute(select(WorkflowTemplate).where(WorkflowTemplate.id == tid))).scalar_one_or_none()
    if not w: raise HTTPException(404, "模板不存在")
    for k, v in body.dict(exclude_unset=True).items():
        setattr(w, k, v)
    await db.commit()
    return w

@router.delete("/templates/{tid}")
async def delete_template(tid: str, admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    w = (await db.execute(select(WorkflowTemplate).where(WorkflowTemplate.id == tid))).scalar_one_or_none()
    if not w: raise HTTPException(404, "模板不存在")
    await db.delete(w)
    await db.commit()
    return {"ok": True}

def _record_summary(steps_data) -> dict:
    """从 steps_data 提取留痕概况：步骤数、已勾选合规项数、照片数。"""
    executed = (steps_data or {}).get("executed") or []
    steps_total = len(executed)
    photo_count = 0
    checks_total = checks_done = 0
    for s in executed:
        photo_count += len(s.get("photos") or [])
        for c in (s.get("checks") or []):
            checks_total += 1
            if c.get("checked"):
                checks_done += 1
    return {"steps_total": steps_total, "photo_count": photo_count,
            "checks_total": checks_total, "checks_done": checks_done}


@router.get("/records")
async def list_records(
    scope: str = "mine",            # mine=自己的作业留痕；all=全部（仅管理员，用于核查）
    status: Optional[str] = None,   # in_progress | completed | paused
    source: str = "all",            # all=两类都看 | workflow=标准化作业 | diagnosis=排查后维修
    page: int = 1, size: int = 20,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """作业指引执行留痕列表。
    - scope=mine：当前用户自己的作业执行记录（一线/管理员都能看自己的）；
    - scope=all ：全部人员的记录（仅管理员，用于核查日常检修/清洗是否执行，含时间/照片/内容）。

    工单有两个来源，靠 workflow_template_id 区分，两者共用同一张 repair_records 表：
    - workflow ：标准化作业指引执行（模板非空），面向可预期的重复任务；
    - diagnosis：分步排查定论后的现场维修执行（模板为空），面向突发故障。
    source 缺省为 all，管理员一处即可核查全部现场作业。
    """
    from sqlalchemy import and_
    # 恒真占位：source=all 且 scope=all 时条件列表会为空，SQLAlchemy 2.0 的 and_() 不接受空参
    conds = [RepairRecord.id.isnot(None)]
    if source == "workflow":
        conds.append(RepairRecord.workflow_template_id.isnot(None))
    elif source == "diagnosis":
        conds.append(RepairRecord.workflow_template_id.is_(None))
    if scope == "all":
        if current_user.role != "admin":
            raise HTTPException(403, "仅管理员可查看全部作业记录")
    else:
        conds.append(RepairRecord.worker_id == current_user.id)
    if status in ("in_progress", "completed", "paused"):
        conds.append(RepairRecord.status == status)

    q = (
        select(RepairRecord, DeviceType.name, WorkflowTemplate.name, User.username)
        .outerjoin(DeviceType, RepairRecord.device_type_id == DeviceType.id)
        .outerjoin(WorkflowTemplate, RepairRecord.workflow_template_id == WorkflowTemplate.id)
        .outerjoin(User, RepairRecord.worker_id == User.id)
        .where(and_(*conds))
        .order_by(RepairRecord.started_at.desc())
        .offset((page - 1) * size).limit(size)
    )
    rows = (await db.execute(q)).all()
    total = (await db.execute(select(func.count()).select_from(RepairRecord).where(and_(*conds)))).scalar()

    items = []
    for r, dname, tname, uname in rows:
        src = "workflow" if r.workflow_template_id else "diagnosis"
        # 维修工单没有模板名，用 LLM 生成的作业名兜底，其次才是故障描述
        plan_title = (r.steps_data or {}).get("plan_title") if isinstance(r.steps_data, dict) else None
        items.append({
            "id": str(r.id),
            "source": src,
            "root_cause": ((r.steps_data or {}).get("root_cause") if isinstance(r.steps_data, dict) else None),
            "template_name": tname or plan_title or (r.fault_description or "作业"),
            "device_type_name": dname,
            "worker_name": uname,
            "status": r.status,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            **_record_summary(r.steps_data),
        })
    return {"items": items, "total": total, "page": page, "size": size}


@router.post("/records")
async def start_record(
    workflow_template_id: Optional[str] = Body(None, embed=True),
    device_type_id: Optional[str] = Body(None, embed=True),
    fault_description: Optional[str] = Body(None, embed=True),
    steps_data: Optional[Any] = Body(None, embed=True),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    r = RepairRecord(
        worker_id=current_user.id,
        workflow_template_id=workflow_template_id or None,
        device_type_id=device_type_id or None,
        fault_description=fault_description,
        steps_data=steps_data,
    )
    db.add(r)
    await db.commit()
    await db.refresh(r)
    return {"id": str(r.id)}

@router.put("/records/{rid}")
async def update_record(
    rid: str,
    steps_data: Optional[Any] = Body(None, embed=True),
    status: Optional[str] = Body(None, embed=True),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """创新点 D：持久化作业执行留痕（每步合规勾选、备注、拍照留证）。
    steps_data 结构示例：
      {"executed":[{"step":1,"title":"安全检查与断电","checks":[{"label":"已断电","checked":true}],
                    "note":"...","photos":["/uploads/.."],"done_at":"..."}],
       "current_idx":2}
    """
    r = (await db.execute(select(RepairRecord).where(
        RepairRecord.id == rid, RepairRecord.worker_id == current_user.id
    ))).scalar_one_or_none()
    if not r:
        raise HTTPException(404, "记录不存在")
    if steps_data is not None:
        r.steps_data = steps_data
    if status in ("in_progress", "completed", "paused"):
        r.status = status
        if status == "completed":
            r.completed_at = datetime.utcnow()
    await db.commit()
    return {"ok": True, "id": str(r.id)}


@router.get("/records/{rid}")
async def get_record(rid: str, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """读取检修工单（含留痕）。本人或管理员可看。"""
    r = (await db.execute(select(RepairRecord).where(RepairRecord.id == rid))).scalar_one_or_none()
    if not r:
        raise HTTPException(404, "记录不存在")
    if str(r.worker_id) != str(current_user.id) and current_user.role != "admin":
        raise HTTPException(403, "无权查看")
    return {
        "id": str(r.id),
        "device_type_id": str(r.device_type_id) if r.device_type_id else None,
        "workflow_template_id": str(r.workflow_template_id) if r.workflow_template_id else None,
        "fault_description": r.fault_description,
        "steps_data": r.steps_data,
        "status": r.status,
        "started_at": r.started_at.isoformat() if r.started_at else None,
        "completed_at": r.completed_at.isoformat() if r.completed_at else None,
    }


@router.post("/records/{rid}/complete")
async def complete_record(rid: str, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    r = (await db.execute(select(RepairRecord).where(RepairRecord.id == rid, RepairRecord.worker_id == current_user.id))).scalar_one_or_none()
    if not r: raise HTTPException(404, "记录不存在")
    r.status = "completed"
    r.completed_at = datetime.utcnow()
    await db.commit()
    return {"ok": True}


# ======================================================================
# 作业指引申请 → 审批 → AI 生成 → 发布（一线申请、管理员建标）
# ======================================================================
def _req_brief(r: WorkflowRequest, device_name=None, requester=None) -> dict:
    return {
        "id": str(r.id),
        "title": r.title,
        "description": r.description,
        "repair_level": r.repair_level,
        "status": r.status,
        "review_comment": r.review_comment,
        "device_type_id": str(r.device_type_id) if r.device_type_id else None,
        "device_type_name": device_name,
        "requester_name": requester,
        "template_id": str(r.template_id) if r.template_id else None,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "reviewed_at": r.reviewed_at.isoformat() if r.reviewed_at else None,
    }


@router.post("/requests")
async def create_request(
    title: str = Body(..., embed=True),
    repair_level: str = Body("daily", embed=True),
    device_type_id: Optional[str] = Body(None, embed=True),
    description: Optional[str] = Body(None, embed=True),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """一线人员申请一份尚不存在的标准化作业指引。"""
    if not (title or "").strip():
        raise HTTPException(400, "请填写作业任务名")
    if repair_level not in ("daily", "minor", "major", "emergency"):
        repair_level = "daily"
    r = WorkflowRequest(
        requester_id=current_user.id,
        device_type_id=device_type_id or None,
        repair_level=repair_level,
        title=title.strip()[:200],
        description=(description or "").strip() or None,
        status="pending",
    )
    db.add(r)
    await db.commit()
    await db.refresh(r)
    return {"ok": True, "id": str(r.id)}


@router.get("/requests/my")
async def my_requests(
    page: int = 1, size: int = 20,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(WorkflowRequest, DeviceType.name).outerjoin(
        DeviceType, WorkflowRequest.device_type_id == DeviceType.id
    ).where(WorkflowRequest.requester_id == current_user.id).order_by(
        WorkflowRequest.created_at.desc()
    ).offset((page-1)*size).limit(size)
    rows = (await db.execute(q)).all()
    total = (await db.execute(select(func.count()).select_from(WorkflowRequest).where(
        WorkflowRequest.requester_id == current_user.id))).scalar()
    return {"items": [_req_brief(r[0], device_name=r[1]) for r in rows], "total": total}


@router.get("/requests")
async def list_requests(
    page: int = 1, size: int = 20, status: str = "pending",
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """管理员：作业指引申请队列。"""
    conds = [WorkflowRequest.status == status] if status else []
    from sqlalchemy import and_
    q = select(WorkflowRequest, DeviceType.name, User.username).outerjoin(
        DeviceType, WorkflowRequest.device_type_id == DeviceType.id
    ).outerjoin(User, WorkflowRequest.requester_id == User.id).where(
        and_(*conds) if conds else True
    ).order_by(WorkflowRequest.created_at.desc()).offset((page-1)*size).limit(size)
    rows = (await db.execute(q)).all()
    total = (await db.execute(select(func.count()).select_from(WorkflowRequest).where(
        and_(*conds) if conds else True))).scalar()
    return {"items": [_req_brief(r[0], device_name=r[1], requester=r[2]) for r in rows], "total": total}


@router.post("/generate")
async def generate_workflow_draft(
    title: str = Body(..., embed=True),
    repair_level: str = Body("daily", embed=True),
    device_type_id: Optional[str] = Body(None, embed=True),
    description: Optional[str] = Body(None, embed=True),
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """管理员：基于知识库手册，用大模型生成作业指引步骤草稿（不落库，供审核编辑）。"""
    device_name = ""
    if device_type_id:
        dt = (await db.execute(select(DeviceType).where(DeviceType.id == device_type_id))).scalar_one_or_none()
        device_name = dt.name if dt else ""

    # 以任务名 + 说明 + 设备 检索手册依据
    kb_context = ""
    try:
        from app.services.vector_store import VectorStore
        query = f"{device_name} {title} {description or ''}".strip()
        sources = await VectorStore().hybrid_search(query, top_k=5, device_type_id=device_type_id)
        kb_context = "\n\n".join(
            f"【手册{i+1}】{s.get('title','')}\n{(s.get('content') or '')[:500]}"
            for i, s in enumerate(sources)
        )
    except Exception as e:
        logger.warning(f"作业指引生成检索手册失败（将不带手册依据）: {e}")

    from app.services.llm_service import LLMService
    draft = await LLMService().generate_workflow(
        device_name=device_name, repair_level=repair_level,
        title=title, description=description or "", kb_context=kb_context,
    )
    if not draft.get("steps"):
        raise HTTPException(502, "AI 生成失败或返回为空，请重试或手动编辑")
    draft["device_name"] = device_name
    return draft


@router.post("/requests/{req_id}/approve")
async def approve_request(
    req_id: str,
    name: str = Body(..., embed=True),
    steps: list = Body(..., embed=True),
    repair_level: Optional[str] = Body(None, embed=True),
    device_type_id: Optional[str] = Body(None, embed=True),
    estimated_duration: Optional[int] = Body(None, embed=True),
    comment: str = Body("", embed=True),
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """管理员审核通过：把（AI 生成并人工编辑后的）步骤发布为正式作业模板，并关联回申请。"""
    r = (await db.execute(select(WorkflowRequest).where(WorkflowRequest.id == req_id))).scalar_one_or_none()
    if not r:
        raise HTTPException(404, "申请不存在")
    if r.status != "pending":
        raise HTTPException(400, "该申请已处理")
    if not steps:
        raise HTTPException(400, "作业步骤不能为空")

    level = repair_level or r.repair_level
    tpl = WorkflowTemplate(
        device_type_id=(device_type_id or r.device_type_id) or None,
        repair_level=level if level in ("daily", "minor", "major", "emergency") else "daily",
        name=name.strip()[:200] or r.title,
        steps=steps,
        estimated_duration=estimated_duration,
        created_by=admin.id,
    )
    db.add(tpl)
    await db.flush()   # 取 tpl.id

    r.status = "published"
    r.template_id = tpl.id
    r.reviewer_id = admin.id
    r.review_comment = comment
    r.reviewed_at = datetime.utcnow()
    await db.commit()
    logger.info(f"作业指引申请发布 req={req_id} → template={tpl.id} by admin={admin.id}")
    return {"ok": True, "template_id": str(tpl.id)}


@router.post("/requests/{req_id}/reject")
async def reject_request(
    req_id: str,
    comment: str = Body(..., embed=True),
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    r = (await db.execute(select(WorkflowRequest).where(WorkflowRequest.id == req_id))).scalar_one_or_none()
    if not r:
        raise HTTPException(404, "申请不存在")
    if r.status != "pending":
        raise HTTPException(400, "该申请已处理")
    r.status = "rejected"
    r.reviewer_id = admin.id
    r.review_comment = comment
    r.reviewed_at = datetime.utcnow()
    await db.commit()
    return {"ok": True}
