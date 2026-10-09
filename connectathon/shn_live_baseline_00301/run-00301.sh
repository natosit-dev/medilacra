#!/usr/bin/env bash
# shellcheck disable=SC2016  # the $-operation paths are literal, not expansions
# MediLacra first run against the SHN provider test endpoint, route 00301 (Da Vinci 2.2 line).
#
#   ./run-00301.sh register   # once: POST /register, saves client.json (mode 600)
#   ./run-00301.sh token      # POST /oauth/token (client_secret_basic); token lasts 5 min
#   ./run-00301.sh crd        # CRD order-sign; saves the questionnaire canonical
#   ./run-00301.sh dtr        # DTR $questionnaire-package with that canonical
#   ./run-00301.sh submit     # PAS Claim/$submit (expect a pend, A4)
#   ./run-00301.sh inquire    # PAS Claim/$inquire built from the submit body
#   ./run-00301.sh all        # token, crd, dtr, submit, inquire (stops at the first non-2xx)
#
# Bodies: crd-00301.json (reference 5.1), dtr-00301.json (reference 5.2),
# pas-00301.json (reference Appendix A); the inquiry is the quick-start 4 jq transform.
# Outputs: out/<step>.json (answer body), out/<step>.headers (answer headers only),
# out/run-log.tsv. The script never prints or saves the secret, the token or any request header.
set -euo pipefail

BASE="${BASE:-https://pa-test.shn-preview.org}"
CONSOLE="https://admin.shn-preview.org"
COVINFO="http://hl7.org/fhir/us/davinci-crd/StructureDefinition/ext-coverage-information"
INQUIRY_BUNDLE="http://hl7.org/fhir/us/davinci-pas/StructureDefinition/profile-pas-inquiry-request-bundle"
INQUIRY_CLAIM="http://hl7.org/fhir/us/davinci-pas/StructureDefinition/profile-claim-inquiry"
TOKEN_MAX_AGE=240   # seconds; tokens last 300 (reference 3)

cd "$(dirname "$0")"
umask 077
OUT=out
LOG="$OUT/run-log.tsv"

die() { echo "error: $*" >&2; exit 1; }
for t in curl jq; do command -v "$t" >/dev/null || die "$t is required"; done
mkdir -p "$OUT"
[ -f "$LOG" ] || printf 'time_utc\tstep\thttp_status\tsent_correlation_id\tx_correlation_id\tx_shn_leg_id\ttrace_url\n' > "$LOG"

now_utc() { date -u +%Y-%m-%dT%H:%M:%SZ; }

# header NAME FILE: the last value of a response header (curl -D may hold a 100-continue block first).
header() { grep -i "^$1:" "$2" | tail -n 1 | cut -d: -f2- | tr -d '\r' | sed 's/^ *//' || true; }

# --- register ------------------------------------------------------------------------------
do_register() {
  local body=register-medilacra.json tmp status
  if [ -e client.json ]; then die "client.json already exists: this client is registered. Reuse it (a new registration makes a new client and participant)."; fi
  jq -e . "$body" >/dev/null || die "$body is not valid JSON"
  if grep -q '[<>]' "$body"; then
    die "$body still has <placeholders>: put your name, email and system under test in it first"
  fi
  jq -e '[.client_name, .auth_method, .organization, .contact_name, .contact_email, .system_under_test, .participant_type]
         | all(type == "string" and length > 0)' "$body" >/dev/null \
    || die "$body: every field is required (reference 2)"
  tmp=$(mktemp client.json.XXXXXX)
  status=$(curl -sS -o "$tmp" -w '%{http_code}' "$BASE/register" \
    -H 'Content-Type: application/json' --data-binary @"$body")
  printf '%s\tregister\t%s\t\t\t\t\n' "$(now_utc)" "$status" >> "$LOG"
  if [ "$status" = 200 ] && jq -e '.client_id' "$tmp" >/dev/null 2>&1; then
    mv "$tmp" client.json && chmod 600 client.json
    echo "registered: HTTP 200, client_id $(jq -r .client_id client.json)"
    echo "client.json (mode 600) holds the one-time client_secret. Back it up somewhere private; it is never shown again."
  else
    echo "register: HTTP $status" >&2
    head -c 500 "$tmp" >&2; echo >&2   # a refusal is plain text, never a secret
    rm -f "$tmp"
    echo "look the text up under 'Registering' in the refusal guide" >&2
    exit 1
  fi
}

