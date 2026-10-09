#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  connectathon/shn_bulk_crd_send.sh BATCH_DIR [BASELINE_DIR]

Example:
  connectathon/shn_bulk_crd_send.sh \
    connectathon/results/shn_bulk_crd/shn_bulk_lumbar_fusion_0100_0109

BASELINE_DIR defaults to connectathon/shn_live_baseline_00301 and must contain
the local, gitignored client.json created during SHN registration.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

BATCH_DIR="${1:-}"
BASELINE_DIR="${2:-connectathon/shn_live_baseline_00301}"

if [[ -z "$BATCH_DIR" ]]; then
  usage >&2
  exit 2
fi

MANIFEST="$BATCH_DIR/manifest.json"
RUNNER="$BASELINE_DIR/run-00301.sh"
TOKEN_FILE="$BASELINE_DIR/out/.token"
LIVE_DIR="$BATCH_DIR/live"
LOG="$LIVE_DIR/run-log.tsv"

for cmd in curl jq; do
  command -v "$cmd" >/dev/null 2>&1 || {
    echo "missing required command: $cmd" >&2
    exit 2
  }
done

[[ -f "$MANIFEST" ]] || {
  echo "missing manifest: $MANIFEST" >&2
  exit 2
}
[[ -x "$RUNNER" ]] || {
  echo "missing executable baseline runner: $RUNNER" >&2
  exit 2
}
[[ -f "$BASELINE_DIR/client.json" ]] || {
  echo "missing SHN credential file: $BASELINE_DIR/client.json" >&2
  exit 2
}

mkdir -p "$LIVE_DIR"
chmod 700 "$LIVE_DIR"

printf '%s\n'   $'seed\tcase_id\thttp_status\tpatient_id\tcoverage_id\tservice_request_id\treturned_service_request_id\treturned_patient_ref\treturned_coverage_ref\tidentity_match\tcovered\tpa_needed\tdoc_needed\tinfo_needed\tquestionnaire\tx_correlation_id\tx_shn_leg_id\ttrace_url'   > "$LOG"

refresh_token() {
  "$RUNNER" token
  [[ -s "$TOKEN_FILE" ]] || {
    echo "token file was not created: $TOKEN_FILE" >&2
    exit 1
  }
}

coverage_value() {
  local body="$1"
  local key="$2"
  jq -r --arg key "$key" '
    [
      .systemActions[]?.resource.extension[]?
      | select(.url == "http://hl7.org/fhir/us/davinci-crd/StructureDefinition/ext-coverage-information")
      | .extension[]?
      | select(.url == $key)
      | (
          .valueCode //
          .valueCanonical //
          .valueString //
          .valueDate //
          .valueReference.reference //
          empty
        )
    ][0] // ""
  ' "$body"
}

refresh_token

index=0
while IFS= read -r row; do
  index=$((index + 1))

  # Refresh well before the five-minute token lifetime for larger cohorts.
  if (( index > 1 && (index - 1) % 25 == 0 )); then
    refresh_token
  fi

  seed=$(jq -r '.seed' <<<"$row")
  case_id=$(jq -r '.case_id' <<<"$row")
  patient_id=$(jq -r '.patient_id' <<<"$row")
  coverage_id=$(jq -r '.coverage_id' <<<"$row")
  order_id=$(jq -r '.service_request_id' <<<"$row")
  request_rel=$(jq -r '.request' <<<"$row")
  request_file="$BATCH_DIR/$request_rel"

  [[ -f "$request_file" ]] || {
    echo "missing request for $case_id: $request_file" >&2
    exit 2
  }

  prefix="$LIVE_DIR/$case_id"
  body="$prefix.response.json"
  headers="$prefix.headers"
  cid="medilacra-bulk-crd-${seed}-$(date -u +%Y%m%dT%H%M%SZ)"

  status=$(
    printf 'header = "Authorization: Bearer %s"\n' "$(cat "$TOKEN_FILE")" |
      curl -sS --config -         -D "$headers"         -o "$body"         -w '%{http_code}'         'https://pa-test.shn-preview.org/cds-services/shn-order-sign'         -H 'Content-Type: application/json'         -H "X-Correlation-Id: $cid"         --data-binary @"$request_file"
  )

  xcid=$(grep -i '^x-correlation-id:' "$headers" | tail -1 | cut -d: -f2- | tr -d '\r' | xargs || true)
  leg=$(grep -i '^x-shn-leg-id:' "$headers" | tail -1 | cut -d: -f2- | tr -d '\r' | xargs || true)
  trace=""
  [[ -n "$xcid" ]] && trace="https://admin.shn-preview.org/connectathon/trace/$xcid"

  returned_order=""
  returned_patient=""
  returned_coverage=""
  covered=""
  pa_needed=""
  doc_needed=""
  info_needed=""
  questionnaire=""
  identity_match="false"

  if [[ "$status" =~ ^2 ]]; then
    returned_order=$(jq -r '.systemActions[0].resource.id // ""' "$body")
    returned_patient=$(jq -r '.systemActions[0].resource.subject.reference // ""' "$body")
    returned_coverage=$(jq -r '.systemActions[0].resource.insurance[0].reference // ""' "$body")
    covered=$(coverage_value "$body" "covered")
    pa_needed=$(coverage_value "$body" "pa-needed")
    doc_needed=$(coverage_value "$body" "doc-needed")
    info_needed=$(coverage_value "$body" "info-needed")
    questionnaire=$(coverage_value "$body" "questionnaire")

    if [[ "$returned_order" == "$order_id"        && "$returned_patient" == "Patient/$patient_id"        && "$returned_coverage" == "Coverage/$coverage_id" ]]; then
      identity_match="true"
    fi
  fi

  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n'     "$seed" "$case_id" "$status" "$patient_id" "$coverage_id" "$order_id"     "$returned_order" "$returned_patient" "$returned_coverage" "$identity_match"     "$covered" "$pa_needed" "$doc_needed" "$info_needed" "$questionnaire"     "$xcid" "$leg" "$trace" >> "$LOG"

  printf '[%d/%s] seed=%s HTTP=%s identity=%s covered=%s pa=%s questionnaire=%s\n'     "$index" "$(jq -r '.count' "$MANIFEST")" "$seed" "$status" "$identity_match"     "${covered:-<none>}" "${pa_needed:-<none>}" "${questionnaire:-<none>}"
done < <(jq -c '.cases[]' "$MANIFEST")

echo
echo "Bulk CRD run complete: $LOG"
echo
column -t -s $'\t' "$LOG"
