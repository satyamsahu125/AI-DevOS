#!/bin/bash

BASE_URL="http://localhost:8000"

echo "=== AI DevOS End-to-End Test ==="

# 1. Health check
echo "[1] Health check..."
curl -s "$BASE_URL/health" | python -m json.tool
echo ""

# 2. Create project
echo "[2] Creating project..."
PROJECT=$(curl -s -X POST "$BASE_URL/projects" \
  -H "Content-Type: application/json" \
  -d '{"name": "Test App", "description": "A simple todo app"}')
echo "$PROJECT" | python -m json.tool
PROJECT_ID=$(echo "$PROJECT" | python -c "import sys,json; print(json.load(sys.stdin)['project']['project_id'])")
echo "Project ID: $PROJECT_ID"
echo ""

# 3. Start workflow (runs the ProductOwner stage)
echo "[3] Starting workflow..."
curl -s -X POST "$BASE_URL/workflow/start" \
  -H "Content-Type: application/json" \
  -d "{\"project_id\": \"$PROJECT_ID\", \"request\": \"Build a todo app with user authentication\"}" \
  | python -m json.tool
echo ""

# 4. Check workflow status
echo "[4] Checking status..."
curl -s "$BASE_URL/workflow/$PROJECT_ID" | python -m json.tool
echo ""

echo "=== Test complete ==="