# --- token ---------------------------------------------------------------------------------
fetch_token() {
  local id secret status
  [ -f client.json ] || die "no client.json: run '$0 register' first"
  id=$(jq -r '.client_id // empty' client.json)
  secret=$(jq -r '.client_secret // empty' client.json)
  [ -n "$id" ] && [ -n "$secret" ] || die "client.json has no client_id/client_secret"
  # client_secret_basic, as `curl -u id:secret` (quick-start 2), but the credential goes
  # through curl's config on stdin so it is not on the command line (ps) or in any file we write.
  status=$(printf 'user = "%s:%s"\n' "$id" "$secret" | curl -sS --config - \
    -o "$OUT/token.raw" -w '%{http_code}' "$BASE/oauth/token" -d grant_type=client_credentials)
  printf '%s\ttoken\t%s\t\t\t\t\n' "$(now_utc)" "$status" >> "$LOG"
  if [ "$status" != 200 ]; then
    echo "token: HTTP $status $(cat "$OUT/token.raw")" >&2
    rm -f "$OUT/token.raw"
    echo "look it up under 'Getting a token' in the refusal guide" >&2
    exit 1
  fi
  jq -r '.access_token' "$OUT/token.raw" > "$OUT/.token"
  date +%s > "$OUT/.token.time"
  echo "token: HTTP 200, $(jq -r '"expires_in \(.expires_in)s, scope \(.scope)"' "$OUT/token.raw")"
  rm -f "$OUT/token.raw"
}

ensure_token() {
  local born=0
  [ -f "$OUT/.token.time" ] && born=$(cat "$OUT/.token.time")
  if [ ! -s "$OUT/.token" ] || [ $(( $(date +%s) - born )) -ge "$TOKEN_MAX_AGE" ]; then
    fetch_token
  fi
}

# --- one call ------------------------------------------------------------------------------
# call STEP PATH BODYFILE: POST with a fresh-enough token and our own X-Correlation-Id
# (allowed on every CRD, DTR and PAS call: reference 8.5). Sets CALL_STATUS.
call() {
  local step=$1 path=$2 body=$3 cid xcid leg trace link warn
  ensure_token
  cid="medilacra-${step}-$(date -u +%Y%m%dT%H%M%SZ)"
  CALL_STATUS=$(printf 'header = "Authorization: Bearer %s"\n' "$(cat "$OUT/.token")" | curl -sS --config - \
    -D "$OUT/$step.headers" -o "$OUT/$step.json" -w '%{http_code}' "$BASE$path" \
    -H 'Content-Type: application/json' -H "X-Correlation-Id: $cid" --data-binary @"$body")
  xcid=$(header X-Correlation-Id "$OUT/$step.headers")
  leg=$(header X-SHN-Leg-Id "$OUT/$step.headers")
  link=$(header Link "$OUT/$step.headers")
  warn=$(header Warning "$OUT/$step.headers")
  trace="$CONSOLE/connectathon/trace/${xcid:-$cid}"
  [ -n "$xcid" ] || trace="$trace (answer carried no id: find the call by time and client_id)"
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$(now_utc)" "$step" "$CALL_STATUS" "$cid" "$xcid" "$leg" "$trace" >> "$LOG"
  echo "== $step: HTTP $CALL_STATUS"
  echo "   X-Correlation-Id: ${xcid:-<none>}   (sent $cid)"
  echo "   X-SHN-Leg-Id:     ${leg:-<none>}"
  echo "   trace:            $trace"
  if [ -n "$link" ]; then echo "   Link: $link  (served under the canonical form; use that one)"; fi
  if [ -n "$warn" ]; then echo "   Warning: $warn"; fi
  echo "   body: $OUT/$step.json   headers: $OUT/$step.headers"
  if [ "${CALL_STATUS:0:1}" != 2 ]; then
    echo "   not 2xx: a refusal or failed exchange. First 600 bytes of the body:"
    head -c 600 "$OUT/$step.json"; echo
    echo "   look the text up in the refusal guide; send your SHN contact the X-Correlation-Id and the time"
    return 1
  fi
}

