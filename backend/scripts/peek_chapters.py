#!/usr/bin/env python3
"""快速查看 /tmp/chapters.json 解析质量（确认中文无乱码）。用法: python scripts/peek_chapters.py"""
import json, sys

path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/chapters.json"
d = json.load(open(path, encoding="utf-8"))
print("count:", len(d))
for i in (0, 10, 30, 50):
    if i < len(d):
        c = d[i]
        print(f"\n--- chunk[{i}] ---")
        print("title:", c.get("title"))
        print("body :", (c.get("content") or "")[:220])
        print("model:", c.get("device_model"), " page:", c.get("page_start"))
