import uuid
from datetime import datetime
from sqlalchemy import String, Text, Integer, DateTime, ForeignKey, func, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from app.database import Base

class WorkflowTemplate(Base):
    __tablename__ = "workflow_templates"
    __table_args__ = (
        CheckConstraint("repair_level IN ('daily','minor','major','emergency')", name="ck_wf_repair_level"),
    )

    id:             Mapped[uuid.UUID]    = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    device_type_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("device_types.id"))
    repair_level:   Mapped[str]          = mapped_column(String(20), nullable=False)  # daily|minor|major|emergency
    name:           Mapped[str]          = mapped_column(String(200), nullable=False)
    steps:          Mapped[dict]         = mapped_column(JSONB, nullable=False)
    estimated_duration: Mapped[int | None] = mapped_column(Integer)
    created_by:     Mapped[uuid.UUID]    = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at:     Mapped[datetime]     = mapped_column(DateTime, server_default=func.now())
    updated_at:     Mapped[datetime]     = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

class WorkflowRequest(Base):
    """一线人员对"不存在的作业指引"的申请。
    流程：一线提交申请(pending) → 管理员 AI 生成草稿 + 审核编辑 → 发布(published，关联生成的模板) / 拒绝(rejected)。
    面向定期保养、清洗等标准化作业的按需建标，全程留痕、可证明一线已作业。
    """
    __tablename__ = "workflow_requests"
    __table_args__ = (
        CheckConstraint("status IN ('pending','published','rejected')", name="ck_wfreq_status"),
    )

    id:             Mapped[uuid.UUID]    = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    requester_id:   Mapped[uuid.UUID]    = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    device_type_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("device_types.id"))
    repair_level:   Mapped[str]          = mapped_column(String(20), nullable=False)
    title:          Mapped[str]          = mapped_column(String(200), nullable=False)   # 作业任务名，如"化油器定期清洗"
    description:    Mapped[str | None]   = mapped_column(Text)                            # 申请说明/背景
    status:         Mapped[str]          = mapped_column(String(20), default="pending")  # pending|published|rejected
    review_comment: Mapped[str | None]   = mapped_column(Text)
    template_id:    Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("workflow_templates.id"))
    reviewer_id:    Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    created_at:     Mapped[datetime]     = mapped_column(DateTime, server_default=func.now())
    reviewed_at:    Mapped[datetime | None] = mapped_column(DateTime)


class RepairRecord(Base):
    __tablename__ = "repair_records"
    __table_args__ = (
        CheckConstraint("status IN ('in_progress','completed','paused')", name="ck_records_status"),
    )

    id:                  Mapped[uuid.UUID]    = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    worker_id:           Mapped[uuid.UUID]    = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    workflow_template_id:Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("workflow_templates.id"))
    device_type_id:      Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("device_types.id"))
    fault_description:   Mapped[str | None]   = mapped_column(Text)
    diagnosis_result:    Mapped[str | None]   = mapped_column(Text)
    steps_data:          Mapped[dict | None]  = mapped_column(JSONB)
    images:              Mapped[list[str] | None] = mapped_column(ARRAY(String))
    status:              Mapped[str]          = mapped_column(String(20), default="in_progress")
    started_at:          Mapped[datetime]     = mapped_column(DateTime, server_default=func.now())
    completed_at:        Mapped[datetime | None] = mapped_column(DateTime)
