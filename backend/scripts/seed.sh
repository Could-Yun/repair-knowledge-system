#!/bin/bash
# 种子数据一键导入脚本（LoongArch + 银河麒麟 V11 桌面版）
# 使用方法: bash scripts/seed.sh
#
# LoongArch 提示：PyMuPDF 在 V11 上需源码编译（慢）。推荐改在 x86 机器先执行
#   python scripts/parse_manual.py --pdf 手册.pdf --output /tmp/chapters.json
# 把 /tmp/chapters.json scp 到 V11，本脚本会自动复用已存在的 chapters.json（跳过解析）。
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$(dirname "$SCRIPT_DIR")"
PDF_PATH="D:/cnsoft/摩托车发动机维修手册.pdf"
# LoongArch 环境下调整为实际路径
if [ -f "/opt/repair-system/data/摩托车发动机维修手册.pdf" ]; then
    PDF_PATH="/opt/repair-system/data/摩托车发动机维修手册.pdf"
fi

IMG_DIR="/data/manual_images"
CHAPTERS_JSON="/tmp/chapters.json"

cd "$BACKEND_DIR"

echo "=========================================="
echo "  设备检修系统 — 种子数据导入"
echo "=========================================="
echo ""

# 1. 初始化数据库（建表 + 默认账号）
echo "[Step 1/5] 初始化数据库..."
python3 scripts/init_db.py

# 2. PDF 解析（若已存在预解析的 chapters.json，则复用，跳过 PyMuPDF）
echo ""
if [ -f "$CHAPTERS_JSON" ]; then
    echo "[Step 2/5] 检测到已存在 $CHAPTERS_JSON，复用（跳过 PDF 解析）"
else
    echo "[Step 2/5] 解析 PDF 手册: $PDF_PATH"
    if [ ! -f "$PDF_PATH" ]; then
        echo "[WARN] PDF 文件不存在: $PDF_PATH"
        echo "       请将 摩托车发动机维修手册.pdf 放到上述路径，"
        echo "       或在 x86 机预解析出 $CHAPTERS_JSON 后 scp 到此处再重跑。"
        exit 1
    fi
    python3 scripts/parse_manual.py \
        --pdf "$PDF_PATH" \
        --output "$CHAPTERS_JSON" \
        --img-dir "$IMG_DIR"
fi

# 3. 入 knowledge_base
echo ""
echo "[Step 3/5] 向量化并写入知识库..."
python3 scripts/ingest_manual.py \
    --input "$CHAPTERS_JSON" \
    --device-type "摩托车发动机"

# 4. 建索引（数据导入后重建 IVFFlat，覆盖真实数据分布；SKILL 02 §3）
echo ""
echo "[Step 4/5] 创建/重建数据库索引..."
python3 scripts/create_indexes.py --lists 100

# 5. 知识图谱抽取（后台异步，不阻塞）
echo ""
echo "[Step 5/5] 启动知识图谱抽取（后台运行）..."
mkdir -p /var/log/repair-system
nohup python3 scripts/extract_kg.py \
    --source manual \
    --limit 200 \
    > /var/log/repair-system/kg_extract.log 2>&1 &
KG_PID=$!
echo "  KG 抽取进程 PID: $KG_PID，日志: /var/log/repair-system/kg_extract.log"

echo ""
echo "=========================================="
echo "  种子数据导入完成！"
echo "  PDF 章节数: $(python3 -c "import json; d=json.load(open('$CHAPTERS_JSON')); print(len(d))")"
echo "=========================================="
