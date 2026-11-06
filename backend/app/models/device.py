import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base

class DeviceType(Base):
    __tablename__ = "device_types"

    id:           Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name:         Mapped[str]       = mapped_column(String(100), nullable=False)
    category:     Mapped[str | None]= mapped_column(String(50))
    model_no:     Mapped[str | None]= mapped_column(String(100))
    manufacturer: Mapped[str | None]= mapped_column(String(100))
    manual_url:   Mapped[str | None]= mapped_column(String(500))
    created_at:   Mapped[datetime]  = mapped_column(DateTime, server_default=func.now())
