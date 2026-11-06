from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from datetime import datetime, timedelta
from app.database import get_db
from app.models.user import User
from app.schemas.auth import LoginRequest, TokenResponse, UserOut, RegisterRequest
from app.utils.security import hash_password, verify_password, create_access_token, create_refresh_token
from app.utils.deps import get_current_user, get_current_admin

router = APIRouter(prefix="/api/auth", tags=["auth"])

@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == body.username, User.is_active == True))
    user: User = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    # 检查锁定
    if user.locked_until and user.locked_until > datetime.utcnow():
        raise HTTPException(status_code=401, detail="账户已临时锁定，请15分钟后重试")

    if not verify_password(body.password, user.password_hash):
        # 失败计数
        count = (user.failed_login_count or 0) + 1
        locked = None
        if count >= 10:
            locked = datetime.utcnow() + timedelta(minutes=15)
            count = 0
        await db.execute(
            update(User).where(User.id == user.id).values(
                failed_login_count=count, locked_until=locked
            )
        )
        await db.commit()
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    # 重置失败计数
    await db.execute(update(User).where(User.id == user.id).values(failed_login_count=0, locked_until=None))
    await db.commit()

    token_data = {"sub": str(user.id), "role": user.role}
    return TokenResponse(
        access_token=create_access_token(token_data),
        refresh_token=create_refresh_token(token_data),
    )

ALLOWED_ROLES = ("admin", "field_worker")


@router.post("/register", response_model=UserOut)
async def register(
    body: RegisterRequest,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),   # 仅管理员可建号，一线人员调用返回 403
):
    """新建账号（管理员专用）。

    账号一律由管理员创建，不开放自助注册：role 由调用方传入，
    若不加鉴权与白名单，任何人都能把自己注册成 admin 拿到审核与全员留痕权限。
    首个管理员账号来自 scripts/init_db.py 的种子数据。
    """
    if body.role not in ALLOWED_ROLES:
        raise HTTPException(status_code=400, detail="角色只能是 admin 或 field_worker")
    if not body.username or not body.username.strip():
        raise HTTPException(status_code=400, detail="用户名不能为空")
    if not body.password or len(body.password) < 6:
        raise HTTPException(status_code=400, detail="密码至少 6 位")
    # 检查用户名重复
    exists = await db.execute(select(User).where(User.username == body.username))
    if exists.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="用户名已存在")
    user = User(
        username=body.username,
        password_hash=hash_password(body.password),
        role=body.role,
        real_name=body.real_name,
        phone=body.phone,
        department=body.department,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user

@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)):
    return current_user

@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(current_user: User = Depends(get_current_user)):
    token_data = {"sub": str(current_user.id), "role": current_user.role}
    return TokenResponse(
        access_token=create_access_token(token_data),
        refresh_token=create_refresh_token(token_data),
    )
