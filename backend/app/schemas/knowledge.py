from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List
import uuid

class KBItemOut(BaseModel):
    id:          uuid.UUID
    source_type: str
    title:       str
    content:     str
    image_urls:  Optional[List[str]] = []
    device_model:Optional[str] = None
    tags:        Optional[List[str]] = []
    score:       Optional[float] = None  # 检索相关度
    created_at:  datetime

    class Config:
        orm_mode = True

class KBSearchOut(BaseModel):
    items:       List[KBItemOut]
    total:       int
    query:       str
    search_time: Optional[float] = None
