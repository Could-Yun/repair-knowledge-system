import uuid
from datetime import datetime
from sqlalchemy import String, Text, DateTime, ForeignKey, func, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from app.database import Base

class Case(Base):
    __tablename__ = "cases"
    __table_args__ = (
        CheckConstraint("status IN ('pending','approved','rejected')", name="ck_cases_status"),
    )

    id:             Mapped[uuid.UUID]    = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    submitter_id:   Mapped[uuid.UUID]    = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    device_type_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("device_types.id"))
    title:          Mapped[str]          = mapped_column(String(200), nullable=False)
    fault_phenomenon: Mapped[str]        = mapped_column(Text, nullable=False)
    fault_reason:   Mapped[str | None]   = mapped_column(Text)
    solution:       Mapped[str]          = mapped_column(Text, nullable=False)
    tools_used:     Mapped[list[str] | None] = mapped_column(ARRAY(String))
    images:         Mapped[list[str] | None] = mapped_column(ARRAY(String))
    status:         Mapped[str]          = mapped_column(String(20), default="pending")  # pending|approved|rejected
    reviewer_id:    Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    review_comment: Mapped[str | None]   = mapped_column(Text)
    reviewed_at:    Mapped[datetime | None]  = mapped_column(DateTime)
    created_at:     Mapped[datetime]     = mapped_column(DateTime, server_default=func.now())
    updated_at:     Mapped[datetime]     = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
