#!/usr/bin/env bash
# 停止 start_all.sh 启动的全部服务
set -Eeuo pipefail

BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
RUN_DIR="$BASE_DIR/.run"

stop_one() {
  local name="$1" pid_file="$RUN_DIR/$1.pid"
  if [ ! -f "$pid_file" ]; then
    echo "[SKIP] $name 未记录 PID"
    return 0
  fi
  local pid; pid="$(cat "$pid_file")"
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null || true
    for _ in $(seq 1 10); do
      kill -0 "$pid" 2>/dev/null || break
      sleep 1
    done
    kill -0 "$pid" 2>/dev/null && kill -9 "$pid" 2>/dev/null || true
    echo "[ OK ] $name 已停止（PID $pid）"
  else
    echo "[SKIP] $name 进程已不存在"
  fi
  rm -f "$pid_file"
}

echo "停止服务..."
stop_one backend
stop_one local_llm
stop_one local_embed
echo "完成。"
