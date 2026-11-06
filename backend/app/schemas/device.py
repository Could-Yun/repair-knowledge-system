from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List
import uuid

class DeviceTypeOut(BaseModel):
    id:           uuid.UUID
    name:         str
    category:     Optional[str] = None
    model_no:     Optional[str] = None
    manufacturer: Optional[str] = None
    created_at:   datetime

    class Config:
        orm_mode = True

class DeviceTypeListOut(BaseModel):
    items: List[DeviceTypeOut]
    total: int
