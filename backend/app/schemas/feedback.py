from pydantic import BaseModel
from typing import Optional
import uuid

class FeedbackIn(BaseModel):
    original_output: str
    user_correction: str
    correction_type: str   # error | incomplete | optimization
    record_id:       Optional[uuid.UUID] = None
