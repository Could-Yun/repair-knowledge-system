import uuid
from datetime import datetime
from sqlalchemy import String, Text, Integer, Boolean, DateTime, ForeignKey, func, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from pgvector.sqlalchemy import Vector
from app.database import Base

class KnowledgeBase(Base):
    __tablename__ = "knowledge_base"
    __table_args__ = (
        CheckConstraint("source_type IN ('case','manual','experience')", name="ck_kb_source_type"),
    )

    id:             Mapped[uuid.UUID]    = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_type:    Mapped[str]          = mapped_column(String(20), nullable=False)  # case|manual|experience
    source_id:      Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    title:          Mapped[str]          = mapped_column(String(200), nullable=False)
    content:        Mapped[str]          = mapped_column(Text, nullable=False)
    content_vector: Mapped[list | None]  = mapped_column(Vector(768))  # BGE-base-zh-v1.5
    image_urls:     Mapped[list[str] | None] = mapped_column(ARRAY(String))
    image_description: Mapped[str | None]= mapped_column(Text)
    device_type_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("device_types.id"))
    device_model:   Mapped[str | None]   = mapped_column(String(100))
    tags:           Mapped[list[str] | None] = mapped_column(ARRAY(String))
    # 创新点 A（答案可溯源）：入库时保留该知识块在原手册/文档中的起始页码，
    # 供诊断结果"点开看手册第 N 页"。可空（历史数据与案例来源无页码）。
    page_no:        Mapped[int | None]   = mapped_column(Integer)
    created_at:     Mapped[datetime]     = mapped_column(DateTime, server_default=func.now())


class SearchLog(Base):
    """知识检索历史：记录每位用户的检索行为，供"我的检索历史"查看。
    create_all 自动建表（新表，无需手工迁移）。"""
    __tablename__ = "search_logs"

    id:           Mapped[uuid.UUID]    = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id:      Mapped[uuid.UUID]    = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    query:        Mapped[str]          = mapped_column(Text, nullable=False)
    device_type_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("device_types.id"))
    result_count: Mapped[int]          = mapped_column(Integer, default=0)
    has_image:    Mapped[bool]         = mapped_column(Boolean, default=False)
    created_at:   Mapped[datetime]     = mapped_column(DateTime, server_default=func.now())
