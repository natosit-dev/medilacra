#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  connectathon/shn_rule_matrix_send.sh MATRIX_DIR [BASELINE_DIR]

Example:
  connectathon/shn_rule_matrix_send.sh \
    connectathon/results/shn_rule_matrix/shn_rule_matrix_0200_0208

The baseline directory defaults to connectathon/shn_live_baseline_00301 and
must contain the local gitignored client.json created during SHN registration.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

MATRIX_DIR="${1:-}"
BASELINE_DIR="${2:-connectathon/shn_live_baseline_00301}"

[[ -n "$MATRIX_DIR" ]] || { usage >&2; exit 2; }

MANIFEST="$MATRIX_DIR/manifest.json"
RUNNER="$BASELINE_DIR/run-00301.sh"
TOKEN_FILE="$BASELINE_DIR/out/.token"
LIVE_DIR="$MATRIX_DIR/live"
LOG="$LIVE_DIR/run-log.tsv"

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

printf '%s\n'   $'seed\tscenario\tservice_code\thttp_status\tpatient_id\tcoverage_id\tservice_request_id\tidentity_match\tbehavior_match\tcovered\tpa_needed\tdoc_needed\tinfo_needed\tquestionnaire\texpected_crd\tx_correlation_id\tx_shn_leg_id\ttrace_url'   > "$LOG"

refresh_token() {
  "$RUNNER" token
  [[ -s "$TOKEN_FILE" ]] || {
    echo "token file was not created: $TOKEN_FILE" >&2
    exit 1
  }
}

coverage_object() {
  local body="$1"
  jq -c '
    (
      [
        .systemActions[]?.resource.extension[]?
        | select(.url == "http://hl7.org/fhir/us/davinci-crd/StructureDefinition/ext-coverage-information")
        | .extension[]?
        | {
            key: .url,
            value: (
              .valueCode //
              .valueCanonical //
              .valueString //
              .valueDate //
              .valueReference.reference //
              null
            )
          }
      ]
      | from_entries
    ) as $found
    | {
        "covered": ($found["covered"] // null),
        "pa-needed": ($found["pa-needed"] // null),
        "doc-needed": ($found["doc-needed"] // null),
        "info-needed": ($found["info-needed"] // null),
        "questionnaire": ($found["questionnaire"] // null)
      }
  ' "$body"
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
  scenario=$(jq -r '.scenario' <<<"$row")
  service_code=$(jq -r '.service_code' <<<"$row")
  case_id=$(jq -r '.case_id' <<<"$row")
  patient_id=$(jq -r '.patient_id' <<<"$row")
  coverage_id=$(jq -r '.coverage_id' <<<"$row")
  order_id=$(jq -r '.service_request_id' <<<"$row")
  request_rel=$(jq -r '.request' <<<"$row")
  expected=$(jq -c '.expected_crd' <<<"$row")
  request_file="$MATRIX_DIR/$request_rel"

  [[ -f "$request_file" ]] || {
    echo "missing request for $case_id: $request_file" >&2
    exit 2
  }

  prefix="$LIVE_DIR/$case_id"
  body="$prefix.response.json"
  headers="$prefix.headers"
  cid="medilacra-rule-${seed}-${scenario}-$(date -u +%Y%m%dT%H%M%SZ)"

  status=$(
    printf 'header = "Authorization: Bearer %s"\n' "$(cat "$TOKEN_FILE")" |
      curl -sS --config -         -D "$headers"         -o "$body"         -w '%{http_code}'         'https://pa-test.shn-preview.org/cds-services/shn-order-sign'         -H 'Content-Type: application/json'         -H "X-Correlation-Id: $cid"         --data-binary @"$request_file"
  )

  xcid=$(grep -i '^x-correlation-id:' "$headers" | tail -1 | cut -d: -f2- | tr -d '\r' | xargs || true)
  leg=$(grep -i '^x-shn-leg-id:' "$headers" | tail -1 | cut -d: -f2- | tr -d '\r' | xargs || true)
  trace=""
  [[ -n "$xcid" ]] && trace="https://admin.shn-preview.org/connectathon/trace/$xcid"

  identity_match="false"
  behavior_match="false"
  actual='{"covered":null,"pa-needed":null,"doc-needed":null,"info-needed":null,"questionnaire":null}'

  if [[ "$status" =~ ^2 ]]; then
    returned_order=$(jq -r '.systemActions[0].resource.id // ""' "$body")
    returned_patient=$(jq -r '.systemActions[0].resource.subject.reference // ""' "$body")
    returned_coverage=$(jq -r '.systemActions[0].resource.insurance[0].reference // ""' "$body")

    if [[ "$returned_order" == "$order_id"        && "$returned_patient" == "Patient/$patient_id"        && "$returned_coverage" == "Coverage/$coverage_id" ]]; then
      identity_match="true"
    fi

    actual=$(coverage_object "$body")
    behavior_match=$(jq -nr       --argjson expected "$expected"       --argjson actual "$actual"       'reduce ($expected | keys[]) as $k
         (true; . and ($actual[$k] == $expected[$k]))')
  fi

  covered=$(jq -r '."covered" // ""' <<<"$actual")
  pa_needed=$(jq -r '."pa-needed" // ""' <<<"$actual")
  doc_needed=$(jq -r '."doc-needed" // ""' <<<"$actual")
  info_needed=$(jq -r '."info-needed" // ""' <<<"$actual")
  questionnaire=$(jq -r '."questionnaire" // ""' <<<"$actual")

  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n'     "$seed" "$scenario" "$service_code" "$status" "$patient_id" "$coverage_id"     "$order_id" "$identity_match" "$behavior_match" "$covered" "$pa_needed"     "$doc_needed" "$info_needed" "$questionnaire" "$expected" "$xcid" "$leg" "$trace"     >> "$LOG"

  printf '[%d/%s] seed=%s scenario=%s code=%s HTTP=%s identity=%s behavior=%s\n'     "$index" "$total" "$seed" "$scenario" "$service_code" "$status"     "$identity_match" "$behavior_match"
done < <(jq -c '.cases[]' "$MANIFEST")

echo
echo "Rule matrix complete: $LOG"
echo
column -t -s $'\t' "$LOG"
