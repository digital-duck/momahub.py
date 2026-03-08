#!/usr/bin/env bash
# setup.sh — One-command node bootstrap for Momahub (Momahub).
# Idempotent: safe to re-run. Handles GPU check, Ollama install,
# model pull, pip install, smoke test, and prints the join command.
set -euo pipefail

# ── Helpers ──────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; }

MODELS="${MODELS:-llama3}"   # override: MODELS="llama3 mistral" ./setup.sh

# ── Stage 1: GPU check ──────────────────────────────────────────
info "Stage 1/5: Checking GPU..."
if command -v nvidia-smi &>/dev/null; then
    GPU_INFO=$(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null || true)
    if [ -n "$GPU_INFO" ]; then
        info "GPU detected: $GPU_INFO"
    else
        warn "nvidia-smi found but no GPU reported — will run CPU-only."
    fi
else
    warn "nvidia-smi not found — will run CPU-only (slower inference)."
fi

# ── Stage 2: Ollama ─────────────────────────────────────────────
info "Stage 2/5: Checking Ollama..."
if command -v ollama &>/dev/null; then
    info "Ollama already installed: $(ollama --version 2>/dev/null || echo 'unknown version')"
else
    info "Installing Ollama..."
    curl -fsSL https://ollama.com/install.sh | sh
    info "Ollama installed."
fi

# Ensure Ollama is running
if ! curl -sf http://localhost:11434/api/version &>/dev/null; then
    info "Starting Ollama service..."
    if command -v systemctl &>/dev/null; then
        sudo systemctl start ollama 2>/dev/null || ollama serve &>/dev/null &
    else
        ollama serve &>/dev/null &
    fi
    sleep 3
    if ! curl -sf http://localhost:11434/api/version &>/dev/null; then
        error "Could not start Ollama. Please start it manually: ollama serve"
        exit 1
    fi
fi
info "Ollama is running."

# ── Stage 3: Pull models ────────────────────────────────────────
info "Stage 3/5: Pulling models..."
for model in $MODELS; do
    short_name=$(echo "$model" | cut -d: -f1)
    if ollama list 2>/dev/null | grep -q "$short_name"; then
        info "  $model — already present."
    else
        info "  Pulling $model (this may take a while)..."
        ollama pull "$model"
    fi
done

# ── Stage 4: Install Momahub ────────────────────────────────────
info "Stage 4/5: Installing Momahub..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if pip show moma-hub &>/dev/null; then
    info "moma-hub already installed."
else
    pip install -e "${SCRIPT_DIR}[dev]"
    info "moma-hub installed."
fi

# ── Stage 5: Smoke test ─────────────────────────────────────────
info "Stage 5/5: Smoke test..."
FIRST_MODEL=$(echo "$MODELS" | awk '{print $1}')
RESPONSE=$(curl -sf http://localhost:11434/api/generate \
    -d "{\"model\":\"${FIRST_MODEL}\",\"prompt\":\"Say hello in 5 words.\",\"stream\":false}" \
    2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('response','ERROR')[:80])" 2>/dev/null || echo "FAILED")

if [ "$RESPONSE" = "FAILED" ]; then
    warn "Smoke test failed — Ollama may still be loading the model. Try again in a minute."
else
    info "Smoke test passed: $RESPONSE"
fi

# ── Print join command ───────────────────────────────────────────
LAN_IP=$(python3 -c "
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
try:
    s.connect(('8.8.8.8', 80))
    print(s.getsockname()[0])
finally:
    s.close()
" 2>/dev/null || echo "127.0.0.1")

echo ""
info "=== Setup complete ==="
echo ""
echo "  To start a hub on this machine:"
echo "    moma hub up --host 0.0.0.0 --port 8000"
echo ""
echo "  To join an existing hub as an agent:"
echo "    moma join http://<HUB_IP>:8000 --host ${LAN_IP} --port 8100"
echo ""
echo "  This machine's LAN IP: ${LAN_IP}"
echo ""
