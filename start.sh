#!/bin/bash
set -Eeuo pipefail

echo "🚀 Đang khởi động hệ thống Huohuo AI VTuber..."

BASE_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)
BACKEND_DIR="$BASE_DIR/my-ai-app/backend"
FRONTEND_DIR="$BASE_DIR/my-ai-app"
SEARXNG_DIR="$BASE_DIR/infra/searxng"

OLLAMA_PID=""
BACKEND_PID=""
FRONTEND_PID=""
OLLAMA_STARTED=0
CLEANUP_DONE=0

cleanup() {
  local exit_code=$?
  local process_still_running=0
  if [[ "$CLEANUP_DONE" -eq 1 ]]; then
    return
  fi
  CLEANUP_DONE=1
  trap - EXIT INT TERM

  if [[ -n "$BACKEND_PID" ]] && kill -0 "$BACKEND_PID" >/dev/null 2>&1; then
    kill "$BACKEND_PID" 2>/dev/null || true
  fi
  if [[ -n "$FRONTEND_PID" ]] && kill -0 "$FRONTEND_PID" >/dev/null 2>&1; then
    kill "$FRONTEND_PID" 2>/dev/null || true
  fi
  if [[ "$OLLAMA_STARTED" -eq 1 ]] && [[ -n "$OLLAMA_PID" ]] && kill -0 "$OLLAMA_PID" >/dev/null 2>&1; then
    kill "$OLLAMA_PID" 2>/dev/null || true
  fi

  # Chờ tối đa 5 giây để các server đóng kết nối, sau đó buộc dừng nếu cần.
  for _ in {1..25}; do
    process_still_running=0
    [[ -n "$BACKEND_PID" ]] && kill -0 "$BACKEND_PID" >/dev/null 2>&1 && process_still_running=1
    [[ -n "$FRONTEND_PID" ]] && kill -0 "$FRONTEND_PID" >/dev/null 2>&1 && process_still_running=1
    [[ "$OLLAMA_STARTED" -eq 1 && -n "$OLLAMA_PID" ]] && kill -0 "$OLLAMA_PID" >/dev/null 2>&1 && process_still_running=1
    [[ "$process_still_running" -eq 0 ]] && break
    sleep 0.2
  done

  [[ -n "$BACKEND_PID" ]] && kill -0 "$BACKEND_PID" 2>/dev/null && kill -KILL "$BACKEND_PID" 2>/dev/null || true
  [[ -n "$FRONTEND_PID" ]] && kill -0 "$FRONTEND_PID" 2>/dev/null && kill -KILL "$FRONTEND_PID" 2>/dev/null || true
  [[ "$OLLAMA_STARTED" -eq 1 && -n "$OLLAMA_PID" ]] && kill -0 "$OLLAMA_PID" 2>/dev/null && kill -KILL "$OLLAMA_PID" 2>/dev/null || true

  [[ -n "$BACKEND_PID" ]] && wait "$BACKEND_PID" 2>/dev/null || true
  [[ -n "$FRONTEND_PID" ]] && wait "$FRONTEND_PID" 2>/dev/null || true
  [[ "$OLLAMA_STARTED" -eq 1 && -n "$OLLAMA_PID" ]] && wait "$OLLAMA_PID" 2>/dev/null || true

  if [[ -n "$BACKEND_PID" || -n "$FRONTEND_PID" || "$OLLAMA_STARTED" -eq 1 ]]; then
    echo "🛑 Đã tắt các tiến trình do start.sh khởi động."
  fi
  exit "$exit_code"
}

trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

if [[ ! -d "$BACKEND_DIR" ]]; then
  echo "❌ Không tìm thấy backend tại: $BACKEND_DIR"
  exit 1
fi

if [[ ! -f "$BACKEND_DIR/.env" ]]; then
  echo "❌ Chưa có $BACKEND_DIR/.env"
  echo "   Hãy sao chép backend/.env.example thành backend/.env và điền cấu hình thật."
  exit 1
fi

if [[ ! -f "$FRONTEND_DIR/package.json" ]]; then
  echo "❌ Không tìm thấy frontend package.json tại: $FRONTEND_DIR"
  exit 1
fi

if [[ -x "$BACKEND_DIR/venv/bin/python" ]]; then
  BACKEND_PYTHON="$BACKEND_DIR/venv/bin/python"
