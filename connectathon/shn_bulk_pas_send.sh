#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  connectathon/shn_bulk_pas_send.sh PAS_BATCH_DIR [BASELINE_DIR]

Example:
  connectathon/shn_bulk_pas_send.sh \
    connectathon/results/shn_bulk_pas/shn_bulk_pas_documented

Sends each documented PAS request sequentially. HTTP 429 is retried up to
three times using Retry-After when available, otherwise a 65-second backoff.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

BATCH_DIR="${1:-}"
BASELINE_DIR="${2:-connectathon/shn_live_baseline_00301}"

[[ -n "$BATCH_DIR" ]] || { usage >&2; exit 2; }

MANIFEST="$BATCH_DIR/manifest.json"
RUNNER="$BASELINE_DIR/run-00301.sh"
TOKEN_FILE="$BASELINE_DIR/out/.token"
LIVE_DIR="$BATCH_DIR/live"
LOG="$LIVE_DIR/run-log.tsv"
ENDPOINT='https://pa-test.shn-preview.org/Claim/$submit'

for cmd in curl jq; do
  command -v "$cmd" >/dev/null 2>&1 || {
    echo "missing required command: $cmd" >&2
    exit 2
  }
done

[[ -f "$MANIFEST" ]] || { echo "missing manifest: $MANIFEST" >&2; exit 2; }
[[ -x "$RUNNER" ]] || { echo "missing executable baseline runner: $RUNNER" >&2; exit 2; }

mkdir -p "$LIVE_DIR"
chmod 700 "$LIVE_DIR"

printf '%s\n'   $'seed\tcase_id\thttp_status\tattempts\toutcome\treview_code\treview_display\tcommunication_requests\tauthorization\tbehavior_match\tx_correlation_id\tx_shn_leg_id\ttrace_url'   > "$LOG"

refresh_token() {
  "$RUNNER" token >/dev/null
  [[ -s "$TOKEN_FILE" ]] || { echo "token missing" >&2; exit 1; }
}

header_value() {
  local name="$1"
  local file="$2"
  grep -i "^$name:" "$file" | tail -1 | cut -d: -f2- | tr -d '\r' | xargs || true
}

refresh_token
index=0
total=$(jq -r '.count' "$MANIFEST")

while IFS= read -r row; do
  index=$((index + 1))
  if (( index > 1 && (index - 1) % 25 == 0 )); then
    refresh_token
  fi

  seed=$(jq -r '.seed' <<<"$row")
  case_id=$(jq -r '.case_id' <<<"$row")
  req_rel=$(jq -r '.request' <<<"$row")
  exp_rel=$(jq -r '.expected' <<<"$row")
  request="$BATCH_DIR/$req_rel"
  expected="$BATCH_DIR/$exp_rel"
  prefix="$LIVE_DIR/$case_id"
  headers="$prefix.headers"
  body="$prefix.response.json"
  cid="medilacra-pas-${seed}-$(date -u +%Y%m%dT%H%M%SZ)"

  attempts=0
  while :; do
    attempts=$((attempts + 1))
    status=$(
      printf 'header = "Authorization: Bearer %s"\n' "$(cat "$TOKEN_FILE")" |
        curl -sS --config - \
          -D "$headers" \
          -o "$body" \
          -w '%{http_code}' \
          "$ENDPOINT" \
          -H 'Content-Type: application/fhir+json' \
          -H "X-Correlation-Id: $cid" \
          --data-binary @"$request"
    )

    if [[ "$status" != "429" || "$attempts" -ge 3 ]]; then
      break
    fi

    retry_after=$(header_value "retry-after" "$headers")
    [[ "$retry_after" =~ ^[0-9]+$ ]] || retry_after=65
    echo "429 for seed=$seed; waiting ${retry_after}s" >&2
    sleep "$retry_after"
    refresh_token
  done

  outcome=""
  review_code=""
  review_display=""
  comm_count=0
  authorization=""
  behavior_match=false

  if [[ "$status" =~ ^2 ]]; then
    outcome=$(jq -r '[.entry[]?.resource | select(.resourceType=="ClaimResponse") | .outcome][0] // ""' "$body")
    review_code=$(jq -r '[.. | objects | select((.url? // "") | endswith("extension-reviewActionCode")) | .valueCodeableConcept.coding[]?.code][0] // ""' "$body")
    review_display=$(jq -r '[.. | objects | select((.url? // "") | endswith("extension-reviewActionCode")) | .valueCodeableConcept.coding[]?.display][0] // ""' "$body")
    comm_count=$(jq -r '[.entry[]?.resource | select(.resourceType=="CommunicationRequest")] | length' "$body")
    authorization=$(jq -r '[.. | objects | select((.url? // "") | endswith("extension-reviewAction")) | .extension[]? | select(.url=="number") | .valueString][0] // ""' "$body")

    exp_outcome=$(jq -r '.expected_live_response.claim_response_outcome' "$expected")
    exp_code=$(jq -r '.expected_live_response.review_action_code' "$expected")
    exp_display=$(jq -r '.expected_live_response.review_action_display' "$expected")
    exp_comm=$(jq -r '.expected_live_response.communication_request_count' "$expected")

    if [[ "$outcome" == "$exp_outcome" \
       && "$review_code" == "$exp_code" \
       && "$review_display" == "$exp_display" \
       && "$comm_count" == "$exp_comm" \
       && -n "$authorization" ]]; then
      behavior_match=true
    fi
  fi

  xcid=$(header_value "x-correlation-id" "$headers")
  leg=$(header_value "x-shn-leg-id" "$headers")
  trace=""
  [[ -n "$xcid" ]] && trace="https://admin.shn-preview.org/connectathon/trace/$xcid"

  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$seed" "$case_id" "$status" "$attempts" "$outcome" "$review_code" \
    "$review_display" "$comm_count" "$authorization" "$behavior_match" \
    "$xcid" "$leg" "$trace" >> "$LOG"

  printf '[%d/%s] seed=%s HTTP=%s %s "%s" comm=%s auth=%s match=%s\n' \
    "$index" "$total" "$seed" "$status" "$review_code" "$review_display" \
    "$comm_count" "${authorization:-<none>}" "$behavior_match"
done < <(jq -c '.cases[]' "$MANIFEST")

echo
echo "Bulk PAS run complete: $LOG"
