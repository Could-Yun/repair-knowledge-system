import uuid
from datetime import datetime
from sqlalchemy import String, Text, Boolean, DateTime, ForeignKey, func, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base

class Feedback(Base):
    __tablename__ = "feedbacks"
    __table_args__ = (
        CheckConstraint("correction_type IN ('error','incomplete','optimization')", name="ck_feedback_correction_type"),
    )

    id:               Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id:          Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    record_id:        Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("repair_records.id"))
    original_output:  Mapped[str]       = mapped_column(Text, nullable=False)
    user_correction:  Mapped[str]       = mapped_column(Text, nullable=False)
    correction_type:  Mapped[str]       = mapped_column(String(20), nullable=False)  # error|incomplete|optimization
    is_adopted:       Mapped[bool]      = mapped_column(Boolean, default=False)
    created_at:       Mapped[datetime]  = mapped_column(DateTime, server_default=func.now())
