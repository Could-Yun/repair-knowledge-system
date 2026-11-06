"""
设备检修知识检索与作业系统 — FastAPI 主入口
赛题: 第十五届中国软件杯 A1（龙芯中科出题）
部署: LoongArch + 银河麒麟 V11
"""
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager

from app.config import settings
from app.database import engine, Base, check_connection, close_engine
from app.utils.logger import logger
from app.routers import auth, diagnosis, cases, audit, knowledge, workflow, feedback, upload, devices, admin, documents, system


async def _run_light_migrations(conn) -> None:
    """幂等的轻量列迁移（不依赖 alembic）。每条都用 IF NOT EXISTS，可安全重复执行。"""
    from sqlalchemy import text
    migrations = [
        # 创新点 A：knowledge_base 增加 page_no（手册页码），用于答案溯源
        "ALTER TABLE knowledge_base ADD COLUMN IF NOT EXISTS page_no INTEGER",
    ]
    for sql in migrations:
        try:
            await conn.execute(text(sql))
        except Exception as e:  # 失败不致命：记录并继续启动
            logger.warning(f"轻量迁移跳过/失败: {sql} | {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ---- 启动 ----
    # 1) 连通性 + 扩展自动启用（致命失败抛 RuntimeError 阻塞启动）
    await check_connection()

    # 2) 建表（开发期用；生产期切 alembic）
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # 轻量迁移：create_all 只建缺失的表、不会给已存在的表补列。
        # 对已部署的 V11 库，用幂等 ADD COLUMN IF NOT EXISTS 补上新增列（重启即生效，无需手工 DDL）。
        await _run_light_migrations(conn)
    logger.info("数据库表结构同步完成")

    # 3) 预加载 Embedding 模型（失败仅警告）
    try:
        from app.services.embedding import EmbeddingService
        emb = EmbeddingService()
        emb._load()
        logger.info("Embedding 模型预热完成")
    except Exception as e:
        logger.warning(f"Embedding 预热失败（将在首次调用时加载）: {e}")

    yield

    # ---- 关闭 ----
    await close_engine()
    logger.info("服务关闭")


app = FastAPI(
    title="设备检修知识检索与作业系统",
    description="第十五届中国软件杯 A1 · LoongArch + 银河麒麟 V11",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 路由注册
app.include_router(auth.router)
app.include_router(diagnosis.router)
app.include_router(cases.router)
app.include_router(audit.router)
app.include_router(knowledge.router)
app.include_router(workflow.router)
app.include_router(feedback.router)
app.include_router(upload.router)
app.include_router(devices.router)
app.include_router(admin.router)
app.include_router(documents.router)
app.include_router(system.router)


@app.get("/api/health")
async def health():
    """服务健康检查。
    注意：本路由必须注册在根路径静态挂载之前 —— Starlette 按注册顺序匹配，
    app.mount("/") 会吞掉其后注册的所有路由，否则本接口将永远返回 404。
    """
    return {"status": "ok", "version": "1.0.0", "platform": "LoongArch · 银河麒麟 V11"}


# 上传文件静态服务
uploads_dir = os.path.abspath(settings.UPLOAD_DIR)
os.makedirs(uploads_dir, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=uploads_dir), name="uploads")

# 前端静态资源（Vue3 build 产物）
# 必须放在所有 API 路由与其它挂载之后：它匹配根路径，会拦截其后注册的一切请求。
static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.exists(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        workers=1,        # 8G 内存，单进程异步
        log_level="info",
    )
