import uuid
from datetime import datetime
from sqlalchemy import String, Text, Integer, DateTime, ForeignKey, func, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.database import Base


class KnowledgeDocument(Base):
    """一线人员提交的知识文档（PDF）。审核通过后其段落块写入 knowledge_base。"""
    __tablename__ = "knowledge_documents"
    __table_args__ = (
        CheckConstraint("status IN ('pending','approved','rejected')", name="ck_kdoc_status"),
    )

    id:             Mapped[uuid.UUID]    = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    submitter_id:   Mapped[uuid.UUID]    = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    device_type_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("device_types.id"))
    title:          Mapped[str]          = mapped_column(String(200), nullable=False)
    filename:       Mapped[str]          = mapped_column(String(255), nullable=False)
    file_path:      Mapped[str]          = mapped_column(String(500), nullable=False)  # /uploads/...
    file_size:      Mapped[int | None]   = mapped_column(Integer)
    page_count:     Mapped[int | None]   = mapped_column(Integer)
    chunk_count:    Mapped[int]          = mapped_column(Integer, default=0)
    chunks:         Mapped[list | None]  = mapped_column(JSONB)  # 解析结果，审核通过时向量化入库
    status:         Mapped[str]          = mapped_column(String(20), default="pending")  # pending|approved|rejected
    ingested_count: Mapped[int]          = mapped_column(Integer, default=0)
    reviewer_id:    Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    review_comment: Mapped[str | None]   = mapped_column(Text)
    reviewed_at:    Mapped[datetime | None]  = mapped_column(DateTime)
    created_at:     Mapped[datetime]     = mapped_column(DateTime, server_default=func.now())
