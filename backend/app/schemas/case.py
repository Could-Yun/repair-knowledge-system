from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List
import uuid

class CaseOut(BaseModel):
    id:               uuid.UUID
    title:            str
    fault_phenomenon: str
    fault_reason:     Optional[str] = None
    solution:         str
    tools_used:       Optional[List[str]] = []
    images:           Optional[List[str]] = []
    status:           str
    review_comment:   Optional[str] = None
    reviewed_at:      Optional[datetime] = None
    created_at:       datetime
    # 关联展示字段（通过 JOIN 填充）
    device_type_name: Optional[str] = None
    submitter_name:   Optional[str] = None

    class Config:
        orm_mode = True

class CaseListOut(BaseModel):
    items: List[CaseOut]
    total: int
    page:  int
    size:  int
