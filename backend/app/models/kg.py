import uuid
from datetime import datetime
from sqlalchemy import String, Text, Float, DateTime, ForeignKey, func, UniqueConstraint, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from app.database import Base

class KgEntity(Base):
    __tablename__ = "kg_entities"
    __table_args__ = (
        UniqueConstraint("entity_type", "name"),
        CheckConstraint(
            "entity_type IN ('device','component','symptom','cause','solution','tool','part')",
            name="ck_kg_entity_type"),
    )

    id:           Mapped[uuid.UUID]    = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_type:  Mapped[str]          = mapped_column(String(20), nullable=False)
    name:         Mapped[str]          = mapped_column(String(200), nullable=False)
    aliases:      Mapped[list[str] | None] = mapped_column(ARRAY(String))
    description:  Mapped[str | None]   = mapped_column(Text)
    properties:   Mapped[dict | None]  = mapped_column(JSONB)
    source_case_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("cases.id"))
    created_at:   Mapped[datetime]     = mapped_column(DateTime, server_default=func.now())

class KgRelation(Base):
    __tablename__ = "kg_relations"
    __table_args__ = (
        UniqueConstraint("subject_id", "predicate", "object_id"),
        CheckConstraint(
            "predicate IN ('has_component','symptom_of','caused_by','solved_by',"
            "'requires_tool','part_of','related_to')",
            name="ck_kg_predicate"),
    )

    id:           Mapped[uuid.UUID]    = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subject_id:   Mapped[uuid.UUID]    = mapped_column(UUID(as_uuid=True), ForeignKey("kg_entities.id", ondelete="CASCADE"), nullable=False)
    predicate:    Mapped[str]          = mapped_column(String(50), nullable=False)
    object_id:    Mapped[uuid.UUID]    = mapped_column(UUID(as_uuid=True), ForeignKey("kg_entities.id", ondelete="CASCADE"), nullable=False)
    confidence:   Mapped[float]        = mapped_column(Float, default=1.0)
    source_case_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("cases.id"))
    created_at:   Mapped[datetime]     = mapped_column(DateTime, server_default=func.now())
