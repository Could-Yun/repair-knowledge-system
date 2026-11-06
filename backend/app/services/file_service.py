"""
文件存储服务：本地文件系统 + 缩略图生成
上传路径: uploads/{user_id}/{uuid}.{ext}
缩略图:  uploads/{user_id}/thumb_{uuid}.jpg (512px)
"""
import os
import uuid
import aiofiles
from fastapi import UploadFile
from PIL import Image
import io
from app.config import settings
from app.utils.logger import logger


ALLOWED_MIME = {"image/jpeg", "image/png", "application/pdf"}

class FileService:
    def __init__(self):
        self.upload_dir = settings.UPLOAD_DIR
        os.makedirs(self.upload_dir, exist_ok=True)

    async def save_upload(
        self,
        file: UploadFile,
        user_id,
        related_type: str = "general",
        max_size: int | None = None,
    ) -> str:
        """保存上传文件，返回 URL 路径。max_size 可覆盖默认大小上限（如文档放宽到 50MB）。"""
        if file.content_type not in ALLOWED_MIME:
            raise ValueError(f"不支持的文件类型: {file.content_type}")

        limit = max_size or settings.MAX_FILE_SIZE
        content = await file.read()
        if len(content) > limit:
            raise ValueError(f"文件超过 {limit // (1024*1024)}MB 限制")

        ext       = self._get_ext(file.filename, file.content_type)
        file_uuid = str(uuid.uuid4())
        user_dir  = os.path.join(self.upload_dir, str(user_id))
        os.makedirs(user_dir, exist_ok=True)

        filename  = f"{file_uuid}.{ext}"
        full_path = os.path.join(user_dir, filename)

        async with aiofiles.open(full_path, "wb") as f:
            await f.write(content)

        logger.info(f"文件上传: user={user_id} type={related_type} size={len(content)} path={full_path}")

        # 图片自动生成缩略图
        if file.content_type in ("image/jpeg", "image/png"):
            try:
                self._make_thumbnail(content, user_dir, file_uuid, ext)
            except Exception as e:
                logger.warning(f"缩略图生成失败: {e}")

        # 返回可访问的 URL 路径
        return f"/uploads/{user_id}/{filename}"

    @staticmethod
    def _make_thumbnail(content: bytes, user_dir: str, file_uuid: str, ext: str):
        img = Image.open(io.BytesIO(content))
        img.thumbnail((512, 512), Image.LANCZOS)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        thumb_path = os.path.join(user_dir, f"thumb_{file_uuid}.jpg")
        img.save(thumb_path, "JPEG", quality=85, optimize=True)

    @staticmethod
    def _get_ext(filename: str, content_type: str) -> str:
        ext_map = {"image/jpeg": "jpg", "image/png": "png", "application/pdf": "pdf"}
        if filename and "." in filename:
            return filename.rsplit(".", 1)[-1].lower()
        return ext_map.get(content_type, "bin")
