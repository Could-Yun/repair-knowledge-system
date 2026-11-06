import uuid
from datetime import datetime
from sqlalchemy import String, Integer, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base

class UploadFile(Base):
    __tablename__ = "upload_files"

    id:            Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    uploader_id:   Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    original_name: Mapped[str]       = mapped_column(String(255), nullable=False)
    stored_path:   Mapped[str]       = mapped_column(String(500), nullable=False)
    file_size:     Mapped[int | None]= mapped_column(Integer)
    mime_type:     Mapped[str | None]= mapped_column(String(100))
    related_type:  Mapped[str | None]= mapped_column(String(50))
    related_id:    Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at:    Mapped[datetime]  = mapped_column(DateTime, server_default=func.now())
