#!/usr/bin/env bash
# ============================================================
# 一键启动：BGE 向量服务 + Qwen 对话模型 + 后端
#
# 放在 ~/cnsoft/repair-system/ 下使用（开发目录原本没有任何启动脚本，
# 只能一个一个手工起，这就是每次重启后 Embedding 静默降级为 mock 的原因）。
#
#   ./start_all.sh              # 全部启动（BGE 必启，Qwen 有模型就启）
#   ./start_all.sh --no-chat    # 只启 BGE + 后端，不启本地对话模型
#   ./stop_all.sh               # 全部停止
# ============================================================
set -Eeuo pipefail

BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$BASE_DIR/backend"
VENV_PY="${VENV_PY:-$HOME/.venvs/repair/bin/python}"
RUN_DIR="$BASE_DIR/.run"
LOG_DIR="$BACKEND_DIR/logs"

EMBED_PORT=11435          # 必须与 config.py 的 EMBED_LOCAL_URL 一致
CHAT_PORT=11434           # 必须与 .env 的 LOCAL_LLM_URL 一致
BACKEND_PORT=8000

START_CHAT=1
[ "${1:-}" = "--no-chat" ] && START_CHAT=0

mkdir -p "$RUN_DIR" "$LOG_DIR"

# ---------- 自动定位 llama-server 与模型 ----------
find_first() {
  for p in "$@"; do [ -f "$p" ] && { echo "$p"; return 0; }; done
  return 1
}

LLAMA_SERVER="$(find_first \
  "$HOME/53011414/third_party/llama_cpp/llama-server" \
  "$HOME/llama.cpp-master/build/bin/llama-server" \
  "$BASE_DIR/third_party/llama_cpp/llama-server" || true)"

EMBED_MODEL="$(find_first \
  "$HOME/53011414/models/bge-base-zh-v1.5-q8_0.gguf" \
  "$HOME/modelsyuan/bge-base-zh-v1.5-q8_0.gguf" || true)"

CHAT_MODEL="$(find_first \
  "$HOME/qwen2.5-1.5b-instruct-q4_k_m.gguf" \
  "$HOME/modelsyuan/qwen2.5-1.5b-instruct-q4_k_m.gguf" \
  "$HOME/53011414/models/qwen2.5-1.5b-instruct-q4_k_m.gguf" || true)"

log()  { echo "[INFO] $*"; }
warn() { echo "[WARN] $*" >&2; }

alive() { [ -f "$1" ] && kill -0 "$(cat "$1")" 2>/dev/null; }

wait_port() {                     # wait_port <port> <秒数> <名称>
  for _ in $(seq 1 "$2"); do
    if (echo > /dev/tcp/127.0.0.1/"$1") >/dev/null 2>&1; then
      echo "[ OK ] $3 就绪（端口 $1）"; return 0
    fi
    sleep 1
  done
  echo "[FAIL] $3 启动超时（端口 $1）" >&2; return 1
}

start_llama() {                   # start_llama <名称> <模型> <端口> [额外参数...]
  local name="$1" model="$2" port="$3"; shift 3
  local pid="$RUN_DIR/$name.pid" logf="$LOG_DIR/$name.log"
  if alive "$pid"; then log "$name 已在运行（PID $(cat "$pid")）"; return 0; fi
  [ -n "$LLAMA_SERVER" ] || { warn "未找到 llama-server，跳过 $name"; return 1; }
  [ -n "$model" ] && [ -f "$model" ] || { warn "未找到模型，跳过 $name"; return 1; }
  chmod +x "$LLAMA_SERVER" 2>/dev/null || true
  log "启动 $name（$port）..."
  nohup "$LLAMA_SERVER" -m "$model" --host 127.0.0.1 --port "$port" "$@" > "$logf" 2>&1 &
  echo $! > "$pid"
  wait_port "$port" 90 "$name" || { warn "详见 $logf"; return 1; }
}

echo "=============================================="
echo " 设备检修系统 · 一键启动"
echo "=============================================="

# 1) BGE 向量服务 —— 语义检索的必需组件，不是可选项
#    它不起来，Embedding 会降级为 mock 随机向量，检索静默失效
if ! start_llama "local_embed" "$EMBED_MODEL" "$EMBED_PORT" --embedding -t 2; then
  warn "BGE 未启动 → Embedding 将按 .env 的 EMBED_BACKEND 降级"
  warn "  若 EMBED_BACKEND=auto，会走云端 DashScope（注意：与本地 BGE 向量空间不同，"
  warn "  存量向量若是 BGE 编码的，需先用 revectorize.py 重算，否则检索质量会明显下降）"
  warn "  若 EMBED_BACKEND=llama，会直接掉进 mock 随机向量 —— 检索完全失效且无提示"
fi

# 2) Qwen 对话模型 —— 断网兜底，可选
if [ "$START_CHAT" = "1" ]; then
  start_llama "local_llm" "$CHAT_MODEL" "$CHAT_PORT" -c 2048 -t 2 || \
    warn "本地对话模型未启动，断网时诊断将不可用（云端仍正常）"
else
  log "按 --no-chat 跳过本地对话模型"
fi

# 3) 后端
PIDB="$RUN_DIR/backend.pid"
if alive "$PIDB"; then
  log "后端已在运行（PID $(cat "$PIDB")）"
else
  [ -x "$VENV_PY" ] || { echo "[ERROR] 未找到虚拟环境 Python：$VENV_PY"; exit 1; }

  # emoji 字体：工单打印/PDF 渲染用，缺了会导致部分字符显示成方块
  EMOJI_SRC="/usr/share/fonts/google-noto-emoji/NotoEmoji-Regular.ttf"
  EMOJI_DST="$BACKEND_DIR/static/fonts/emoji.ttf"
  if [ ! -f "$EMOJI_DST" ] && [ -f "$EMOJI_SRC" ]; then
    mkdir -p "$(dirname "$EMOJI_DST")"
    cp "$EMOJI_SRC" "$EMOJI_DST" && log "已部署 emoji 字体"
  fi

  log "启动后端（$BACKEND_PORT）..."
  cd "$BACKEND_DIR"
  nohup "$VENV_PY" -m uvicorn app.main:app --host 0.0.0.0 --port "$BACKEND_PORT" \
        > "$LOG_DIR/backend.log" 2>&1 &
  echo $! > "$PIDB"
  wait_port "$BACKEND_PORT" 60 "后端"
fi

# 4) 自检：确认 Embedding 真的没降级
echo
echo "---------- 启动自检 ----------"
sleep 2
MODE="$(grep -ah 'Embedding 模式' "$LOG_DIR/backend.log" "$LOG_DIR/app.log" 2>/dev/null | tail -1 || true)"
if [ -n "$MODE" ]; then
  echo "$MODE"
  case "$MODE" in
    *MOCK*) echo "[FAIL] Embedding 降级为随机向量，语义检索将完全失效！"
            echo "       检查：1) BGE 服务是否在 $EMBED_PORT 上；"
            echo "             2) .env 的 EMBED_BACKEND 是否为 auto（不要设成 llama）" ;;
    *)      echo "[ OK ] Embedding 未降级" ;;
  esac
else
  warn "未从日志读到 Embedding 模式，请手动确认：tail -f $LOG_DIR/backend.log"
fi

echo
echo "访问：http://127.0.0.1:$BACKEND_PORT"
echo "日志：$LOG_DIR/"
echo "停止：$BASE_DIR/stop_all.sh"
