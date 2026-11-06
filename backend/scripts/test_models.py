#!/usr/bin/env python3
"""
四通道大模型自检：CHAT(云) / VL(云) / Embedding / 本地LLM
真发一次请求，确认 V11 能连通各模型端点 + API key 有效。

用法（在 backend 目录、venv 激活下）:
  python scripts/test_models.py
"""
import sys, os, asyncio, base64, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

G = "\033[92m"; R = "\033[91m"; Y = "\033[93m"; B = "\033[94m"; E = "\033[0m"
def ok(m):   print(f"  {G}[ OK ]{E} {m}")
def bad(m):  print(f"  {R}[FAIL]{E} {m}")
def warn(m): print(f"  {Y}[WARN]{E} {m}")
def sec(t):  print(f"\n{B}=== {t} ==={E}")


def _make_test_image() -> str:
    """生成一张 320x320 的真实图片（带形状），规避 qwen-vl 对超小图的 400 拒绝。"""
    p = os.path.join(tempfile.gettempdir(), "_vl_test.png")
    try:
        from PIL import Image, ImageDraw
        img = Image.new("RGB", (320, 320), (58, 64, 78))
        d = ImageDraw.Draw(img)
        d.ellipse([70, 70, 250, 250], fill=(170, 60, 45))      # 红色圆（模拟部件）
        d.rectangle([130, 150, 220, 175], fill=(25, 25, 25))   # 黑色条
        d.line([60, 280, 260, 290], fill=(220, 200, 60), width=6)
        img.save(p)
    except Exception:
        # Pillow 不可用时退回 1x1（可能触发 400，但至少能跑）
        with open(p, "wb") as f:
            f.write(base64.b64decode(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="))
    return p


async def _raw_vl_probe(settings, path):
    """describe_images 吞掉了错误体；这里直发一次，打印服务器原始返回，定位 400 真因。"""
    import httpx
    b64 = base64.b64encode(open(path, "rb").read()).decode()
    url = settings.VL_BASE_URL.rstrip("/") + "/chat/completions"
    payload = {
        "model": settings.VL_MODEL,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": "请简短描述这张图片"},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
        ]}],
        "max_tokens": 100,
    }
    try:
        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.post(url, headers={"Authorization": f"Bearer {settings.VL_API_KEY}"}, json=payload)
            print(f"  {Y}原始HTTP {r.status_code}{E}: {r.text[:600]}")
    except Exception as e:
        print(f"  {R}原始探测异常{E}: {str(e)[:300]}")


async def main():
    from app.config import settings
    from app.services.llm_service import LLMService
    from app.services.embedding import EmbeddingService
    llm = LLMService()

    sec(f"1. CHAT 云端 (百炼 {settings.CHAT_MODEL})")
    try:
        r = await llm.chat([{"role": "user", "content": "只回复两个字：正常"}], max_tokens=20)
        ok(f"返回: {r.strip()[:60]}") if r.strip() else bad("返回空串")
    except Exception as e:
        bad(str(e)[:200])

    sec(f"2. VL 云端 ({settings.VL_MODEL})")
    p = _make_test_image()
    try:
        r = await llm.describe_images([p], prompt="请简短描述这张图片里有什么")
        if r.strip():
            ok(f"返回: {r.strip()[:100]}")
        else:
            bad("describe_images 返回空，下面打印服务器原始错误以定位真因：")
            await _raw_vl_probe(settings, p)
    except Exception as e:
        bad(str(e)[:200])
        await _raw_vl_probe(settings, p)

    sec(f"3. Embedding (后端={settings.EMBED_BACKEND} → 云端兜底)")
    try:
        v = await EmbeddingService().encode("发动机怠速抖动并伴有异响")
        ok(f"维度 {len(v)} 正确，前3值: {[round(x, 4) for x in v[:3]]}") \
            if v and len(v) == settings.EMBEDDING_DIM else bad(f"维度异常: {len(v) if v else 0}")
    except Exception as e:
        bad(str(e)[:200])

    sec(f"4. 本地大模型 (llama.cpp {settings.LOCAL_LLM_MODEL} @ {settings.LOCAL_LLM_URL})")
    try:
        r = await llm._call_local([{"role": "user", "content": "你好"}], max_tokens=20)
        ok(f"返回: {r.strip()[:60]}")
    except Exception as e:
        warn(f"未起（预期内，llama.cpp 尚未部署）: {str(e)[:120]}")

    print(f"\n{B}=== 小结 ==={E}")
    print("  云端 CHAT / VL / Embedding 三项 [OK] = 三个云端模型可用")
    print("  本地 [WARN] = llama.cpp 兜底待部署（仅断网时需要，联网评测不影响）")


if __name__ == "__main__":
    asyncio.run(main())
