import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, func, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base

class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('admin','field_worker')", name="ck_users_role"),
    )

    id:           Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username:     Mapped[str]       = mapped_column(String(50), unique=True, nullable=False)
    password_hash:Mapped[str]       = mapped_column(String(255), nullable=False)
    role:         Mapped[str]       = mapped_column(String(20), nullable=False)   # field_worker | admin
    real_name:    Mapped[str | None]= mapped_column(String(50))
    phone:        Mapped[str | None]= mapped_column(String(20))
    department:   Mapped[str | None]= mapped_column(String(100))
    is_active:    Mapped[bool]      = mapped_column(Boolean, default=True)
    created_at:   Mapped[datetime]  = mapped_column(DateTime, server_default=func.now())
    updated_at:   Mapped[datetime]  = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # 暴力破解防护
    failed_login_count: Mapped[int]      = mapped_column(default=0)
    locked_until:       Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
