"""
数据库连接层（async）
- 驱动: asyncpg（SKILL 16 明确：拒绝 psycopg2-binary，无 loong64 wheel）
- 连接池: pool_size=2, max_overflow=3（SKILL 05 §10 内存约束）
- 扩展自动启用: pgvector / uuid-ossp / pg_trgm
- zhparser 按 settings.ENABLE_ZHPARSER 决定（Windows 本地默认关闭，V11 默认开启）
"""
from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy import text
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncSession, create_async_engine, async_sessionmaker
)
from sqlalchemy.orm import DeclarativeBase

from app.config import settings
from app.utils.logger import logger


# ============================================================
# Engine：异步 PostgreSQL（asyncpg）
# ============================================================
engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=settings.DB_POOL_SIZE,           # 默认 2
    max_overflow=settings.DB_MAX_OVERFLOW,     # 默认 3
    pool_timeout=settings.DB_POOL_TIMEOUT,     # 默认 30s
    pool_recycle=3600,                         # 1h 回收，防 idle 中断
    pool_pre_ping=True,                        # 取出连接前 ping，自动重连
    echo=settings.DB_ECHO,                     # 调试 SQL 打印
)

async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    pass


# ============================================================
# 依赖注入：FastAPI Depends(get_db)
# ============================================================
async def get_db() -> AsyncIterator[AsyncSession]:
    session = async_session()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


# ============================================================
# 启动期：连通性检查 + 扩展自动启用
# ============================================================
REQUIRED_EXTENSIONS = [
    # (扩展名, 是否致命, 描述, SKILL 出处)
    ("uuid-ossp", True,  "UUID 主键生成",       "SKILL 02 §1"),
    ("vector",    True,  "pgvector 向量检索",   "SKILL 02 §1 / SKILL 10"),
    ("pg_trgm",   False, "设备型号 LIKE 索引",  "SKILL 02 §3"),
]

OPTIONAL_EXTENSIONS = [
    ("zhparser",  "中文分词全文检索", "SKILL 05 §2 / SKILL 02 §3"),
]


async def check_connection() -> dict:
    """
    数据库连通性体检。
    返回包含 server_version / extensions / fts_config 的字典；
    失败抛 RuntimeError，由 main.py lifespan 决定是否阻塞启动。
    """
    info = {"url": _safe_url(settings.DATABASE_URL)}
    try:
        async with engine.begin() as conn:
            # 1) 服务器版本
            row = (await conn.execute(text("SELECT version()"))).scalar()
            info["server_version"] = row.split(",")[0] if row else "unknown"

            # 2) 必需扩展
            installed_exts: list[str] = []
            for ext, required, desc, src in REQUIRED_EXTENSIONS:
                try:
                    await conn.execute(text(f'CREATE EXTENSION IF NOT EXISTS "{ext}"'))
                    installed_exts.append(ext)
                    logger.info(f"扩展 OK: {ext}  ({desc})")
                except SQLAlchemyError as e:
                    msg = f"扩展失败: {ext} — {desc}  [{src}]  原因: {_short(e)}"
                    if required:
                        logger.error(msg)
                        raise RuntimeError(msg) from e
                    logger.warning(msg)

            # 3) 可选扩展（zhparser）
            if settings.ENABLE_ZHPARSER:
                for ext, desc, src in OPTIONAL_EXTENSIONS:
                    try:
                        await conn.execute(text(f'CREATE EXTENSION IF NOT EXISTS "{ext}"'))
                        installed_exts.append(ext)
                        logger.info(f"扩展 OK: {ext}  ({desc})")
                        await _ensure_chinese_fts(conn)
                    except SQLAlchemyError as e:
                        logger.warning(
                            f"zhparser 未启用，全文检索将降级为 simple parser："
                            f"{_short(e)}  [{src}]"
                        )
            else:
                logger.info("ENABLE_ZHPARSER=false，全文检索使用 simple parser（适合本地开发）")

            info["extensions"]  = installed_exts
            info["fts_config"]  = settings.FTS_CONFIG
            info["pool_status"] = {
                "pool_size":   settings.DB_POOL_SIZE,
                "max_overflow": settings.DB_MAX_OVERFLOW,
            }

        logger.info(
            f"数据库连接 OK | {info['server_version']} | "
            f"扩展: {','.join(info['extensions'])} | FTS: {info['fts_config']}"
        )
        return info

    except OperationalError as e:
        msg = (
            f"数据库连接失败：{_short(e)}\n"
            f"  - 检查 .env 中 DATABASE_URL\n"
            f"  - 当前值: {_safe_url(settings.DATABASE_URL)}\n"
            f"  - 本地开发请确认 PostgreSQL 服务已启动（参见 docs/DATABASE_SETUP.md）"
        )
        logger.error(msg)
        raise RuntimeError(msg) from e


async def _ensure_chinese_fts(conn):
    """配置 zhparser → chinese 文本检索配置（SKILL 02 §3）"""
    await conn.execute(text("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_ts_config WHERE cfgname = 'chinese'
            ) THEN
                CREATE TEXT SEARCH CONFIGURATION chinese (PARSER = zhparser);
                ALTER TEXT SEARCH CONFIGURATION chinese
                    ADD MAPPING FOR n,v,a,i,e,l WITH simple;
            END IF;
        END $$;
    """))
    # multi_short：粒度更细的分词（SKILL 02 §3）
    try:
        await conn.execute(text("SET zhparser.multi_short = on"))
    except SQLAlchemyError:
        pass


# ============================================================
# 辅助
# ============================================================
def _safe_url(url: str) -> str:
    """脱敏 DATABASE_URL（隐藏密码）"""
    import re
    return re.sub(r'(://[^:]+:)[^@]+(@)', r'\1***\2', url)


def _short(e: Exception, n: int = 200) -> str:
    s = str(e).strip().splitlines()[0]
    return (s[:n] + "...") if len(s) > n else s


async def close_engine() -> None:
    """关闭引擎（lifespan shutdown 调用）"""
    await engine.dispose()
    logger.info("数据库连接池已关闭")
