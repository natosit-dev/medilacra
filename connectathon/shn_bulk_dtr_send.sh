#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  connectathon/shn_bulk_dtr_send.sh DTR_BATCH_DIR [BASELINE_DIR]

Example:
  connectathon/shn_bulk_dtr_send.sh \
    connectathon/results/shn_bulk_dtr/shn_bulk_dtr_0300_0399

The runner retries HTTP 429 with Retry-After when supplied, otherwise a
65-second backoff. It refreshes the SHN token before retrying.
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
ENDPOINT='https://pa-test.shn-preview.org/Questionnaire/$questionnaire-package'

for cmd in curl jq; do
  command -v "$cmd" >/dev/null 2>&1 || {
    echo "missing required command: $cmd" >&2
    exit 2
  }
done

[[ -f "$MANIFEST" ]] || { echo "missing manifest: $MANIFEST" >&2; exit 2; }
[[ -x "$RUNNER" ]] || { echo "missing executable baseline runner: $RUNNER" >&2; exit 2; }
[[ -f "$BASELINE_DIR/client.json" ]] || {
  echo "missing SHN credential file: $BASELINE_DIR/client.json" >&2
  exit 2
}

mkdir -p "$LIVE_DIR"
chmod 700 "$LIVE_DIR"

printf '%s\n'   $'seed\tcase_id\thttp_status\tattempts\tpatient_id\tcoverage_id\texpected_questionnaire\treturned_questionnaire\treturned_qr_subject\treturned_qr_coverage\tidentity_match\tpackage_match\twarning_count\tx_correlation_id\tx_shn_leg_id\ttrace_url'   > "$LOG"

refresh_token() {
  "$RUNNER" token
  [[ -s "$TOKEN_FILE" ]] || {
    echo "token file was not created: $TOKEN_FILE" >&2
    exit 1
  }
}

header_value() {
  local name="$1"
  local file="$2"
  grep -i "^$name:" "$file" | tail -1 | cut -d: -f2- | tr -d '\r' | xargs || true
}

send_one() {
  local request_file="$1"
  local headers="$2"
  local body="$3"
  local cid="$4"
  local status

  status=$(
    printf 'header = "Authorization: Bearer %s"\n' "$(cat "$TOKEN_FILE")" |
      curl -sS --config -         -D "$headers"         -o "$body"         -w '%{http_code}'         "$ENDPOINT"         -H 'Content-Type: application/json'         -H "X-Correlation-Id: $cid"         --data-binary @"$request_file"
  )
  printf '%s' "$status"
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
  patient_id=$(jq -r '.patient_id' <<<"$row")
  coverage_id=$(jq -r '.coverage_id' <<<"$row")
  expected_q=$(jq -r '.questionnaire' <<<"$row")
  request_rel=$(jq -r '.request' <<<"$row")
  request_file="$BATCH_DIR/$request_rel"

  [[ -f "$request_file" ]] || {
    echo "missing DTR request for $case_id: $request_file" >&2
    exit 2
  }

  prefix="$LIVE_DIR/$case_id"
  body="$prefix.response.json"
  headers="$prefix.headers"
  cid="medilacra-dtr-${seed}-$(date -u +%Y%m%dT%H%M%SZ)"

  attempts=0
  while :; do
    attempts=$((attempts + 1))
    status=$(send_one "$request_file" "$headers" "$body" "$cid")

    if [[ "$status" != "429" || "$attempts" -ge 3 ]]; then
      break
    fi

    retry_after=$(header_value "retry-after" "$headers")
    if [[ ! "$retry_after" =~ ^[0-9]+$ ]]; then
      retry_after=65
    fi
    echo "429 for seed=$seed; waiting ${retry_after}s before retry" >&2
    sleep "$retry_after"
    refresh_token
  done

  xcid=$(header_value "x-correlation-id" "$headers")
  leg=$(header_value "x-shn-leg-id" "$headers")
  trace=""
  [[ -n "$xcid" ]] && trace="https://admin.shn-preview.org/connectathon/trace/$xcid"

  returned_q=""
  qr_subject=""
  qr_coverage=""
  warning_count=0
  identity_match="false"
  package_match="false"

  if [[ "$status" =~ ^2 ]]; then
    returned_q=$(jq -r '
      [
        .parameter[]?
        | select(.name == "packagebundle")
        | .resource.entry[]?.resource
        | select(.resourceType == "Questionnaire")
        | .url
      ][0] // ""
    ' "$body")

    qr_subject=$(jq -r '
      [
        .parameter[]?
        | select(.name == "packagebundle")
        | .resource.entry[]?.resource
        | select(.resourceType == "QuestionnaireResponse")
        | .subject.reference
      ][0] // ""
    ' "$body")

    qr_coverage=$(jq -r '
      [
        .parameter[]?
        | select(.name == "packagebundle")
        | .resource.entry[]?.resource
        | select(.resourceType == "QuestionnaireResponse")
        | .extension[]?
        | select(.url == "http://hl7.org/fhir/us/davinci-dtr/StructureDefinition/qr-coverage")
        | .valueReference.reference
      ][0] // ""
    ' "$body")

    warning_count=$(jq -r '
      [
        .parameter[]?
        | select(.name == "outcome")
        | .resource.issue[]?
        | select(.severity == "warning")
      ] | length
    ' "$body")

    if [[ "$qr_subject" == "Patient/$patient_id"        && "$qr_coverage" == "Coverage/$coverage_id" ]]; then
      identity_match="true"
    fi

    if [[ "$returned_q" == "$expected_q" ]]; then
      package_match="true"
    fi
  fi

  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n'     "$seed" "$case_id" "$status" "$attempts" "$patient_id" "$coverage_id"     "$expected_q" "$returned_q" "$qr_subject" "$qr_coverage" "$identity_match"     "$package_match" "$warning_count" "$xcid" "$leg" "$trace" >> "$LOG"

  printf '[%d/%s] seed=%s HTTP=%s attempts=%s identity=%s package=%s warnings=%s\n'     "$index" "$total" "$seed" "$status" "$attempts" "$identity_match"     "$package_match" "$warning_count"
done < <(jq -c '.cases[]' "$MANIFEST")

echo
echo "Bulk DTR run complete: $LOG"
echo
column -t -s $'\t' "$LOG"
