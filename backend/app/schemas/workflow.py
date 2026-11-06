from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List, Any
import uuid

class WorkflowTemplateOut(BaseModel):
    id:                 uuid.UUID
    name:               str
    repair_level:       str
    steps:              Any   # JSONB list
    estimated_duration: Optional[int] = None
    device_type_name:   Optional[str] = None
    created_at:         datetime

    class Config:
        orm_mode = True

class WorkflowTemplateIn(BaseModel):
    device_type_id:     Optional[uuid.UUID] = None
    repair_level:       str
    name:               str
    steps:              List[Any]
    estimated_duration: Optional[int] = None

class RepairRecordOut(BaseModel):
    id:               uuid.UUID
    fault_description:Optional[str] = None
    diagnosis_result: Optional[str] = None
    steps_data:       Optional[Any] = None
    status:           str
    started_at:       datetime
    completed_at:     Optional[datetime] = None
    device_type_name: Optional[str] = None

    class Config:
        orm_mode = True
