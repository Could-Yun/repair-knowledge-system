"""
知识文档（PDF）提交与审核：
  一线人员上传 PDF → 在线解析为段落块（不入库）→ 待审核
  管理员审核通过 → 向量化写入 knowledge_base（source_type='manual'）→ 可被诊断/检索命中
"""
import os
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, Body, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, delete
from datetime import datetime
from typing import Optional

from app.config import settings
from app.database import get_db
from app.models.user import User
from app.models.device import DeviceType
from app.models.document import KnowledgeDocument
from app.models.knowledge import KnowledgeBase
from app.utils.deps import get_current_user, get_current_admin
from app.utils.logger import logger

router = APIRouter(prefix="/api/documents", tags=["documents"])


def _abs_path(url_path: str) -> str:
    """/uploads/{uid}/{file} → 磁盘绝对路径"""
    rel = url_path.replace("/uploads/", "", 1)
    return os.path.join(settings.UPLOAD_DIR, rel)


def _doc_brief(d: KnowledgeDocument, device_name=None, submitter=None) -> dict:
    return {
        "id": str(d.id), "title": d.title, "filename": d.filename,
        "file_path": d.file_path, "file_size": d.file_size,
        "page_count": d.page_count, "chunk_count": d.chunk_count,
        "status": d.status, "ingested_count": d.ingested_count,
        "review_comment": d.review_comment,
        "reviewed_at": d.reviewed_at.isoformat() if d.reviewed_at else None,
        "created_at": d.created_at.isoformat() if d.created_at else None,
        "device_type_id": str(d.device_type_id) if d.device_type_id else None,
        "device_type_name": device_name,
        "submitter_name": submitter,
    }