# --- CRD -----------------------------------------------------------------------------------
do_crd() {
  call crd /cds-services/shn-order-sign crd-00301.json
  # The canonical sits in the coverage-information extension on the systemActions update
  # (reference 1.4 and 5.1): systemActions[].resource.extension[url=ext-coverage-information]
  #   .extension[url=questionnaire].valueCanonical. Walk the whole answer, as tools/payersmoke does,
  # keep every one in order without repeats, exactly as written.
  jq -r --arg u "$COVINFO" '
    [ .. | objects | select(.url? == $u) | .extension[]? | select(.url == "questionnaire") | .valueCanonical // empty ]
    | reduce .[] as $c ([]; if index([$c]) then . else . + [$c] end) | .[]' \
    "$OUT/crd.json" > "$OUT/questionnaire-canonical.txt"
  jq -r --arg u "$COVINFO" '
    "   cards: \(.cards | length), systemActions: \(.systemActions | length)",
    ( .. | objects | select(.url? == $u) | .extension[]?
      | select(.url | IN("covered", "pa-needed", "doc-needed", "coverage-assertion-id"))
      | "   \(.url): \(.valueCode // .valueString)" )' "$OUT/crd.json"
  if [ -s "$OUT/questionnaire-canonical.txt" ]; then
    echo "   questionnaire: $(paste -sd' ' "$OUT/questionnaire-canonical.txt")  -> $OUT/questionnaire-canonical.txt"
  else
    echo "   no questionnaire canonical in the answer; dtr will refuse to run" >&2
    return 1
  fi
}

# --- DTR -----------------------------------------------------------------------------------
do_dtr() {
  [ -s "$OUT/questionnaire-canonical.txt" ] || die "no $OUT/questionnaire-canonical.txt: run '$0 crd' first"
  local qs
  qs=$(jq -R . "$OUT/questionnaire-canonical.txt" | jq -s .)
  # Replace dtr-00301.json's "questionnaire" parameter (valueCanonical) with the CRD answer's,
  # in the same place; everything else is sent as the reference has it.
  jq --argjson qs "$qs" '
    ($qs | map({name: "questionnaire", valueCanonical: .})) as $new
    | (.parameter | map(.name == "questionnaire") | index(true)) as $i
    | if $i == null then .parameter += $new
      else .parameter = (.parameter[:$i] + $new + (.parameter[$i:] | map(select(.name != "questionnaire")))) end' \
    dtr-00301.json > "$OUT/dtr-request.json"
  call dtr '/Questionnaire/$questionnaire-package' "$OUT/dtr-request.json"
  jq -r '
    (.parameter[]? | select(.name == "packagebundle") | .resource.entry
      | "   packagebundle: " + (map(.resource.resourceType) | group_by(.) | map("\(.[0]) x\(length)") | join(", "))),
    (.parameter[]? | select(.name == "outcome") | .resource.issue[]?
      | "   outcome \(.severity): \((.diagnostics // .details.text // "") | .[0:160])")' "$OUT/dtr.json"
  if ! grep -q 'FHIRHelpers' "$OUT/dtr.json"; then
    echo "   (no FHIRHelpers Library in the package: known on 00301, payer-side, not your bug)"
  fi
}

# --- PAS submit ----------------------------------------------------------------------------
do_submit() {
  call submit '/Claim/$submit' pas-00301.json
  date -u +%s > "$OUT/submit.time"
  jq -r '
    (.entry[]? | .resource | select(.resourceType == "ClaimResponse")
      | "   ClaimResponse outcome: \(.outcome)",
        ( [ .. | objects | select((.url? // "") | endswith("extension-reviewActionCode")) | .valueCodeableConcept.coding[0]
            | "\(.code) \"\(.display // "")\"" ] | unique | "   review action: " + join(", ") )),
    (.entry[]? | .resource | select(.resourceType == "CommunicationRequest")
      | "   CommunicationRequest \(.status): trace number \(.identifier[0].value), payload \(.payload[0].contentString // "-")")' \
    "$OUT/submit.json"
  jq -r '.entry[]? | .resource | select(.resourceType == "CommunicationRequest") | .identifier[0].value' \
    "$OUT/submit.json" > "$OUT/pas-trn.txt" || true
  echo "   (expect A4 Pending + a CommunicationRequest with 102089-0: reference 5.3)"
}

# --- PAS inquire ---------------------------------------------------------------------------
do_inquire() {
  local clearing last now trn n
  [ -f "$OUT/submit.time" ] || echo "note: no submit in this run yet; an inquiry finds only what the payer still holds" >&2
  # The 00301 payer is cleared nightly at 07:00 UTC from 10/07 to 10/14 (reference 1.5).
  if [ -f "$OUT/submit.time" ]; then
    now=$(date -u +%s); last=$(cat "$OUT/submit.time")
    clearing=$(( now / 86400 * 86400 + 7 * 3600 ))
    if [ "$clearing" -gt "$now" ]; then clearing=$(( clearing - 86400 )); fi
    if [ "$last" -lt "$clearing" ]; then
      echo "warning: your submit was before the last 07:00 UTC clearing; run '$0 submit' again first" >&2
    fi
  fi
  jq --arg b "$INQUIRY_BUNDLE" --arg c "$INQUIRY_CLAIM" '
    .meta.profile = [$b]
    | (.entry[] | select(.resource.resourceType == "Claim") | .resource.meta.profile) = [$c]' \
    pas-00301.json > "$OUT/inquire-00301.json"
  call inquire '/Claim/$inquire' "$OUT/inquire-00301.json"
  n=$(jq '[.. | objects | select(.resourceType? == "ClaimResponse")] | length' "$OUT/inquire.json")
  echo "   ClaimResponses in the answer: $n (every matching claim held since the last clearing, other participants' included: reference 1.6)"
  trn=$(cat "$OUT/pas-trn.txt" 2>/dev/null || true)
  if [ -n "$trn" ]; then
    if grep -qF "$trn" "$OUT/inquire.json"; then echo "   your submission ($trn) is in it"
    else echo "   your submission ($trn) is not in it (cleared since? submit again, wait a minute, inquire again)"; fi
  fi
}

case "${1:-}" in
  register) do_register ;;
  token)    fetch_token ;;
  crd)      do_crd ;;
  dtr)      do_dtr ;;
  submit)   do_submit ;;
  inquire)  do_inquire ;;
  all)      fetch_token; do_crd; do_dtr; do_submit; do_inquire ;;
  *) echo "usage: $0 register|token|crd|dtr|submit|inquire|all" >&2; exit 2 ;;
esac