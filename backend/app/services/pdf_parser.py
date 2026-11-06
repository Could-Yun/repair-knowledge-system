"""
PDF 解析服务：把上传的知识文档（PDF）解析为可入库的段落块。
逻辑沿用 scripts/parse_manual.py（中文手册章节切分 + 段落分块），
供 /api/documents 在线上传时调用（文本为主，不抽取图片）。

解析后端用 pypdf（纯 Python）：LoongArch 上无需任何编译，也不引入
cryptography/Rust（pdfminer.six 会拖 cryptography，已规避）。在线上传 PDF
时由后端当场解析，无需 PyMuPDF。
"""
import re
from pathlib import Path

try:
    from pypdf import PdfReader  # 纯 Python，LoongArch 可装
except ImportError:  # 解析能力缺失时由调用方兜底
    PdfReader = None


# 章节标题正则：匹配「第X章」「X.X 标题」「一、 标题」「【…】」等中文手册常见格式
_CHAPTER_PATTERNS = [
    re.compile(r'^第[一二三四五六七八九十百\d]+章\s+\S'),
    re.compile(r'^\d+\.\d+[\s　]+\S'),
    re.compile(r'^[一二三四五六七八九十]+、\s*\S'),
    re.compile(r'^【.+】'),
]


def _is_chapter_title(line: str) -> bool:
    line = line.strip()
    if len(line) < 3 or len(line) > 80:
        return False
    return any(p.match(line) for p in _CHAPTER_PATTERNS)


def _is_toc_page(text: str, ratio_threshold: float = 0.6) -> bool:
    """目录页判定：短行中"标题样式"占比超阈值则视为目录，跳过（避免与正文重名）。"""
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    body = [l for l in lines if not re.match(r'^No\.\s*\d+\s*/\s*\d+$', l) and "维修手册" not in l]
    if len(body) < 6:
        return False
    title_like = sum(1 for l in body if _is_chapter_title(l))
    return title_like / len(body) >= ratio_threshold


def _chunk_text(text: str, size: int = 512, overlap: int = 64) -> list[str]:
    """按段落优先切片，超长段落按字符切，并加少量重叠。"""
    paragraphs = [p.strip() for p in text.split("\n\n") if len(p.strip()) > 10]
    chunks, buf = [], ""
    for p in paragraphs:
        if len(buf) + len(p) + 1 <= size:
            buf = buf + "\n" + p if buf else p
        else:
            if buf:
                chunks.append(buf.strip())
            if len(p) > size:
                for i in range(0, len(p), size - overlap):
                    chunks.append(p[max(0, i - overlap):i + size].strip())
                buf = ""
            else:
                buf = p
    if buf:
        chunks.append(buf.strip())
    result = []
    for i, c in enumerate(chunks):
        if i == 0:
            result.append(c)
        else:
            tail = chunks[i-1][-overlap:] if len(chunks[i-1]) >= overlap else chunks[i-1]
            result.append(tail + " " + c)
    return [r for r in result if len(r.strip()) > 20]


def _extract_model(text: str) -> str | None:
    m = re.search(r'\b([A-Z]{2,}\d+[A-Z0-9\-]{0,10})\b', text)
    return m.group(1) if m else None


def _extract_pages(pdf_path: str) -> list[str]:
    """逐页提取文本（pypdf，纯 Python）。返回每页字符串列表。"""
    reader = PdfReader(pdf_path)
    pages: list[str] = []
    for pg in reader.pages:
        try:
            pages.append(pg.extract_text() or "")
        except Exception:
            pages.append("")
    return pages


def parse_pdf(pdf_path: str, doc_title: str = "") -> dict:
    """
    解析 PDF → 返回 {page_count, chunks:[{title, content, page_start, device_model}]}
    抛出 RuntimeError 表示解析能力不可用或文件无法读取。
    """
    if PdfReader is None:
        raise RuntimeError("PDF 解析依赖 pypdf 未安装（pip install pypdf）")
    if not Path(pdf_path).exists():
        raise RuntimeError(f"文件不存在: {pdf_path}")

    pages = _extract_pages(pdf_path)
    page_count = len(pages)
    fallback_title = (doc_title or Path(pdf_path).stem or "未命名文档").strip()

    chapters = []
    current = {"title": fallback_title, "content": "", "page_start": 1}
    for page_num, text in enumerate(pages):
        if _is_toc_page(text):
            continue
        for line in text.split("\n"):
            if _is_chapter_title(line):
                if current["content"].strip():
                    chapters.append(dict(current))
                current = {"title": line.strip(), "content": "", "page_start": page_num + 1}
            current["content"] += line + "\n"
    if current["content"].strip():
        chapters.append(current)

    chunks = []
    for ch in chapters:
        body = ch["content"].replace(ch["title"], "", 1).strip()
        if len(body) < 15:  # 剔除空壳章节（仅标题）
            continue
        for i, t in enumerate(_chunk_text(ch["content"])):
            chunks.append({
                "title":        ch["title"] if i == 0 else f"{ch['title']} (片段{i+1})",
                "content":      t,
                "page_start":   ch["page_start"],
                "device_model": _extract_model(ch["title"] + " " + t[:100]),
            })

    # 整篇无可识别章节时，兜底：全文按块切，统一挂在文档标题下
    if not chunks:
        full = "\n".join(pages)
        for i, t in enumerate(_chunk_text(full)):
            chunks.append({
                "title":        fallback_title if i == 0 else f"{fallback_title} (片段{i+1})",
                "content":      t,
                "page_start":   1,
                "device_model": _extract_model(t[:120]),
            })

    return {"page_count": page_count, "chunks": chunks}
