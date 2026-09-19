#!/bin/bash
set -u

echo "🚀 Đang khởi động hệ thống Huohuo AI VTuber..."

BASE_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)
BACKEND_DIR="$BASE_DIR/my-ai-app/backend"
FRONTEND_DIR="$BASE_DIR/my-ai-app"
SEARXNG_DIR="$BASE_DIR/infra/searxng"
OLLAMA_PID=""
OLLAMA_STARTED=0
SEARCH_PROVIDER="${WEB_SEARCH_PROVIDER:-searxng}"

# Đọc provider/model mà không source toàn bộ .env (tránh đưa secret vào môi trường con).
LLM_PROVIDER="${LLM_PROVIDER:-ollama}"
OLLAMA_MODEL="${OLLAMA_MODEL:-qwen3.5:4b}"
if [[ -f "$BACKEND_DIR/.env" ]]; then
  ENV_PROVIDER=$(sed -n 's/^LLM_PROVIDER=//p' "$BACKEND_DIR/.env" | head -n 1)
  ENV_MODEL=$(sed -n 's/^OLLAMA_MODEL=//p' "$BACKEND_DIR/.env" | head -n 1)
  ENV_SEARCH_PROVIDER=$(sed -n 's/^WEB_SEARCH_PROVIDER=//p' "$BACKEND_DIR/.env" | head -n 1)
  [[ -n "$ENV_PROVIDER" ]] && LLM_PROVIDER="$ENV_PROVIDER"
  [[ -n "$ENV_MODEL" ]] && OLLAMA_MODEL="$ENV_MODEL"
  [[ -n "$ENV_SEARCH_PROVIDER" ]] && SEARCH_PROVIDER="$ENV_SEARCH_PROVIDER"
fi

if [[ ! -d "$BACKEND_DIR" ]]; then
  echo "❌ Không tìm thấy backend tại: $BACKEND_DIR"
  exit 1
fi

if [[ ! -d "$FRONTEND_DIR" ]]; then
  echo "❌ Không tìm thấy frontend tại: $FRONTEND_DIR"
  exit 1
fi

start_ollama() {
  if [[ "$(printf '%s' "$LLM_PROVIDER" | tr '[:upper:]' '[:lower:]')" != "ollama" ]]; then
    echo "[1/3] LLM_PROVIDER=$LLM_PROVIDER, bỏ qua Ollama."
    return 0
  fi

  if ! command -v ollama >/dev/null 2>&1; then
    echo "❌ Không tìm thấy Ollama. Cài Ollama hoặc đổi LLM_PROVIDER trong backend/.env."
    exit 1
  fi

  if ! command -v curl >/dev/null 2>&1; then
    echo "❌ Không tìm thấy curl để kiểm tra Ollama."
    exit 1
  fi

  if ! curl -fsS --max-time 2 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    echo "[1/3] Ollama chưa chạy, đang khởi động..."
    ollama serve >"$BASE_DIR/ollama.log" 2>&1 &
    OLLAMA_PID=$!
    OLLAMA_STARTED=1

    for _ in {1..30}; do
      if curl -fsS --max-time 2 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
        break
      fi
      sleep 1
    done
  else
    echo "[1/3] Ollama đang chạy."
  fi

  if ! curl -fsS --max-time 2 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    echo "❌ Ollama không phản hồi. Xem log tại $BASE_DIR/ollama.log"
    exit 1
  fi

  if ! ollama list | awk 'NR > 1 {print $1}' | grep -Fxq "$OLLAMA_MODEL"; then
    echo "[1/3] Đang tải model $OLLAMA_MODEL (có thể mất vài phút)..."
    if ! ollama pull "$OLLAMA_MODEL"; then
      echo "❌ Không tải được model $OLLAMA_MODEL."
      exit 1
    fi
  fi

  echo "[1/3] Đang preload model $OLLAMA_MODEL..."
  if ! curl -fsS --max-time 180 http://127.0.0.1:11434/api/generate \
    -H "Content-Type: application/json" \
    -d "{\"model\":\"$OLLAMA_MODEL\",\"prompt\":\" \" ,\"stream\":false,\"keep_alive\":-1}" >/dev/null; then
    echo "❌ Không preload được model $OLLAMA_MODEL."
    exit 1
  fi
  echo "✅ Model $OLLAMA_MODEL đã sẵn sàng."
}

start_ollama

start_searxng() {
  if [[ "$(printf '%s' "$SEARCH_PROVIDER" | tr '[:upper:]' '[:lower:]')" != "searxng" ]]; then
    echo "[2/4] WEB_SEARCH_PROVIDER=$SEARCH_PROVIDER, bỏ qua SearXNG."
    return 0
  fi

  if [[ ! -d "$SEARXNG_DIR" ]]; then
    echo "❌ Không tìm thấy cấu hình SearXNG tại: $SEARXNG_DIR"
    exit 1
  fi
  if ! command -v docker >/dev/null 2>&1; then
    echo "❌ Không tìm thấy Docker để khởi động SearXNG. Hãy mở Docker Desktop."
    exit 1
  fi

  echo "[2/4] Đang khởi động SearXNG..."
  if ! (cd "$SEARXNG_DIR" && docker compose up -d); then
    echo "❌ Không khởi động được SearXNG."
    exit 1
  fi
  echo "✅ SearXNG đã sẵn sàng tại http://127.0.0.1:8080"
}

start_searxng

# Chạy Backend (FastAPI / MySQL)
echo "[3/4] Đang khởi động Backend FastAPI..."
cd "$BACKEND_DIR"
if [[ -x "$BACKEND_DIR/venv/bin/python" ]]; then
  BACKEND_PYTHON="$BACKEND_DIR/venv/bin/python"
elif [[ -x "$BACKEND_DIR/.venv/bin/python" ]]; then
  BACKEND_PYTHON="$BACKEND_DIR/.venv/bin/python"
else
  echo "⚠️ Không tìm thấy backend venv, dùng python mặc định."
  BACKEND_PYTHON="python"
fi
"$BACKEND_PYTHON" -m uvicorn main:app --reload &
BACKEND_PID=$!

# Chạy Frontend (React / Vite)
echo "[4/4] Đang khởi động Frontend..."
cd "$FRONTEND_DIR"
if command -v pnpm >/dev/null 2>&1; then
  pnpm run dev &
elif command -v npm >/dev/null 2>&1; then
  npm run dev &
else
  echo "❌ Không tìm thấy pnpm hoặc npm để chạy frontend."
  exit 1
fi
FRONTEND_PID=$!

cleanup() {
  echo "🛑 Đang tắt toàn bộ hệ thống..."
  if kill -0 "$BACKEND_PID" >/dev/null 2>&1; then
    kill "$BACKEND_PID" 2>/dev/null || true
  fi
  if kill -0 "$FRONTEND_PID" >/dev/null 2>&1; then
    kill "$FRONTEND_PID" 2>/dev/null || true
  fi
  if [[ "$OLLAMA_STARTED" -eq 1 ]] && [[ -n "$OLLAMA_PID" ]] && kill -0 "$OLLAMA_PID" >/dev/null 2>&1; then
    kill "$OLLAMA_PID" 2>/dev/null || true
  fi
  exit 0
}

trap cleanup SIGINT SIGTERM

echo "✅ Hoàn tất! Hệ thống chat đã online. Nhấn Ctrl+C để tắt các server."
wait
