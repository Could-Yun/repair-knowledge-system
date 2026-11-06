"""
系统辅助接口：手机访问二维码生成。
GET /api/qrcode?data=<url>  → 返回该 URL 的二维码 PNG
  - 前端传入 window.location.origin，二维码即指向"当前访问地址"，IP 变化自动跟随。
  - 未传 data 时，服务端探测本机局域网 IP 兜底（部署在麒麟 V11 等原生 Linux 上即为可达 IP）。
公开接口（供 <img> 直接引用，无需鉴权）。
"""
import io
import socket
from fastapi import APIRouter, Query, Request
from fastapi.responses import Response

router = APIRouter(prefix="/api", tags=["system"])


def _lan_ip() -> str:
    """探测本机出口网卡的局域网 IP（不真正发包）。"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


@router.get("/qrcode")
async def gen_qrcode(
    request: Request,
    data: str | None = Query(None, description="二维码内容(URL)；留空则用本机IP兜底"),
    port: int | None = Query(None, description="兜底时使用的端口"),
):
    import qrcode

    if data:
        text = data.strip()[:1024]
    else:
        p = port or (request.url.port or 8000)
        text = f"http://{_lan_ip()}:{p}"

    img = qrcode.make(text)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return Response(
        content=buf.getvalue(),
        media_type="image/png",
        headers={"Cache-Control": "no-store"},
    )
