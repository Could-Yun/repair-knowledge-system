"""
Embedding 服务（SKILL 10，2026-06-02 锁定 llama.cpp 统一推理）

加载顺序（懒加载 + 自动降级，受 settings.EMBED_BACKEND 控制）:
  1. llama.cpp --embedding HTTP（:11435）→ V11 桌面版主路径，零 ONNX 依赖，与 chat 调用对称
  2. 本地 BGE-base-zh-v1.5 ONNX        → 备选 A，仅当 onnxruntime 可 import 时启用
  3. DashScope text-embedding-v3        → 云端兜底，dimensions=768 保持 schema 对齐
  4. mock 随机向量                      → 仅开发期且以上均不可用时，便于跑通流程

EMBED_BACKEND: auto（默认，依次尝试 1→2→3→4）| llama（仅 1）| onnx（仅 2）| cloud（仅 3）

维度: 768（与 knowledge_base.content_vector VECTOR(768) 严格对齐）
LoongArch 兼容: 主路径走 llama.cpp，纯 HTTP，无架构依赖；onnxruntime 已非必装
"""
import asyncio
import numpy as np
import httpx
from typing import List
from enum import Enum

from app.config import settings
from app.utils.logger import logger


class _Mode(str, Enum):
    UNLOADED   = "unloaded"
    LOCAL_HTTP = "local_http"   # llama.cpp --embedding（:11435）主路径
    LOCAL      = "local"        # ONNX 备选
    CLOUD      = "cloud"        # DashScope
    MOCK       = "mock"         # 随机向量（开发期兜底）


