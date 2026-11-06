from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from datetime import datetime, timedelta
from app.database import get_db
from app.models.user import User
from app.models.case import Case
from app.models.knowledge import KnowledgeBase
from app.models.workflow import RepairRecord
from app.services.llm_service import LLMService
from app.services.embedding import EmbeddingService
from app.utils.deps import get_current_admin, get_current_user
from app.config import settings

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/health/llm")
async def health_llm():
    """
    LLM 三通道健康检查（SKILL 07 §1.3）
    任何用户可访问，便于配置 key 时排错
    """
    llm = LLMService()
    emb = EmbeddingService()
    emb._load()
    return {
        "llm":       await llm.health(),
        "embedding": {
            "mode":   emb.mode,                # local | cloud | mock
            "dim":    settings.EMBEDDING_DIM,
        },
        "database":  {
            "fts_config":      settings.FTS_CONFIG,
            "zhparser_enabled": settings.ENABLE_ZHPARSER,
        },
    }

@router.get("/stats")
async def stats(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """数据驾驶舱统计。系统级聚合数据，任何登录用户均可查看（首页）。"""
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    # 今日诊断：仅统计真实诊断记录，排除标准化作业指引产生的执行工单
    is_diag = RepairRecord.workflow_template_id.is_(None)
    today_diag  = (await db.execute(select(func.count()).select_from(RepairRecord).where(RepairRecord.started_at >= today, is_diag))).scalar()
    kb_total    = (await db.execute(select(func.count()).select_from(KnowledgeBase))).scalar()
    approved    = (await db.execute(select(func.count()).select_from(Case).where(Case.status == "approved"))).scalar()
    pending     = (await db.execute(select(func.count()).select_from(Case).where(Case.status == "pending"))).scalar()
    rejected    = (await db.execute(select(func.count()).select_from(Case).where(Case.status == "rejected"))).scalar()

    # ---------- 环比（对比昨日） ----------
    # 四张卡的口径不同，环比也要分别定义，不能一刀切：
    #   今日诊断 / 待审核 是"当下存量或当日计数"，与昨日同口径数值相减；
    #   知识条目 / 通过案例 是"累计总数"，只增不减，环比取今日新增量。
    yday = today - timedelta(days=1)
    yday_diag = (await db.execute(select(func.count()).select_from(RepairRecord).where(
        RepairRecord.started_at >= yday, RepairRecord.started_at < today, is_diag))).scalar()
    kb_today = (await db.execute(select(func.count()).select_from(KnowledgeBase).where(
        KnowledgeBase.created_at >= today))).scalar()
    approved_today = (await db.execute(select(func.count()).select_from(Case).where(
        Case.status == "approved", Case.reviewed_at >= today))).scalar()
    # 昨日结束时的待审量：昨日之前提交，且当时尚未审核（未审核，或审核发生在今天）
    pending_yday = (await db.execute(select(func.count()).select_from(Case).where(
        Case.created_at < today,
        or_(Case.status == "pending", Case.reviewed_at >= today)))).scalar()

    deltas = {
        # value 为与昨日的差值或今日新增量；up 表示该变化是否为正面信号
        "today_diagnosis": {"value": today_diag - yday_diag, "up": today_diag >= yday_diag},
        "kb_total":        {"value": kb_today,               "up": True},
        "approved_cases":  {"value": approved_today,         "up": True},
        # 待审核积压减少才是好事，所以 up 取反
        "pending_cases":   {"value": pending - pending_yday, "up": pending <= pending_yday},
    }

    # 近7日趋势
    trend = []
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        next_day = day + timedelta(days=1)
        cnt = (await db.execute(select(func.count()).select_from(RepairRecord).where(
            RepairRecord.started_at >= day, RepairRecord.started_at < next_day, is_diag
        ))).scalar()
        trend.append({"date": day.strftime("%m/%d"), "count": cnt})

    return {
        "today_diagnosis": today_diag,
        "kb_total":        kb_total,
        "approved_cases":  approved,
        "pending_cases":   pending,
        "trend":           trend,
        "case_status":     {"approved": approved, "pending": pending, "rejected": rejected},
        "deltas":          deltas,
    }
