from pydantic import BaseModel
from datetime import datetime
import uuid

class LoginRequest(BaseModel):
    username: str
    password: str

class TokenResponse(BaseModel):
    access_token:  str
    refresh_token: str
    token_type:    str = "bearer"

class UserOut(BaseModel):
    id:         uuid.UUID
    username:   str
    role:       str
    real_name:  str | None = None
    phone:      str | None = None
    department: str | None = None
    is_active:  bool
    created_at: datetime

    class Config:
        orm_mode = True

class RegisterRequest(BaseModel):
    username:  str
    password:  str
    role:      str = "field_worker"
    real_name: str | None = None
    phone:     str | None = None
    department:str | None = None
