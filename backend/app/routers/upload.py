from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from app.models.user import User
from app.utils.deps import get_current_user

router = APIRouter(prefix="/api/upload", tags=["upload"])

@router.post("")
async def upload_file(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    from app.services.file_service import FileService
    from app.config import settings
    if file.size and file.size > settings.MAX_FILE_SIZE:
        raise HTTPException(400, "文件大小超过限制（5MB）")
    allowed = {"image/jpeg", "image/png", "application/pdf"}
    if file.content_type not in allowed:
        raise HTTPException(400, "不支持的文件类型，仅允许 JPG/PNG/PDF")
    fs = FileService()
    path = await fs.save_upload(file, current_user.id)
    return {"url": path, "name": file.filename}
