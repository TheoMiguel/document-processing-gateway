#!/usr/bin/env bash
# smoke_test.sh — end-to-end smoke test for the Document Processing Gateway
# Usage: bash scripts/smoke_test.sh [API_BASE_URL]
# Default URL: http://localhost:8000

set -euo pipefail

BASE="${1:-http://localhost:8000}"
PASS=0
FAIL=0

green() { printf '\033[32m%s\033[0m\n' "$*"; }
red()   { printf '\033[31m%s\033[0m\n' "$*"; }
bold()  { printf '\033[1m%s\033[0m\n' "$*"; }

ok() {
  green "  PASS: $1"
  ((PASS++))
}

fail() {
  red "  FAIL: $1"
  red "        $2"
  ((FAIL++))
}

assert_eq() {
  local label="$1" expected="$2" actual="$3"
  if [ "$expected" = "$actual" ]; then
    ok "$label"
  else
    fail "$label" "expected='$expected' got='$actual'"
  fi
}

assert_contains() {
  local label="$1" needle="$2" haystack="$3"
  if echo "$haystack" | grep -q "$needle"; then
    ok "$label"
  else
    fail "$label" "expected to contain '$needle'"
  fi
}

poll_status() {
  local job_id="$1" expected_status="$2" max_wait="${3:-15}"
  local elapsed=0 status=""
  while [ "$elapsed" -lt "$max_wait" ]; do
    status=$(curl -sf "$BASE/api/v1/jobs/$job_id" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])" 2>/dev/null || echo "error")
    if [ "$status" = "$expected_status" ]; then
      echo "$status"
      return 0
    fi
    sleep 1
    ((elapsed++))
  done
  echo "$status"
}

# ---------------------------------------------------------------------------

bold "=== Document Processing Gateway — Smoke Test ==="
echo "Target: $BASE"
echo ""

# 1. Health check
bold "[ 1 ] Health check"
HEALTH=$(curl -sf "$BASE/health" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])" 2>/dev/null || echo "error")
assert_eq "GET /health returns ok" "ok" "$HEALTH"

# 2. Full pipeline
bold "[ 2 ] Full pipeline — all three stages"
RESPONSE=$(curl -sf -X POST "$BASE/api/v1/jobs" \
  -H "Content-Type: application/json" \
  -d '{"document_name":"smoke_full.txt","document_type":"report","document_content":"The quick brown fox jumps over the lazy dog with complex terminology and specialized jargon.","pipeline_config":["extraction","analysis","enrichment"]}')
JOB_FULL=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
INIT_STATUS=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])")
assert_eq "POST /jobs returns pending" "pending" "$INIT_STATUS"

FINAL=$(poll_status "$JOB_FULL" "completed" 20)
assert_eq "Job reaches completed" "completed" "$FINAL"

RESULT=$(curl -sf "$BASE/api/v1/jobs/$JOB_FULL")
KEYS=$(echo "$RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(sorted(d['partial_results'].keys()))" 2>/dev/null || echo "error")
assert_eq "partial_results has extraction+analysis+enrichment" "['analysis', 'enrichment', 'extraction']" "$KEYS"

