#!/bin/bash
set -e

echo "=== AI DevOS Startup ==="

# Check Ollama is running
echo "[1/4] Checking Ollama..."
if ! curl -s http://localhost:11434/api/tags > /dev/null; then
    echo "ERROR: Ollama is not running."
    echo "Start it with: ollama serve"
    echo "Pull model with: ollama pull qwen2.5-coder:7b"
    exit 1
fi
echo "  Ollama OK"

# Check model is available
echo "[2/4] Checking model..."
if ! curl -s http://localhost:11434/api/tags | grep -q "qwen2.5-coder"; then
    echo "Pulling qwen2.5-coder:7b..."
    ollama pull qwen2.5-coder:7b
fi
echo "  Model OK"

# Install dependencies
echo "[3/4] Installing dependencies..."
pip install -r backend/requirements.txt -q
echo "  Dependencies OK"

# Run tests
echo "[4/4] Running tests..."
cd backend
if ! python -m pytest tests/ -v --tb=short -q; then
    echo "ERROR: Tests failed. Fix before running."
    exit 1
fi
echo "  All tests passed"

# Start server
echo ""
echo "=== Starting AI DevOS API ==="
echo "API: http://localhost:8000"
echo "Docs: http://localhost:8000/docs"
echo ""
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --reload-exclude "temp-workspace"