elif [[ -x "$BACKEND_DIR/.venv/bin/python" ]]; then
  BACKEND_PYTHON="$BACKEND_DIR/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  BACKEND_PYTHON=$(command -v python3)
  echo "⚠️ Không tìm thấy backend venv, dùng $BACKEND_PYTHON."
else
  echo "❌ Không tìm thấy Python để chạy backend."
  exit 1
fi

if command -v pnpm >/dev/null 2>&1; then
  FRONTEND_RUNNER="pnpm"
elif command -v npm >/dev/null 2>&1; then
  FRONTEND_RUNNER="npm"
else
  echo "❌ Không tìm thấy pnpm hoặc npm để chạy frontend."
  exit 1
fi

# Chỉ đọc các giá trị cần cho tiến trình khởi động, không source toàn bộ .env.
LLM_PROVIDER="${LLM_PROVIDER:-ollama}"
OLLAMA_MODEL="${OLLAMA_MODEL:-qwen3.5:4b}"
SEARCH_PROVIDER="${WEB_SEARCH_PROVIDER:-searxng}"
MEMORY_EMBEDDING_ENABLED="${MEMORY_EMBEDDING_ENABLED:-false}"
MEMORY_EMBEDDING_MODEL="${MEMORY_EMBEDDING_MODEL:-qwen3-embedding:0.6b}"
ENV_PROVIDER=$(sed -n 's/^LLM_PROVIDER=//p' "$BACKEND_DIR/.env" | head -n 1)
ENV_MODEL=$(sed -n 's/^OLLAMA_MODEL=//p' "$BACKEND_DIR/.env" | head -n 1)
ENV_SEARCH_PROVIDER=$(sed -n 's/^WEB_SEARCH_PROVIDER=//p' "$BACKEND_DIR/.env" | head -n 1)
ENV_EMBEDDING_ENABLED=$(sed -n 's/^MEMORY_EMBEDDING_ENABLED=//p' "$BACKEND_DIR/.env" | head -n 1)
ENV_EMBEDDING_MODEL=$(sed -n 's/^MEMORY_EMBEDDING_MODEL=//p' "$BACKEND_DIR/.env" | head -n 1)
[[ -n "$ENV_PROVIDER" ]] && LLM_PROVIDER="$ENV_PROVIDER"
[[ -n "$ENV_MODEL" ]] && OLLAMA_MODEL="$ENV_MODEL"
[[ -n "$ENV_SEARCH_PROVIDER" ]] && SEARCH_PROVIDER="$ENV_SEARCH_PROVIDER"
[[ -n "$ENV_EMBEDDING_ENABLED" ]] && MEMORY_EMBEDDING_ENABLED="$ENV_EMBEDDING_ENABLED"
[[ -n "$ENV_EMBEDDING_MODEL" ]] && MEMORY_EMBEDDING_MODEL="$ENV_EMBEDDING_MODEL"

is_enabled() {
  case "$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')" in
    1|true|yes|on) return 0 ;;
    *) return 1 ;;
  esac
}

ensure_ollama_model() {
  local model="$1"
  local purpose="$2"
  if ollama list | awk 'NR > 1 {print $1}' | grep -Fxq "$model"; then
    echo "✅ Model $purpose $model đã được cài."
    return 0
  fi

  echo "[1/5] Đang tải model $purpose $model (có thể mất vài phút)..."
  if ! ollama pull "$model"; then
    echo "❌ Không tải được model $purpose $model."
    return 1
  fi
}

