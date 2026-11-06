#!/usr/bin/env python3
"""仅本地验证用：把 cnsoft 代码接到 repair_user 拥有的 repair_db，补列+种子账号。"""
import os, asyncio
os.environ["DATABASE_URL"] = "postgresql+asyncpg://repair_user:repair_pass@localhost:5432/repair_db"
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def main():
    from app.database import engine, async_session
    from app.utils.security import hash_password
    from app.models.user import User
    from sqlalchemy import text, select

    async with engine.begin() as conn:
        await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS failed_login_count INTEGER DEFAULT 0"))
        await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS locked_until TIMESTAMP NULL"))
        print("[OK] users 补列 failed_login_count / locked_until")

    async with async_session() as db:
        for uname, pw, role, rn in [("admin","admin123","admin","系统管理员"),
                                     ("worker","worker123","field_worker","测试工人")]:
            u = (await db.execute(select(User).where(User.username==uname))).scalar_one_or_none()
            if u:
                u.password_hash = hash_password(pw); u.failed_login_count = 0; u.locked_until = None
                print(f"[OK] 重置账号 {uname}/{pw}")
            else:
                db.add(User(username=uname, password_hash=hash_password(pw), role=role, real_name=rn))
                print(f"[OK] 新建账号 {uname}/{pw}")
        await db.commit()
    print("[DONE] repair_db 准备完毕")

asyncio.run(main())
