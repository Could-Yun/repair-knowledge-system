"""
全局配置（pydantic-settings）
配置来源: 环境变量 / .env 文件
- 本地开发: cp .env.local .env
- V11 部署: cp .env.v11   .env

LLM 路由（SKILL 07 §1.1 / SKILL 10 §1.3）:
  ┌──────────────┬─────────────────────────────┬─────────────────────────────┐
  │   场景       │  主路径                     │  兜底                       │
  ├──────────────┼─────────────────────────────┼─────────────────────────────┤
  │ 文本对话     │  CHAT_*（DeepSeek 推荐）    │  LOCAL（llama.cpp Qwen2.5）│
  │ 看图诊断     │  VL_*（Qwen-VL-Max 推荐）   │  跳过图片，仅用文本         │
  │ Embedding    │  llama.cpp --embedding:11435│  ONNX → DashScope → mock    │
  └──────────────┴─────────────────────────────┴─────────────────────────────┘

Embedding 后端（2026-06-02 锁定 llama.cpp 统一推理，SKILL 10/16）:
  EMBED_BACKEND=auto → 依次 llama.cpp(:11435) → ONNX(可选) → DashScope → mock
"""
from functools import lru_cache
import os

# pydantic v1（银河麒麟 V11 LoongArch 用系统 RPM python3-pydantic 1.10.x，规避 Rust 编译）
from pydantic import BaseSettings


class Settings(BaseSettings):
    # ============ 环境标识 ============
    APP_ENV:  str = "local"          # local | v11 | prod
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000

    # ============ 数据库（PostgreSQL + pgvector）============
    DATABASE_URL:      str = "postgresql+asyncpg://repair:CHANGE_ME@localhost:5432/repair_system"
    DB_POOL_SIZE:      int = 2
    DB_MAX_OVERFLOW:   int = 3
    DB_POOL_TIMEOUT:   int = 30
    DB_ECHO:           bool = False

    # 中文全文检索（zhparser 是否启用）
    ENABLE_ZHPARSER:   bool = False
    FTS_CONFIG:        str  = "simple"   # simple | chinese

    # ============ JWT ============
    SECRET_KEY:                   str = "change-me-in-production-very-long-secret-min-32-chars"
    ALGORITHM:                    str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES:  int = 480     # SKILL 03 §6: 8h
    REFRESH_TOKEN_EXPIRE_MINUTES: int = 43200   # 30d

    # ============================================================
    # 大模型 — 通道 1: 文本对话（CHAT）
    # ============================================================
    # 用途：故障诊断主回答、知识结构化、KG 三元组抽取、个性化推送精排
    # 推荐：DeepSeek-V3（中文强、性价比高、OpenAI 兼容）
    CHAT_PROVIDER:   str = "deepseek"
    CHAT_API_KEY:    str = ""
    CHAT_BASE_URL:   str = "https://api.deepseek.com/v1"
    CHAT_MODEL:      str = "deepseek-chat"

    # ============================================================
    # 大模型 — 通道 2: 多模态视觉（VL）
    # ============================================================
    # 用途：看故障图，生成图片描述，跨模态检索
    # 推荐：阿里 DashScope Qwen-VL-Max（视觉能力强、OpenAI 兼容端点）
    # 注: DeepSeek-Chat 不支持视觉，必须用独立视觉模型
    VL_PROVIDER:     str = "dashscope"
    VL_API_KEY:      str = ""
    VL_BASE_URL:     str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    VL_MODEL:        str = "qwen-vl-max"

    # ============================================================
    # 大模型 — 通道 3: Embedding 云端兜底
    # ============================================================
    # 仅在本地 BGE ONNX 加载失败（如 V11 上 onnxruntime 装不上）时启用
    # SKILL 10 §1.3：DashScope text-embedding-v3 支持 dimensions=768，与 schema 对齐
    EMBED_FALLBACK_PROVIDER: str = "dashscope"
    EMBED_FALLBACK_API_KEY:  str = ""           # 可与 VL_API_KEY 复用同一把 DashScope key
    EMBED_FALLBACK_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    EMBED_FALLBACK_MODEL:    str = "text-embedding-v3"

    # ============================================================
    # 大模型 — 通道 4: 本地 LLM 兜底（断网/云端全挂时）
    # ============================================================
    # 由 systemd 守护 llama-server（SKILL 05 §11.2 / SKILL 10 §2.3）
    LOCAL_LLM_URL:   str = "http://127.0.0.1:11434/v1"
    LOCAL_LLM_MODEL: str = "qwen2.5-1.5b"
    LOCAL_LLM_KEY:   str = "local-fallback-key"   # llama-server --api-key 参数

    # ============================================================
    # Embedding 后端选择与本地 llama.cpp 通道（SKILL 10 §1.3 / §3.1）
    # ============================================================
    # auto: llama.cpp(:11435) → ONNX(可选) → DashScope → mock
    # llama / onnx / cloud: 仅用指定后端
    EMBED_BACKEND:    str = "auto"
    # llama.cpp --embedding 模式（与 chat:11434 分离），OpenAI 兼容 /v1/embeddings
    EMBED_LOCAL_URL:   str = "http://127.0.0.1:11435/v1"
    EMBED_LOCAL_MODEL: str = "bge-base-zh-v1.5"
    EMBED_LOCAL_KEY:   str = "local-fallback-key"   # llama-server --api-key

    # ============ Embedding 本地配置（ONNX 备选用）============
    EMBEDDING_MODEL_PATH: str = "./models/bge-base-zh-v1.5"
    EMBEDDING_DIM:        int = 768

    # ============ 文件上传 ============
    UPLOAD_DIR:    str = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
    MAX_FILE_SIZE: int = 5 * 1024 * 1024
    MAX_DOC_SIZE:  int = 50 * 1024 * 1024   # 知识文档(PDF)上限，手册可达 ~17MB
    LOG_DIR:       str = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")

    # ============ CORS ============
    CORS_ORIGINS: list[str] = ["*"]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
