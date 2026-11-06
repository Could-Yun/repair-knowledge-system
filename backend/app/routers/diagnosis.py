from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional, List
from datetime import datetime
from app.database import get_db
from app.models.user import User
from app.models.workflow import RepairRecord
from app.utils.deps import get_current_user
from app.utils.logger import logger, llm_logger
import time

router = APIRouter(prefix="/api/diagnosis", tags=["diagnosis"])

import re as _re
def _norm_action(s: str) -> str:
    """归一化检查动作文本，用于判重（去标点/空白/大小写）"""
    return _re.sub(r"[\s，。、,.:：;；!！?？()（）]", "", (s or "")).lower()

@router.post("/analyze")
async def analyze_fault(
    description: str = Form(...),
    device_type_id: Optional[str] = Form(None),
    images: List[UploadFile] = File(default=[]),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.services.llm_service import LLMService
    from app.services.vector_store import VectorStore
    from app.services.file_service import FileService

    t0 = time.time()
    llm = LLMService()
    vs  = VectorStore()
    fs  = FileService()

    # 1. 保存图片
    image_paths = []
    for img in images:
        path = await fs.save_upload(img, current_user.id, related_type="diagnosis")
        image_paths.append(path)

    # 2. 图片描述（VL 模型）
    img_desc = ""
    if image_paths:
        try:
            img_desc = await llm.describe_images(image_paths)
        except Exception as e:
            logger.warning(f"图片描述失败: {e}")

    # 3. 构建查询（文本 + 图片描述）
    full_query = description
    if img_desc:
        full_query += f"\n[图片描述] {img_desc}"

    # 4. RAG 检索
    rag_result = await vs.rag_search(full_query, top_k=3, device_type_id=device_type_id)
    sources = rag_result["sources"]
    # 给每条参考资料编号（1-based），用于答案引用溯源（创新点 A）
    for i, r in enumerate(sources):
        r["ref_no"] = i + 1

    # 5. 构建多模态结构化 Prompt（SKILL 07 §3.1）
    #    参考资料拼接带 [ID:xxx]，便于模型回引 related_case_ids；带【参考资料N】供 [来源N] 溯源
    context = "\n\n".join([
        f"【参考资料{r['ref_no']} ID:{r['id']}】{r['title']}"
        + (f"（手册第{r['page_no']}页）" if r.get("page_no") else "")
        + f"\n{r['content']}"
        for r in sources
    ])

    # 创新点 B：知识图谱关联子图（症状→原因→处置），既注入 LLM 也回传前端可视化
    kg_graph = {"entities": [], "relations": [], "context": ""}
    try:
        from app.services.kg_service import KGService
        kg_graph = await KGService().query_subgraph(full_query)
    except Exception as e:
        logger.warning(f"KG 子图检索失败（不影响诊断）: {e}")

    # 反馈闭环：注入近 30 天已采纳的人工修正（SKILL 07 §5）
    feedback_context = await vs.build_feedback_context()
    messages = llm.build_diagnosis_messages(
        description=description,
        img_desc=img_desc,
        context=context,
        feedback_context=feedback_context,
        kg_context=kg_graph.get("context", ""),
    )

    # 6. 调用 LLM + 结构化解析（SKILL 07 §7）
    t_llm = time.time()
    raw = await llm.chat(messages, temperature=0.3)
    diag = llm.parse_diagnosis_response(raw)
    llm_logger.info(f"diagnosis | latency={time.time()-t_llm:.2f}s | user={current_user.id}")

    # 由结构化字段合成 Markdown，兼容前端 marked 渲染
    answer = _to_markdown(diag)

    # 7. 保存检修记录
    record = RepairRecord(
        worker_id=current_user.id,
        device_type_id=device_type_id,
        fault_description=description,
        diagnosis_result=answer,
        images=image_paths,
        status="in_progress",
    )
    db.add(record)
    await db.commit()

    logger.info(f"diagnosis done | total={time.time()-t0:.2f}s | user={current_user.id}")

    return {
        "answer":            answer,
        "fault_analysis":    diag["fault_analysis"],
        "repair_steps":      diag["repair_steps"],
        "required_tools":    diag["required_tools"],
        "safety_risks":      diag["safety_risks"],
        "confidence":        diag["confidence"],
        "related_case_ids":  diag["related_case_ids"],
        "citations":         diag.get("citations", []),   # 创新点 A：被引用的参考资料序号
        "sources":           sources,                      # 已含 ref_no / page_no，供溯源抽屉
        "kg_graph":          kg_graph,                     # 创新点 B：知识图谱推理子图
        "record_id":         str(record.id),
        "latency":           round(time.time() - t0, 2),
    }


def _to_markdown(diag: dict) -> str:
    """结构化诊断 → Markdown（保持前端展示不破坏）"""
    md = []
    if diag.get("fault_analysis"):
        md.append(f"## 故障原因分析\n\n{diag['fault_analysis']}")
    if diag.get("repair_steps"):
        md.append("## 推荐检修步骤\n\n" + "\n".join(f"{i+1}. {s}" for i, s in enumerate(diag["repair_steps"])))
    if diag.get("required_tools"):
        md.append("## 所需工具\n\n" + "\n".join(f"- {t}" for t in diag["required_tools"]))
    if diag.get("safety_risks"):
        md.append("## 注意事项与风险\n\n" + "\n".join(f"- {r}" for r in diag["safety_risks"]))
    conf = diag.get("confidence")
    if conf is not None:
        md.append(f"_诊断置信度：{round(float(conf) * 100)}%_")
    return "\n\n".join(md) if md else "未能生成诊断结果，请补充故障描述。"

# ----------------------------------------------------------------------
# 分步检修向导：逐步排查（系统给一步 → 用户反馈 → 排除/确认 → 下一步）
# ----------------------------------------------------------------------
class GuideFeedback(BaseModel):
    action: str = ""
    result: str = ""   # 正常 / 异常 / 不确定
    note: str = ""


class GuideStepRequest(BaseModel):
    record_id: Optional[str] = None
    fault_description: str
    fault_analysis: str = ""
    repair_steps: List[str] = []
    history: List[GuideFeedback] = []


class RepairPlanRequest(BaseModel):
    """分步排查定论后，据根本原因生成现场维修作业方案。"""
    record_id: Optional[str] = None
    device_type_id: Optional[str] = None
    fault_description: str
    root_cause: str                      # 排查定论给出的根本原因（guide 的 conclusion）
    history: List[GuideFeedback] = []    # 排查过程，供模型判断哪些部位已确认


@router.post("/guide/step")
async def guide_step(
    payload: GuideStepRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """根据已完成的检查反馈，返回下一步检修指引；可定论时返回最终结论。
    以知识库（检修手册）检索结果为权威基准，云端大模型辅助排序与推进。"""
    from app.services.llm_service import LLMService
    from app.services.vector_store import VectorStore

    llm = LLMService()
    vs  = VectorStore()
    history = [h.dict() for h in payload.history]
    next_no = len(history) + 1

    # 知识库检索：以故障描述 + 当前排查焦点（最近一步）作查询，命中手册相关章节
    kb_query = payload.fault_description
    if history:
        last = history[-1]
        kb_query += f" {last.get('action','')} {last.get('note','')}"
    kb_context = ""
    try:
        sources = await vs.hybrid_search(kb_query, top_k=3)
        kb_context = "\n\n".join(
            f"【手册{i+1}】{s.get('title','')}\n{(s.get('content') or '')[:500]}"
            for i, s in enumerate(sources)
        )
    except Exception as e:
        logger.warning(f"向导知识库检索失败（降级为无手册依据）: {e}")

    MAX_STEPS = 7  # 步数上限，超过则强制收敛，避免无限排查

    messages = llm.build_guide_messages(
        fault_description=payload.fault_description,
        fault_analysis=payload.fault_analysis,
        repair_steps=payload.repair_steps,
        history=history,
        kb_context=kb_context,
    )

    t_llm = time.time()
    raw = await llm.chat(messages, temperature=0.2, max_tokens=1024)
    step = llm.parse_guide_response(raw, step_no=next_no)

    # 护栏：弱模型常原地打转。若返回的步骤与历史重复、或步数超限，则强制收敛出结论
    done_norm = {_norm_action(h.get("action", "")) for h in history}
    repeated = _norm_action(step.get("action", "")) in done_norm
    if not step["is_final"] and (repeated or next_no > MAX_STEPS):
        logger.info(f"guide 强制收敛 | repeated={repeated} no={next_no}")
        messages2 = llm.build_guide_messages(
            fault_description=payload.fault_description,
            fault_analysis=payload.fault_analysis,
            repair_steps=payload.repair_steps,
            history=history,
            kb_context=kb_context,
            force_conclude=True,
        )
        raw2 = await llm.chat(messages2, temperature=0.2, max_tokens=1024)
        step = llm.parse_guide_response(raw2, step_no=next_no)
        step["is_final"] = True
        if not step.get("conclusion"):
            # 兜底结论：指向最近一次“异常”反馈
            abn = next((h for h in reversed(history) if h.get("result") == "异常"), None)
            step["conclusion"] = (
                f"综合排查，故障根因最可能与「{abn['action']}」环节相关，建议据此处置。"
                if abn else "已完成主要排查项，请结合现场实际情况处置；如仍未定位建议送专业检修。"
            )

    llm_logger.info(
        f"guide_step | no={next_no} final={step['is_final']} "
        f"latency={time.time()-t_llm:.2f}s | user={current_user.id}"
    )

    # 持久化排查过程到检修记录（每步更新；定论时标记完成）
    if payload.record_id:
        try:
            rec = await db.get(RepairRecord, payload.record_id)
            if rec and rec.worker_id == current_user.id:
                rec.steps_data = {
                    "guide_history": history,
                    "current_step": step,
                }
                if step["is_final"]:
                    rec.status = "completed"
                    rec.completed_at = datetime.utcnow()
                await db.commit()
        except Exception as e:
            logger.warning(f"向导进度持久化失败（不影响主流程）: {e}")

    return step


@router.post("/repair-plan")
async def generate_repair_plan(
    payload: RepairPlanRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """分步排查定论后，把「根本原因」转成一份可现场执行的分步维修作业方案。

    与标准化作业指引的区别：
      · 标准化作业面向可预期的重复任务（保养、清洗、巡检），由管理员审核后发布为模板；
      · 本接口面向不可预期的突发故障，依据排查定论即时生成，不落模板库，
        执行留痕仍复用 workflow 的 repair_records 引擎。
    """
    from app.services.llm_service import LLMService
    from app.services.vector_store import VectorStore
    from app.models.device import DeviceType

    if not payload.root_cause.strip():
        raise HTTPException(400, "缺少根本原因，请先完成分步排查并得到结论")

    device_name = ""
    if payload.device_type_id:
        dt = (await db.execute(
            select(DeviceType).where(DeviceType.id == payload.device_type_id)
        )).scalar_one_or_none()
        device_name = dt.name if dt else ""

    # 以「根本原因 + 故障现象 + 设备」检索手册中的拆装/更换章节作为权威依据
    kb_context = ""
    try:
        query = f"{device_name} {payload.root_cause} {payload.fault_description}".strip()
        sources = await VectorStore().hybrid_search(
            query, top_k=5, device_type_id=payload.device_type_id)
        kb_context = "\n\n".join(
            f"【手册{i+1}】{s.get('title','')}"
            + (f"（第{s.get('page_no')}页）" if s.get("page_no") else "")
            + f"\n{(s.get('content') or '')[:500]}"
            for i, s in enumerate(sources)
        )
    except Exception as e:
        logger.warning(f"维修方案检索手册失败（将不带手册依据）: {e}")

    t0 = time.time()
    plan = await LLMService().generate_repair_plan(
        device_name=device_name,
        fault_description=payload.fault_description,
        root_cause=payload.root_cause,
        guide_history=[h.dict() for h in payload.history],
        kb_context=kb_context,
    )
    llm_logger.info(
        f"repair_plan | steps={len(plan.get('steps') or [])} "
        f"latency={time.time()-t0:.2f}s | user={current_user.id}"
    )
    if not plan.get("steps"):
        raise HTTPException(502, "维修方案生成失败或返回为空，请重试")

    plan["device_name"] = device_name
    plan["root_cause"]  = payload.root_cause
    plan["record_id"]   = payload.record_id
    return plan


@router.get("/history")
async def diagnosis_history(
    page: int = 1,
    size: int = 10,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.models.device import DeviceType
    offset = (page - 1) * size
    # 仅诊断记录：排除标准化作业指引产生的执行工单（workflow_template_id 非空者属作业留痕，不进诊断历史）
    is_diag = RepairRecord.workflow_template_id.is_(None)
    # 关联设备类型，回传 device_type_name（修复历史记录恒显示"未知设备"的问题）
    q = (
        select(RepairRecord, DeviceType.name)
        .outerjoin(DeviceType, RepairRecord.device_type_id == DeviceType.id)
        .where(RepairRecord.worker_id == current_user.id, is_diag)
        .order_by(RepairRecord.started_at.desc())
        .offset(offset).limit(size)
    )
    rows = (await db.execute(q)).all()
    total_q = await db.execute(select(func.count()).select_from(RepairRecord).where(
        RepairRecord.worker_id == current_user.id, is_diag))
    total = total_q.scalar()

    # 今日诊断数
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_q = await db.execute(select(func.count()).select_from(RepairRecord).where(
        RepairRecord.worker_id == current_user.id,
        is_diag,
        RepairRecord.started_at >= today_start,
    ))
    return {
        "items": [{
            "id": str(r.id),
            "fault_description": r.fault_description,
            "device_type_id": str(r.device_type_id) if r.device_type_id else None,
            "device_type_name": dname,
            "diagnosis_result": r.diagnosis_result,
            "steps_data": r.steps_data,      # 含分步检修指引过程与最终结论
            "status": r.status,
            "started_at": r.started_at.isoformat(),
        } for r, dname in rows],
        "total": total,
        "today_count": today_q.scalar(),
        "page": page,
        "size": size,
    }
