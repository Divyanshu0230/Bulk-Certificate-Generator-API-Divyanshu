#!/usr/bin/env bash
# Submit examples/request.json, wait until the job finishes, and save the zip.
# Usage: scripts/demo.sh [base_url]
set -euo pipefail

BASE="${1:-http://127.0.0.1:8000}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/examples/output"
mkdir -p "$OUT"

RESPONSE="$(curl -sS -X POST "$BASE/api/v1/jobs" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: demo-$(date +%s)" \
  --data-binary @"$ROOT/examples/request.json")"

echo "$RESPONSE" | python3 -m json.tool
JOB_ID="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["id"])' "$RESPONSE")"

for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do
  STATUS_BODY="$(curl -sS "$BASE/api/v1/jobs/$JOB_ID")"
  STATE="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["status"])' "$STATUS_BODY")"
  echo "status=$STATE"
  case "$STATE" in
    completed|completed_with_errors|failed) break ;;
  esac
  sleep 0.4
done

curl -sS -o "$OUT/certificates.zip" "$BASE/api/v1/jobs/$JOB_ID/archive"
curl -sS -o "$OUT/report.csv" "$BASE/api/v1/jobs/$JOB_ID/report"
echo "Saved $OUT/certificates.zip"
echo "Saved $OUT/report.csv"
echo "Verify the first certificate from the CSV, or open $BASE/docs"