# 3. Partial pipeline — extraction only
bold "[ 3 ] Partial pipeline — extraction only"
JOB_PARTIAL=$(curl -sf -X POST "$BASE/api/v1/jobs" \
  -H "Content-Type: application/json" \
  -d '{"document_name":"smoke_partial.txt","document_type":"invoice","document_content":"Invoice 999","pipeline_config":["extraction"]}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

FINAL=$(poll_status "$JOB_PARTIAL" "completed" 15)
assert_eq "Single-stage job completes" "completed" "$FINAL"

KEYS=$(curl -sf "$BASE/api/v1/jobs/$JOB_PARTIAL" | python3 -c "import sys,json; d=json.load(sys.stdin); print(list(d['partial_results'].keys()))")
assert_eq "partial_results only has extraction" "['extraction']" "$KEYS"

# 4. Stage order enforcement (config out of order)
bold "[ 4 ] Stage order enforcement"
JOB_ORDER=$(curl -sf -X POST "$BASE/api/v1/jobs" \
  -H "Content-Type: application/json" \
  -d '{"document_name":"smoke_order.txt","document_type":"contract","document_content":"Order enforcement test document","pipeline_config":["enrichment","extraction","analysis"]}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

FINAL=$(poll_status "$JOB_ORDER" "completed" 20)
assert_eq "Out-of-order config job completes" "completed" "$FINAL"

# 5. List and filter
bold "[ 5 ] List jobs and filter by status"
LIST=$(curl -sf "$BASE/api/v1/jobs" | python3 -c "import sys,json; print(type(json.load(sys.stdin)).__name__)")
assert_eq "GET /jobs returns list" "list" "$LIST"

COMPLETED=$(curl -sf "$BASE/api/v1/jobs?status=completed" | python3 -c "import sys,json; jobs=json.load(sys.stdin); print(all(j['status']=='completed' for j in jobs))")
assert_eq "Status filter returns only completed" "True" "$COMPLETED"

# 6. Job not found
bold "[ 6 ] Job not found (404)"
STATUS_CODE=$(curl -so /dev/null -w "%{http_code}" "$BASE/api/v1/jobs/00000000-0000-0000-0000-000000000000")
assert_eq "GET /jobs/<invalid-id> returns 404" "404" "$STATUS_CODE"

STATUS_CODE=$(curl -so /dev/null -w "%{http_code}" -X DELETE "$BASE/api/v1/jobs/00000000-0000-0000-0000-000000000000")
assert_eq "DELETE /jobs/<invalid-id> returns 404" "404" "$STATUS_CODE"

# 7. Cancel a completed job (conflict)
bold "[ 7 ] Cancel completed job returns 409"
JOB_DONE=$(curl -sf -X POST "$BASE/api/v1/jobs" \
  -H "Content-Type: application/json" \
  -d '{"document_name":"smoke_cancel.txt","document_type":"report","document_content":"Cancel conflict test","pipeline_config":["extraction"]}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

poll_status "$JOB_DONE" "completed" 15 > /dev/null

STATUS_CODE=$(curl -so /dev/null -w "%{http_code}" -X DELETE "$BASE/api/v1/jobs/$JOB_DONE")
assert_eq "DELETE completed job returns 409" "409" "$STATUS_CODE"

# 8. Validation errors
bold "[ 8 ] Input validation errors"
STATUS_CODE=$(curl -so /dev/null -w "%{http_code}" -X POST "$BASE/api/v1/jobs" \
  -H "Content-Type: application/json" \
  -d '{"document_name":"x","document_type":"y","document_content":"z","pipeline_config":[]}')
assert_eq "Empty pipeline_config returns 422" "422" "$STATUS_CODE"

STATUS_CODE=$(curl -so /dev/null -w "%{http_code}" -X POST "$BASE/api/v1/jobs" \
  -H "Content-Type: application/json" \
  -d '{"document_name":"x","document_type":"y","document_content":"z","pipeline_config":["invalid_stage"]}')
assert_eq "Invalid stage name returns 422" "422" "$STATUS_CODE"

STATUS_CODE=$(curl -so /dev/null -w "%{http_code}" -X POST "$BASE/api/v1/jobs" \
  -H "Content-Type: application/json" \
  -d '{"document_name":"missing_fields"}')
assert_eq "Missing required fields returns 422" "422" "$STATUS_CODE"

# 9. Concurrent submissions
bold "[ 9 ] Concurrent submissions (5 jobs)"
PIDS=()
JOB_IDS=()
for i in $(seq 1 5); do
  RESP=$(curl -sf -X POST "$BASE/api/v1/jobs" \
    -H "Content-Type: application/json" \
    -d "{\"document_name\":\"concurrent$i.txt\",\"document_type\":\"report\",\"document_content\":\"Concurrent test $i\",\"pipeline_config\":[\"extraction\"]}")
  JOB_IDS+=("$(echo "$RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")")
done

sleep 10  # let all pipelines finish

ALL_COMPLETED=true
for jid in "${JOB_IDS[@]}"; do
  S=$(curl -sf "$BASE/api/v1/jobs/$jid" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])" 2>/dev/null)
  if [ "$S" != "completed" ]; then
    ALL_COMPLETED=false
    break
  fi
done
assert_eq "All 5 concurrent jobs completed" "true" "$ALL_COMPLETED"

# ---------------------------------------------------------------------------

echo ""
bold "=== Results ==="
green "  Passed: $PASS"
if [ "$FAIL" -gt 0 ]; then
  red "  Failed: $FAIL"
  exit 1
else
  green "  Failed: $FAIL"
  green "All checks passed."
fi
