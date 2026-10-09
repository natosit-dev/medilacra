#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  connectathon/shn_lumbar_fusion_pas_send.sh PAS_CASE_DIR [BASELINE_DIR]

Example:
  connectathon/shn_lumbar_fusion_pas_send.sh \
    connectathon/results/shn_lumbar_fusion_pas/shn_lumbar_fusion_0300

Posts one documented lumbar-fusion PAS request to the SHN provider-test
Claim/$submit endpoint and records the payer response without mutating the request.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

CASE_DIR="${1:-}"
BASELINE_DIR="${2:-connectathon/shn_live_baseline_00301}"

[[ -n "$CASE_DIR" ]] || { usage >&2; exit 2; }

REQUEST="$CASE_DIR/pas_request.json"
EXPECTED="$CASE_DIR/expected_pas_behavior.json"
RUNNER="$BASELINE_DIR/run-00301.sh"
TOKEN_FILE="$BASELINE_DIR/out/.token"
LIVE_DIR="$CASE_DIR/live"
BODY="$LIVE_DIR/submit.response.json"
HEADERS="$LIVE_DIR/submit.headers"
SUMMARY="$LIVE_DIR/submit-summary.json"

for cmd in curl jq; do
  command -v "$cmd" >/dev/null 2>&1 || {
    echo "missing required command: $cmd" >&2
    exit 2
  }
done

[[ -f "$REQUEST" ]] || { echo "missing PAS request: $REQUEST" >&2; exit 2; }
[[ -f "$EXPECTED" ]] || { echo "missing PAS expectation: $EXPECTED" >&2; exit 2; }
[[ -x "$RUNNER" ]] || { echo "missing executable baseline runner: $RUNNER" >&2; exit 2; }
[[ -f "$BASELINE_DIR/client.json" ]] || {
  echo "missing SHN credential file: $BASELINE_DIR/client.json" >&2
  exit 2
}

mkdir -p "$LIVE_DIR"
chmod 700 "$LIVE_DIR"

"$RUNNER" token
[[ -s "$TOKEN_FILE" ]] || {
  echo "token file was not created: $TOKEN_FILE" >&2
  exit 1
}

seed=$(jq -r '.seed' "$EXPECTED")
cid="medilacra-pas-${seed}-$(date -u +%Y%m%dT%H%M%SZ)"

status=$(
  printf 'header = "Authorization: Bearer %s"\n' "$(cat "$TOKEN_FILE")" |
    curl -sS --config - \
      -D "$HEADERS" \
      -o "$BODY" \
      -w '%{http_code}' \
      'https://pa-test.shn-preview.org/Claim/$submit' \
      -H 'Content-Type: application/fhir+json' \
      -H "X-Correlation-Id: $cid" \
      --data-binary @"$REQUEST"
)

header_value() {
  local name="$1"
  grep -i "^$name:" "$HEADERS" | tail -1 | cut -d: -f2- | tr -d '\r' | xargs || true
}

xcid=$(header_value "x-correlation-id")
leg=$(header_value "x-shn-leg-id")
trace=""
[[ -n "$xcid" ]] && trace="https://admin.shn-preview.org/connectathon/trace/$xcid"

outcome=""
review_code=""
review_display=""
comm_count=0
authorization=""
behavior_match=false

if [[ "$status" =~ ^2 ]]; then
  outcome=$(jq -r '
    [
      .entry[]?.resource
      | select(.resourceType == "ClaimResponse")
      | .outcome
    ][0] // ""
  ' "$BODY")

  review_code=$(jq -r '
    [
      ..
      | objects
      | select((.url? // "") | endswith("extension-reviewActionCode"))
      | .valueCodeableConcept.coding[]?.code
    ][0] // ""
  ' "$BODY")

  review_display=$(jq -r '
    [
      ..
      | objects
      | select((.url? // "") | endswith("extension-reviewActionCode"))
      | .valueCodeableConcept.coding[]?.display
    ][0] // ""
  ' "$BODY")

  comm_count=$(jq -r '
    [.entry[]?.resource | select(.resourceType == "CommunicationRequest")] | length
  ' "$BODY")

  authorization=$(jq -r '
    [
      ..
      | objects
      | select((.url? // "") | endswith("extension-reviewAction"))
      | .extension[]?
      | select(.url == "number")
      | .valueString
    ][0] // ""
  ' "$BODY")

  expected_outcome=$(jq -r '.expected_live_response.claim_response_outcome' "$EXPECTED")
  expected_code=$(jq -r '.expected_live_response.review_action_code' "$EXPECTED")
  expected_display=$(jq -r '.expected_live_response.review_action_display' "$EXPECTED")
  expected_comm=$(jq -r '.expected_live_response.communication_request_count' "$EXPECTED")
  expected_auth=$(jq -r '.expected_live_response.authorization_expected' "$EXPECTED")

  authorization_match=false
  if [[ "$expected_auth" == "false" || -n "$authorization" ]]; then
    authorization_match=true
  fi

  if [[ "$outcome" == "$expected_outcome" \
     && "$review_code" == "$expected_code" \
     && "$review_display" == "$expected_display" \
     && "$comm_count" == "$expected_comm" \
     && "$authorization_match" == "true" ]]; then
    behavior_match=true
  fi
fi

jq -n \
  --argjson http_status "$status" \
  --arg outcome "$outcome" \
  --arg review_action_code "$review_code" \
  --arg review_action_display "$review_display" \
  --argjson communication_request_count "$comm_count" \
  --arg authorization "$authorization" \
  --argjson behavior_match "$behavior_match" \
  --arg x_correlation_id "$xcid" \
  --arg x_shn_leg_id "$leg" \
  --arg trace_url "$trace" \
  '{
    http_status: $http_status,
    claim_response_outcome: $outcome,
    review_action_code: $review_action_code,
    review_action_display: $review_action_display,
    communication_request_count: $communication_request_count,
    authorization: ($authorization | if length == 0 then null else . end),
    authorization_match: ($authorization | length > 0),
    behavior_match: $behavior_match,
    x_correlation_id: $x_correlation_id,
    x_shn_leg_id: $x_shn_leg_id,
    trace_url: $trace_url
  }' > "$SUMMARY"

echo "PAS submit:"
echo "  HTTP:                 $status"
echo "  ClaimResponse outcome: ${outcome:-<none>}"
echo "  review action:         ${review_code:-<none>} ${review_display:+\"$review_display\"}"
echo "  CommunicationRequests: $comm_count"
echo "  authorization:         ${authorization:-<none>}"
echo "  behavior match:        $behavior_match"
echo "  X-Correlation-Id:      ${xcid:-<none>}"
echo "  X-SHN-Leg-Id:          ${leg:-<none>}"
echo "  trace:                 ${trace:-<none>}"
echo "  body:                  $BODY"
echo "  summary:               $SUMMARY"

if [[ ! "$status" =~ ^2 ]]; then
  echo
  echo "First 800 bytes of refusal:"
  head -c 800 "$BODY"
  echo
  exit 1
fi
