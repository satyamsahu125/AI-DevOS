#!/bin/bash
# Run just one stage for debugging

STAGE=${1:-"product_owner"}
REQUEST=${2:-"Build a todo app with user auth"}

echo "Running single stage: $STAGE"
curl -s -X POST http://localhost:8000/workflow/stage \
  -H "Content-Type: application/json" \
  -d "{
    \"stage\": \"$STAGE\",
    \"request\": \"$REQUEST\",
    \"project_id\": \"test-project-001\"
  }" | python -m json.tool

# Usage:
# ./test_single_stage.sh product_owner "Build a todo app"
# ./test_single_stage.sh designer "Build a todo app"
# ./test_single_stage.sh architect "Build a todo app"
