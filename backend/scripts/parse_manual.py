#!/usr/bin/env python3
"""
PDF 解析脚本：解析摩托车发动机维修手册.pdf
输出: /tmp/chapters.json

用法:
  python3 scripts/parse_manual.py \
      --pdf "D:/cnsoft/摩托车发动机维修手册.pdf" \
      --output /tmp/chapters.json \
      --img-dir /data/manual_images
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import re
import json
import argparse
from pathlib import Path

import io
try:
    from pypdf import PdfReader   # 纯 Python，LoongArch 可装；不引入 cryptography/Rust
except ImportError:
    print("请安装 pypdf: pip install pypdf")
    sys.exit(1)
try:
    from PIL import Image         # 图片尺寸过滤/转换（V11 用系统 RPM python3-pillow）
except ImportError:
    Image = None


# 章节标题正则：匹配「第X章」「X.X 标题」「一、 标题」等中文手册常见格式
CHAPTER_PATTERNS = [
    re.compile(r'^第[一二三四五六七八九十百\d]+章\s+\S'),
    re.compile(r'^\d+\.\d+[\s　]+\S'),
    re.compile(r'^[一二三四五六七八九十]+、\s*\S'),
    re.compile(r'^【.+】'),
]

def is_chapter_title(line: str) -> bool:
    line = line.strip()
    if len(line) < 3 or len(line) > 80:
        return False
    return any(p.match(line) for p in CHAPTER_PATTERNS)

def is_toc_page(text: str, ratio_threshold: float = 0.6) -> bool:
    """
    判断是否为目录页：非空短行中“章节标题样式”的占比超过阈值。
    手册前 1-2 页是目录，其标题与正文重名，若不剔除会因 ingest 按标题去重而
    误删真正的正文（首次出现的目录空壳胜出）。
    """
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    # 过滤页眉页脚（如 “No. 2 / 41”、书名）
    body = [l for l in lines if not re.match(r'^No\.\s*\d+\s*/\s*\d+$', l) and "维修手册" not in l]
    if len(body) < 6:
        return False
    title_like = sum(1 for l in body if is_chapter_title(l))
    return title_like / len(body) >= ratio_threshold

def chunk_text(text: str, size: int = 512, overlap: int = 64) -> list[str]:
    """按段落优先切片，超长段落按字符切"""
    paragraphs = [p.strip() for p in text.split("\n\n") if len(p.strip()) > 10]
    chunks, buf = [], ""
    for p in paragraphs:
        if len(buf) + len(p) + 1 <= size:
            buf = buf + "\n" + p if buf else p
        else:
            if buf:
                chunks.append(buf.strip())
            # 段落本身超长时按字符切
            if len(p) > size:
                for i in range(0, len(p), size - overlap):
                    chunks.append(p[max(0, i - overlap):i + size].strip())
            else:
                buf = p
    if buf:
        chunks.append(buf.strip())
    # 加重叠
    result = []
    for i, c in enumerate(chunks):
        if i == 0:
            result.append(c)
        else:
            tail = chunks[i-1][-overlap:] if len(chunks[i-1]) >= overlap else chunks[i-1]
            result.append(tail + " " + c)
    return [r for r in result if len(r.strip()) > 20]

def extract_model(text: str) -> str | None:
    """从文本中提取设备型号（如 CB125T-A）"""
    m = re.search(r'\b([A-Z]{2,}\d+[A-Z0-9\-]{0,10})\b', text)
    return m.group(1) if m else None

def parse_manual(pdf_path: str, img_dir: str) -> list[dict]:
    Path(img_dir).mkdir(parents=True, exist_ok=True)
    reader = PdfReader(pdf_path)
    pages  = reader.pages
    print(f"[INFO] 打开 PDF: {pdf_path}，共 {len(pages)} 页")

    chapters   = []
    current    = {"title": "前言", "content": "", "page_start": 0, "images": []}

    skipped_toc = 0
    for page_num, page in enumerate(pages):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""

        # 跳过目录页（标题与正文重名会导致 ingest 去重误删正文）
        if is_toc_page(text):
            skipped_toc += 1
            print(f"[INFO] 第 {page_num+1} 页判定为目录页，跳过")
            continue

        lines = text.split("\n")

        # 提取图片（pypdf page.images 纯 Python；Pillow 过滤过小装饰图并统一存 PNG）
        if Image is not None:
            try:
                for img_idx, image in enumerate(page.images):
                    try:
                        im = Image.open(io.BytesIO(image.data))
                        if im.width < 50 or im.height < 50:
                            continue  # 过滤过小图片（装饰图）
                        img_filename = f"p{page_num:04d}_i{img_idx:02d}.png"
                        img_path = os.path.join(img_dir, img_filename)
                        im.convert("RGB").save(img_path)
                        current["images"].append(img_path)
                    except Exception:
                        pass  # 部分图片可能无法提取
            except Exception:
                pass

        # 章节切分
        for line in lines:
            if is_chapter_title(line):
                if current["content"].strip():
                    chapters.append(dict(current))
                current = {
                    "title": line.strip(),
                    "content": "",
                    "page_start": page_num + 1,
                    "images": current["images"][-2:],  # 保留前一节最后2张图（可能跨页）
                }
            current["content"] += line + "\n"

    if current["content"].strip():
        chapters.append(current)

    print(f"[INFO] 跳过目录页 {skipped_toc} 页")
    print(f"[INFO] 章节切分完成，共 {len(chapters)} 章节")
    return chapters

def _content_without_title(ch: dict) -> str:
    """去掉标题行后的正文长度估算，用于剔除空壳章节"""
    body = ch["content"].replace(ch["title"], "", 1).strip()
    return body

def build_chunks(chapters: list[dict]) -> list[dict]:
    """将章节切成小块，每块 512 字符"""
    chunks = []
    dropped = 0
    for ch in chapters:
        # 剔除“空壳章节”（仅标题、几乎无正文）——目录残留或跨页噪声
        if len(_content_without_title(ch)) < 15:
            dropped += 1
            continue
        text_chunks = chunk_text(ch["content"])
        for i, text in enumerate(text_chunks):
            chunks.append({
                "title":      ch["title"] if i == 0 else f"{ch['title']} (片段{i+1})",
                "content":    text,
                "page_start": ch["page_start"],
                "images":     ch["images"] if i == 0 else [],
                "device_model": extract_model(ch["title"] + " " + text[:100]),
            })
    print(f"[INFO] 剔除空壳章节 {dropped} 个")
    print(f"[INFO] 段落切片完成，共 {len(chunks)} 块")
    return chunks

def main():
    parser = argparse.ArgumentParser(description="解析摩托车发动机维修手册 PDF")
    parser.add_argument("--pdf",     required=True, help="PDF 文件路径")
    parser.add_argument("--output",  default="/tmp/chapters.json", help="输出 JSON 路径")
    parser.add_argument("--img-dir", default="/data/manual_images", help="图片保存目录")
    args = parser.parse_args()

    chapters = parse_manual(args.pdf, args.img_dir)
    chunks   = build_chunks(chapters)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)

    print(f"[INFO] 解析完成，结果写入: {args.output}")
    print(f"[INFO] 共 {len(chapters)} 章节，{len(chunks)} 段落块")

if __name__ == "__main__":
    main()