class EmbeddingService:
    _instance  = None
    _mode      = _Mode.UNLOADED
    _session   = None
    _tokenizer = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    # ------------------------------------------------------------------
    # 加载（同步，启动期一次）
    # ------------------------------------------------------------------
    def _load(self) -> None:
        if self._mode != _Mode.UNLOADED:
            return

        backend = (settings.EMBED_BACKEND or "auto").lower()

        # 1) llama.cpp --embedding HTTP（:11435）主路径
        if backend in ("auto", "llama"):
            if self._probe_local_http():
                self._mode = _Mode.LOCAL_HTTP
                logger.info(f"Embedding 模式: LOCAL_HTTP (llama.cpp {settings.EMBED_LOCAL_URL})")
                return
            logger.warning(f"llama.cpp embedding 探测失败: {settings.EMBED_LOCAL_URL}")
            if backend == "llama":
                self._mode = _Mode.MOCK
                logger.warning("EMBED_BACKEND=llama 但服务不可用 → 暂用 MOCK，启动 llama-server(:11435) 后重启生效")
                return

        # 2) 本地 ONNX 备选（仅当 onnxruntime 可用）
        if backend in ("auto", "onnx"):
            try:
                self._load_local()
                self._mode = _Mode.LOCAL
                logger.info("Embedding 模式: LOCAL (BGE-base ONNX)")
                return
            except Exception as e:
                logger.warning(f"本地 BGE ONNX 加载失败（onnxruntime 未装属正常）: {_short(e)}")
                if backend == "onnx":
                    self._mode = _Mode.MOCK
                    return

        # 3) DashScope 云端兜底
        if backend in ("auto", "cloud") and settings.EMBED_FALLBACK_API_KEY:
            self._mode = _Mode.CLOUD
            logger.info(
                f"Embedding 模式: CLOUD ({settings.EMBED_FALLBACK_PROVIDER} / "
                f"{settings.EMBED_FALLBACK_MODEL})"
            )
            return

        # 4) mock（开发期）
        self._mode = _Mode.MOCK
        logger.warning(
            "Embedding 模式: MOCK (随机 768 维向量) — "
            "启动 llama-server(:11435) 或配置 EMBED_FALLBACK_API_KEY 后切换到真实推理"
        )

    @staticmethod
    def _probe_local_http() -> bool:
        """同步探测 llama.cpp embedding 服务是否在线（启动期一次，避免拖慢首个请求）"""
        url = f"{settings.EMBED_LOCAL_URL.rstrip('/')}/embeddings"
        try:
            r = httpx.post(
                url,
                headers={"Authorization": f"Bearer {settings.EMBED_LOCAL_KEY}",
                         "Content-Type": "application/json"},
                json={"model": settings.EMBED_LOCAL_MODEL, "input": "ping"},
                timeout=5.0,
            )
            if r.status_code >= 400:
                return False
            dim = len(r.json()["data"][0]["embedding"])
            if dim != settings.EMBEDDING_DIM:
                logger.warning(f"llama.cpp embedding 维度={dim} 与期望 {settings.EMBEDDING_DIM} 不符")
                return False
            return True
        except Exception:
            return False

    def _load_local(self) -> None:
        import onnxruntime as ort
        from transformers import AutoTokenizer
        import os

        model_path = settings.EMBEDDING_MODEL_PATH
        onnx_path  = os.path.join(model_path, "model.onnx")
        if not os.path.exists(onnx_path):
            raise FileNotFoundError(f"未找到 {onnx_path}")

        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 2   # SKILL 05 §10 内存约束
        opts.inter_op_num_threads = 1
        self._session = ort.InferenceSession(
            onnx_path, sess_options=opts,
            providers=["CPUExecutionProvider"],
        )
        self._tokenizer = AutoTokenizer.from_pretrained(model_path)

    # ------------------------------------------------------------------
    # 对外 API
    # ------------------------------------------------------------------
    async def encode(self, text: str) -> List[float]:
        return (await self.encode_batch([text]))[0]

    async def encode_batch(
        self,
        texts: List[str],
        batch_size: int = 16,
    ) -> List[List[float]]:
        self._load()

        if self._mode == _Mode.LOCAL_HTTP:
            return await self._encode_local_http_batched(texts, batch_size)
        if self._mode == _Mode.LOCAL:
            return self._encode_local_batched(texts, batch_size)
        if self._mode == _Mode.CLOUD:
            return await self._encode_cloud_batched(texts, batch_size=10)
        # mock
        return [list(np.random.randn(settings.EMBEDDING_DIM).astype(np.float32))
                for _ in texts]

    @property
    def mode(self) -> str:
        return self._mode.value

    # ------------------------------------------------------------------
    # llama.cpp --embedding HTTP 路径（OpenAI 兼容 /v1/embeddings，主路径）
    # ------------------------------------------------------------------
    async def _encode_local_http_batched(self, texts: List[str], batch_size: int) -> List[List[float]]:
        all_vecs: List[List[float]] = []
        for i in range(0, len(texts), batch_size):
            all_vecs.extend(await self._encode_local_http_one_batch(texts[i:i + batch_size]))
        return all_vecs

    async def _encode_local_http_one_batch(self, texts: List[str]) -> List[List[float]]:
        url = f"{settings.EMBED_LOCAL_URL.rstrip('/')}/embeddings"
        headers = {
            "Authorization": f"Bearer {settings.EMBED_LOCAL_KEY}",
            "Content-Type":  "application/json",
        }
        payload = {"model": settings.EMBED_LOCAL_MODEL, "input": texts}
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                r = await client.post(url, headers=headers, json=payload)
                r.raise_for_status()
                data = r.json()
            out: List[List[float]] = []
            # llama.cpp 可能不保证返回顺序，按 index 排序对齐
            items = sorted(data["data"], key=lambda x: x.get("index", 0))
            for item in items:
                v = np.asarray(item["embedding"], dtype=np.float32)
                n = np.linalg.norm(v)
                out.append((v / (n + 1e-8)).tolist())   # L2 归一化（保险起见再做一次）
            return out
        except Exception as e:
            logger.error(f"llama.cpp embedding 失败: {_short(e)} — 返回随机向量保证流程不中断")
            return [list(np.random.randn(settings.EMBEDDING_DIM).astype(np.float32))
                    for _ in texts]

    # ------------------------------------------------------------------
    # 本地 ONNX 路径
    # ------------------------------------------------------------------
    def _encode_local_batched(self, texts: List[str], batch_size: int) -> List[List[float]]:
        vecs: List[List[float]] = []
        for i in range(0, len(texts), batch_size):
            vecs.extend(self._encode_local_one_batch(texts[i:i + batch_size]))
        return vecs

    def _encode_local_one_batch(self, texts: List[str]) -> List[List[float]]:
        # BGE 推荐前缀（仅对短 query 加；段落入库可省略，这里统一加保持一致性）
        prefixed = [f"为这个句子生成表示以用于检索相关文章：{t}" for t in texts]
        enc = self._tokenizer(
            prefixed, padding=True, truncation=True, max_length=512, return_tensors="np"
        )
        inputs = {
            "input_ids":      enc["input_ids"].astype(np.int64),
            "attention_mask": enc["attention_mask"].astype(np.int64),
        }
        if "token_type_ids" in enc:
            inputs["token_type_ids"] = enc["token_type_ids"].astype(np.int64)

        outputs  = self._session.run(None, inputs)
        cls_vecs = outputs[0][:, 0, :]                              # CLS pooling
        norms    = np.linalg.norm(cls_vecs, axis=1, keepdims=True)
        normed   = cls_vecs / (norms + 1e-8)                        # L2 归一化
        return normed.tolist()

    # ------------------------------------------------------------------
    # DashScope 云端兜底（OpenAI 兼容 /embeddings 端点）
    # ------------------------------------------------------------------
    async def _encode_cloud_batched(
        self,
        texts: List[str],
        batch_size: int = 10,
    ) -> List[List[float]]:
        """DashScope text-embedding-v3 单次最多 10 条；dimensions=768 保持与 schema 对齐"""
        all_vecs: List[List[float]] = []
        for i in range(0, len(texts), batch_size):
            chunk = texts[i:i + batch_size]
            all_vecs.extend(await self._encode_cloud_one_batch(chunk))
        return all_vecs

    async def _encode_cloud_one_batch(self, texts: List[str]) -> List[List[float]]:
        url = f"{settings.EMBED_FALLBACK_BASE_URL.rstrip('/')}/embeddings"
        headers = {
            "Authorization": f"Bearer {settings.EMBED_FALLBACK_API_KEY}",
            "Content-Type":  "application/json",
        }
        payload = {
            "model": settings.EMBED_FALLBACK_MODEL,
            "input": texts,
            "dimensions": settings.EMBEDDING_DIM,   # 锁 768
            "encoding_format": "float",
        }
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.post(url, headers=headers, json=payload)
                r.raise_for_status()
                data = r.json()
            # OpenAI 兼容响应：{"data": [{"embedding": [...]}, ...]}
            return [item["embedding"] for item in data["data"]]
        except Exception as e:
            logger.error(f"云端 Embedding 失败: {_short(e)} — 返回随机向量保证流程不中断")
            return [list(np.random.randn(settings.EMBEDDING_DIM).astype(np.float32))
                    for _ in texts]


def _short(e: Exception, n: int = 160) -> str:
    s = str(e).strip().splitlines()[0]
    return (s[:n] + "...") if len(s) > n else s