start_ollama() {
  if [[ "$(printf '%s' "$LLM_PROVIDER" | tr '[:upper:]' '[:lower:]')" != "ollama" ]] && ! is_enabled "$MEMORY_EMBEDDING_ENABLED"; then
    echo "[1/5] LLM và embedding không dùng Ollama, bỏ qua Ollama."
    return 0
  fi

  if ! command -v ollama >/dev/null 2>&1; then
    echo "❌ Không tìm thấy Ollama. Hãy cài Ollama, hoặc tắt các cấu hình đang dùng Ollama trong backend/.env."
    exit 1
  fi
  if ! command -v curl >/dev/null 2>&1; then
    echo "❌ Không tìm thấy curl để kiểm tra Ollama."
    exit 1
  fi

  if ! curl -fsS --max-time 2 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    echo "[1/5] Ollama chưa chạy, đang khởi động..."
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
    echo "[1/5] Ollama đang chạy."
  fi

  if ! curl -fsS --max-time 2 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    echo "❌ Ollama không phản hồi. Xem log tại $BASE_DIR/ollama.log"
    exit 1
  fi

  if [[ "$(printf '%s' "$LLM_PROVIDER" | tr '[:upper:]' '[:lower:]')" == "ollama" ]]; then
    ensure_ollama_model "$OLLAMA_MODEL" "hội thoại" || exit 1
    echo "[1/5] Đang preload model hội thoại $OLLAMA_MODEL..."
    if ! curl -fsS --max-time 180 http://127.0.0.1:11434/api/generate \
      -H "Content-Type: application/json" \
      -d "{\"model\":\"$OLLAMA_MODEL\",\"prompt\":\" \" ,\"stream\":false,\"keep_alive\":-1}" >/dev/null; then
      echo "❌ Không preload được model hội thoại $OLLAMA_MODEL."
      exit 1
    fi
    echo "✅ Model hội thoại $OLLAMA_MODEL đã sẵn sàng."
  fi

  if is_enabled "$MEMORY_EMBEDDING_ENABLED"; then
    ensure_ollama_model "$MEMORY_EMBEDDING_MODEL" "embedding" || exit 1
    echo "[1/5] Đang preload model embedding $MEMORY_EMBEDDING_MODEL..."
    if ! curl -fsS --max-time 180 http://127.0.0.1:11434/api/embed \
      -H "Content-Type: application/json" \
      -d "{\"model\":\"$MEMORY_EMBEDDING_MODEL\",\"input\":\"khởi động bộ nhớ\",\"keep_alive\":-1}" >/dev/null; then
      echo "❌ Không preload được model embedding $MEMORY_EMBEDDING_MODEL."
      exit 1
    fi
    echo "✅ Model embedding $MEMORY_EMBEDDING_MODEL đã sẵn sàng."
  else
    echo "[1/5] MEMORY_EMBEDDING_ENABLED=$MEMORY_EMBEDDING_ENABLED, bỏ qua model embedding."
  fi
}

start_searxng() {
  if [[ "$(printf '%s' "$SEARCH_PROVIDER" | tr '[:upper:]' '[:lower:]')" != "searxng" ]]; then
    echo "[2/5] WEB_SEARCH_PROVIDER=$SEARCH_PROVIDER, bỏ qua SearXNG."
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

  echo "[2/5] Đang khởi động SearXNG..."
  if ! (cd "$SEARXNG_DIR" && docker compose up -d); then
    echo "❌ Không khởi động được SearXNG."
    exit 1
  fi
  echo "✅ SearXNG đã sẵn sàng tại http://127.0.0.1:8080"
}

run_migrations() {
  echo "[3/5] Đang kiểm tra và cập nhật schema MySQL..."
  if ! (cd "$BACKEND_DIR" && "$BACKEND_PYTHON" -m core.migrations); then
    echo "❌ Migration thất bại. Backend chưa được khởi động để tránh chạy với schema cũ."
    exit 1
  fi
  echo "✅ Schema MySQL đã sẵn sàng."
}

start_ollama
start_searxng
run_migrations

echo "[4/5] Đang khởi động Backend FastAPI..."
(
  cd "$BACKEND_DIR"
  exec "$BACKEND_PYTHON" -m uvicorn main:app --reload
) &
BACKEND_PID=$!

echo "[5/5] Đang khởi động Frontend..."
(
  cd "$FRONTEND_DIR"
  exec "$FRONTEND_RUNNER" run dev
) &
FRONTEND_PID=$!

echo "✅ Hoàn tất! Hệ thống chat đã online. Nhấn Ctrl+C để tắt các server."

# Theo dõi riêng backend/frontend; không chờ Ollama chạy vô hạn.
while true; do
  if ! kill -0 "$BACKEND_PID" >/dev/null 2>&1; then
    set +e
    wait "$BACKEND_PID"
    SERVICE_EXIT_CODE=$?
    set -e
    echo "❌ Backend đã dừng (mã $SERVICE_EXIT_CODE)."
    exit "$SERVICE_EXIT_CODE"
  fi
  if ! kill -0 "$FRONTEND_PID" >/dev/null 2>&1; then
    set +e
    wait "$FRONTEND_PID"
    SERVICE_EXIT_CODE=$?
    set -e
    echo "❌ Frontend đã dừng (mã $SERVICE_EXIT_CODE)."
    exit "$SERVICE_EXIT_CODE"
  fi
  sleep 1
done
