#!/bin/bash
set -e

echo "=========================================="
echo "    OREHACK Auto-Updating Worker          "
echo "=========================================="

echo "[1/5] Fetching latest code from GitHub..."
REPO_URL="https://github.com/sasvanthu/OREGENT-Orehack.git"
BRANCH="OREHACK-CLI-Backend"

if [ ! -d "/app/src" ]; then
    echo "Cloning repository ($BRANCH) for the first time..."
    git clone -b $BRANCH $REPO_URL /app/src
else
    echo "Pulling latest updates from GitHub..."
    cd /app/src
    git fetch origin
    git reset --hard origin/$BRANCH
fi

cd /app/src

echo ""
echo "[2/5] Updating Dependencies..."
if [ -f "requirements.txt" ]; then
    pip install --no-cache-dir -r requirements.txt
else
    echo "Warning: No requirements.txt found in repository."
fi

# Emergency fallback in case the GitHub repo doesn't have the OLLAMA_URL fix yet
sed -i 's|OLLAMA_URL     = "http://localhost:11434/api/generate"|OLLAMA_URL     = os.environ.get("OLLAMA_URL", "http://ollama:11434/api/generate")|g' llm/ollama_client.py || true

echo ""
echo "[3/5] Detecting Hardware..."
TOTAL_MEM=$(free -m | awk '/^Mem:/{print $2}')
echo "Total Memory: ${TOTAL_MEM} MB"

HAS_GPU=false
if command -v nvidia-smi &> /dev/null; then
    echo "NVIDIA GPU Detected!"
    nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
    HAS_GPU=true
else
    echo "No NVIDIA GPU detected in container. Running on CPU."
fi

echo ""
echo "[4/5] Validating Model Requirements..."
MODEL=${OLLAMA_MODEL:-"deepseek-coder:6.7b"}
echo "Requested Model: ${MODEL}"

if [[ "$MODEL" == "deepseek-coder:6.7b" && "$TOTAL_MEM" -lt 4000 ]]; then
    echo "=========================================="
    echo " ERROR: INSUFFICIENT MEMORY FOR MODEL     "
    echo "=========================================="
    echo " The default model '$MODEL' requires at least 4GB of RAM."
    echo " Your system only has ${TOTAL_MEM} MB available."
    echo " Please edit the '.env' file and add:"
    echo " OLLAMA_MODEL=deepseek-coder:1.3b"
    echo " or another smaller model, then restart."
    echo "=========================================="
    exit 1
fi
echo "Hardware meets requirements for $MODEL."

echo ""
echo "[5/5] Connecting to Ollama..."
OLLAMA_URL=${OLLAMA_URL:-"http://ollama:11434"}

max_retries=30
count=0
until curl -s ${OLLAMA_URL} > /dev/null; do
    echo "Waiting for Ollama to start at ${OLLAMA_URL}..."
    sleep 2
    count=$((count+1))
    if [ $count -gt $max_retries ]; then
        echo "Error: Ollama did not start in time."
        exit 1
    fi
done
echo "Ollama is running."

echo "Checking if model '$MODEL' is installed..."
MODEL_CHECK=$(curl -s ${OLLAMA_URL}/api/tags | grep "\"${MODEL}\"" || true)

if [ -z "$MODEL_CHECK" ]; then
    echo "Model '$MODEL' not found. Downloading now (this may take a while)..."
    curl -X POST ${OLLAMA_URL}/api/pull -d "{\"name\": \"${MODEL}\"}" -H "Content-Type: application/json"
    echo "Download complete."
else
    echo "Model '$MODEL' is already installed."
fi

echo ""
echo "Starting OREHACK worker..."
exec python worker.py