@router.post("")
async def upload_document(
    title: Optional[str] = Form(None),
    device_type_id: Optional[str] = Form(None),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """上传知识文档（PDF），在线解析为段落块，进入待审核。"""
    if file.content_type != "application/pdf":
        raise HTTPException(400, "目前仅支持 PDF 知识文档")

    from app.services.file_service import FileService
    from app.services.pdf_parser import parse_pdf

    fs = FileService()
    try:
        url_path = await fs.save_upload(file, current_user.id, related_type="document",
                                        max_size=settings.MAX_DOC_SIZE)
    except ValueError as e:
        raise HTTPException(400, str(e))

    abs_path  = _abs_path(url_path)
    file_size = os.path.getsize(abs_path) if os.path.exists(abs_path) else None
    doc_title = (title or "").strip() or os.path.splitext(file.filename or "")[0] or "未命名文档"

    # 解析（失败不致命：保留文件、chunk_count=0，管理员可拒绝）
    try:
        parsed = parse_pdf(abs_path, doc_title=doc_title)
        chunks = parsed["chunks"]
        page_count = parsed["page_count"]
    except Exception as e:
        logger.warning(f"文档解析失败 user={current_user.id} file={file.filename}: {e}")
        chunks, page_count = [], None

    doc = KnowledgeDocument(
        submitter_id=current_user.id,
        device_type_id=device_type_id or None,
        title=doc_title[:200],
        filename=(file.filename or "document.pdf")[:255],
        file_path=url_path,
        file_size=file_size,
        page_count=page_count,
        chunk_count=len(chunks),
        chunks=chunks,
        status="pending",
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    logger.info(f"文档提交 user={current_user.id} doc={doc.id} chunks={len(chunks)}")

    return {
        "id": str(doc.id),
        "title": doc.title,
        "page_count": page_count,
        "chunk_count": len(chunks),
        "status": doc.status,
        # 预览前 3 块，供前端确认解析效果
        "preview": [{"title": c["title"], "content": c["content"][:160]} for c in chunks[:3]],
    }


@router.get("/my")
async def my_documents(
    page: int = 1, size: int = 10,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(KnowledgeDocument, DeviceType.name).outerjoin(
        DeviceType, KnowledgeDocument.device_type_id == DeviceType.id
    ).where(KnowledgeDocument.submitter_id == current_user.id).order_by(
        KnowledgeDocument.created_at.desc()
    ).offset((page-1)*size).limit(size)
    rows = (await db.execute(q)).all()
    total = (await db.execute(select(func.count()).select_from(KnowledgeDocument).where(
        KnowledgeDocument.submitter_id == current_user.id))).scalar()
    return {"items": [_doc_brief(r[0], device_name=r[1]) for r in rows],
            "total": total, "page": page, "size": size}


@router.get("/pending")
async def pending_documents(
    page: int = 1, size: int = 10, status: str = "pending",
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """管理员：待审核文档队列。"""
    conds = [KnowledgeDocument.status == status] if status else []
    q = select(KnowledgeDocument, DeviceType.name, User.username).outerjoin(
        DeviceType, KnowledgeDocument.device_type_id == DeviceType.id
    ).outerjoin(User, KnowledgeDocument.submitter_id == User.id).where(
        and_(*conds) if conds else True
    ).order_by(KnowledgeDocument.created_at.desc()).offset((page-1)*size).limit(size)
    rows = (await db.execute(q)).all()
    total = (await db.execute(select(func.count()).select_from(KnowledgeDocument).where(
        and_(*conds) if conds else True))).scalar()
    return {"items": [_doc_brief(r[0], device_name=r[1], submitter=r[2]) for r in rows],
            "total": total, "page": page, "size": size}


@router.get("/{doc_id}")
async def get_document(
    doc_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    d = (await db.execute(select(KnowledgeDocument).where(KnowledgeDocument.id == doc_id))).scalar_one_or_none()
    if not d:
        raise HTTPException(404, "文档不存在")
    if str(d.submitter_id) != str(current_user.id) and current_user.role != "admin":
        raise HTTPException(403, "无权访问")
    out = _doc_brief(d)
    out["chunks"] = d.chunks or []  # 完整段落块，供审核预览
    return out


@router.delete("/{doc_id}")
async def delete_document(
    doc_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除知识文档（问题 #1）。
    - 普通用户：仅能删自己提交的、且仍为 pending 的文档。
    - 管理员：可删任意状态的任意文档；若已入库(approved)，级联从 knowledge_base
      移除其入库的全部知识块（按 source_id 关联），并删除磁盘原文件。
    """
    d = (await db.execute(select(KnowledgeDocument).where(KnowledgeDocument.id == doc_id))).scalar_one_or_none()
    if not d:
        raise HTTPException(404, "文档不存在")

    is_admin = current_user.role == "admin"
    is_owner = str(d.submitter_id) == str(current_user.id)
    if not (is_admin or is_owner):
        raise HTTPException(403, "无权删除")
    # 普通用户只能删自己的 pending 文档；管理员不受状态限制
    if not is_admin and d.status != "pending":
        raise HTTPException(400, "已审核的文档不能删除（如需下架请联系管理员）")

    # 级联清理：已入库文档先从知识库移除其所有向量块
    removed_kb = 0
    if d.status == "approved":
        res = await db.execute(delete(KnowledgeBase).where(KnowledgeBase.source_id == d.id))
        removed_kb = res.rowcount or 0

    # 删除磁盘原文件（失败不致命）
    try:
        abs_path = _abs_path(d.file_path)
        if abs_path and os.path.exists(abs_path):
            os.remove(abs_path)
    except Exception as e:
        logger.warning(f"删除文档物理文件失败 doc={doc_id}: {e}")

    await db.delete(d)
    await db.commit()
    logger.info(f"删除文档 doc={doc_id} by user={current_user.id} admin={is_admin} 清理知识 {removed_kb} 条")
    return {"ok": True, "removed_knowledge": removed_kb}


# 创新点 B：审核通过文档时，后台从前 N 个知识块抽取知识图谱三元组（非阻塞、有上限，
# 避免在 4 核 V11 上拖慢审核响应）。案例审核已在 ingest_case 内触发，此处覆盖手册文档。
KG_EXTRACT_MAX_CHUNKS = 10


async def _kg_extract_from_chunks(chunks: list[dict]):
    """后台任务：对若干知识块抽取三元组写入 KG（best-effort，失败不影响主流程）。"""
    try:
        from app.services.kg_service import KGService
        kg = KGService()
        for c in chunks[:KG_EXTRACT_MAX_CHUNKS]:
            text = (c.get("content") or "").strip()
            if len(text) < 40:
                continue
            try:
                await kg.extract_and_store(text, source_case_id=None)
            except Exception as e:
                logger.warning(f"文档 KG 抽取单块失败（忽略）: {e}")
        logger.info(f"文档 KG 后台抽取完成，处理块数={min(len(chunks), KG_EXTRACT_MAX_CHUNKS)}")
    except Exception as e:
        logger.warning(f"文档 KG 后台抽取失败（忽略）: {e}")


@router.post("/{doc_id}/approve")
async def approve_document(
    doc_id: str,
    background: BackgroundTasks,
    comment: str = Body("", embed=True),
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """审核通过：把文档段落块向量化写入 knowledge_base。

    幂等保证（问题 #4）：用 SELECT ... FOR UPDATE 锁住该文档行，锁内复核状态。
    并发/连点的多个 approve 会被串行化——第一个把状态置 approved 后，
    后续请求拿到锁时看到已非 pending，直接返回既有结果，不会重复入库。
    再叠加按 source_id 的去重清理作为兜底。
    """
    # 行锁 + 锁内复核（锁持有到本请求事务提交，从而串行化并发 approve）
    d = (await db.execute(
        select(KnowledgeDocument).where(KnowledgeDocument.id == doc_id).with_for_update()
    )).scalar_one_or_none()
    if not d:
        raise HTTPException(404, "文档不存在")
    if d.status != "pending":
        # 已被其它请求处理过：幂等返回，不再重复入库
        return {"ok": True, "ingested_count": d.ingested_count, "idempotent": True}
    chunks = d.chunks or []
    if not chunks:
        raise HTTPException(400, "文档无可入库内容（解析为空），请拒绝处理")

    # 去重兜底：清掉此文档可能残留的旧入库块（重复审核/历史脏数据）
    await db.execute(delete(KnowledgeBase).where(KnowledgeBase.source_id == d.id))

    from app.services.embedding import EmbeddingService
    emb = EmbeddingService()

    # 跨文档内容判重：按 source_id 的清理只能防住同一份文档被重审，
    # 挡不住同一本手册以两份文档重复上传（缺陷 D-04 正是如此）。
    # 这里先把库中已存在的正文全部取出比对，完全相同的块直接跳过。
    existing = set((await db.execute(select(KnowledgeBase.content))).scalars().all())

    inserted = 0
    skipped = 0
    batch_size = 16
    for i in range(0, len(chunks), batch_size):
        batch = [c for c in chunks[i:i + batch_size] if c["content"] not in existing]
        skipped += len(chunks[i:i + batch_size]) - len(batch)
        if not batch:
            continue
        vecs = await emb.encode_batch([c["content"] for c in batch])
        for c, vec in zip(batch, vecs):
            existing.add(c["content"])          # 防同一份文档内部的重复块
            db.add(KnowledgeBase(
                source_type="manual",
                source_id=d.id,
                title=c["title"][:200],
                content=c["content"],
                content_vector=vec,
                device_type_id=d.device_type_id,
                device_model=c.get("device_model"),
                page_no=c.get("page_start"),   # 创新点 A：保留手册页码，供答案溯源
                tags=[d.title, "用户文档"],
            ))
            inserted += 1
    if skipped:
        logger.info(f"文档入库内容判重：跳过 {skipped} 个与已有知识完全相同的块 doc={doc_id}")
    d.status = "approved"
    d.ingested_count = inserted
    d.reviewer_id = admin.id
    d.review_comment = comment
    d.reviewed_at = datetime.utcnow()
    await db.commit()
    logger.info(f"文档审核通过 doc={doc_id} 入库 {inserted} 条知识 by admin={admin.id}")

    # 创新点 B：后台抽取知识图谱（非阻塞，响应已可返回）
    background.add_task(_kg_extract_from_chunks, list(chunks))

    # skipped 一并返回，便于前端在"入库 0 条"时说明原因（内容与已有知识完全重复）
    return {"ok": True, "ingested_count": inserted, "skipped_duplicate": skipped}


@router.post("/{doc_id}/reject")
async def reject_document(
    doc_id: str,
    comment: str = Body(..., embed=True),
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    d = (await db.execute(select(KnowledgeDocument).where(KnowledgeDocument.id == doc_id))).scalar_one_or_none()
    if not d:
        raise HTTPException(404, "文档不存在")
    if d.status != "pending":
        raise HTTPException(400, "文档已审核")
    d.status = "rejected"
    d.reviewer_id = admin.id
    d.review_comment = comment
    d.reviewed_at = datetime.utcnow()
    await db.commit()
    return {"ok": True}
