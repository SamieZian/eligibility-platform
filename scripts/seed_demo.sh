#!/usr/bin/env bash
# Seed a rich demo dataset so reviewers see every state — active, terminated,
# pending (future effective), corrected (bitemporal).
#
# Runs AFTER `make seed` + `make ingest`. Uses the BFF GraphQL mutations so
# the full end-to-end pipeline (BFF → services → outbox → Pub/Sub → projector)
# gets exercised for every row.
set -euo pipefail

BFF=http://localhost:4000
T=11111111-1111-1111-1111-111111111111
H_CT="Content-Type: application/json"
H_T="X-Tenant-Id: $T"

c() { printf "\033[%sm%s\033[0m" "$1" "$2"; }
step() { echo; c 36 "▸ $1"; echo; }

# Send GraphQL via a JSON file to avoid shell-quoting hell.
gql_file() {
  local f=$1
  curl -sf -X POST "$BFF/graphql" -H "$H_CT" -H "$H_T" --data "@$f"
}

jp() { python3 -c "$1"; }

# ─── Wait for BFF ready ───
for _ in $(seq 1 30); do
  if curl -sf "$BFF/livez" >/dev/null 2>&1; then break; fi
  sleep 1
done

TMP=$(mktemp -d)
trap "rm -rf $TMP" EXIT

# ─── Resolve employer + plan IDs ───
step "Resolving employer + plan IDs"
cat > "$TMP/q_groups.json" <<'EOF'
{"query":"{ groupAdmin { id name } }"}
EOF
cat > "$TMP/q_plans.json" <<'EOF'
{"query":"{ plans { id planCode } }"}
EOF

GROUP_ADMIN_RESP=$(gql_file "$TMP/q_groups.json")
PLANS_RESP=$(gql_file "$TMP/q_plans.json")

EMP_SWIGGY=$(echo "$GROUP_ADMIN_RESP" | jp "import sys,json; print(next(e['id'] for e in json.load(sys.stdin)['data']['groupAdmin'] if e['name']=='Swiggy'))")
EMP_ZOMATO=$(echo "$GROUP_ADMIN_RESP" | jp "import sys,json; print(next(e['id'] for e in json.load(sys.stdin)['data']['groupAdmin'] if e['name']=='Zomato'))")
PLAN_GOLD=$(echo "$PLANS_RESP" | jp "import sys,json; print(next(p['id'] for p in json.load(sys.stdin)['data']['plans'] if p['planCode']=='PLAN-GOLD'))")
PLAN_SILVER=$(echo "$PLANS_RESP" | jp "import sys,json; print(next(p['id'] for p in json.load(sys.stdin)['data']['plans'] if p['planCode']=='PLAN-SILVER'))")
PLAN_BRONZE=$(echo "$PLANS_RESP" | jp "import sys,json; print(next(p['id'] for p in json.load(sys.stdin)['data']['plans'] if p['planCode']=='PLAN-BRONZE'))")

echo "  Swiggy=$EMP_SWIGGY"
echo "  Zomato=$EMP_ZOMATO"
echo "  Plans: GOLD=$PLAN_GOLD · SILVER=$PLAN_SILVER · BRONZE=$PLAN_BRONZE"

# ─── Helper: add a member by writing a temp JSON file + posting it ───
add_member() {
  local first=$1 last=$2 dob=$3 emp=$4 plan=$5 eff=$6
  # Quoted heredoc <<'PY' prevents bash from expanding $in / $first / etc.
  # We pass bash vars to Python via env instead.
  FIRST="$first" LAST="$last" DOB="$dob" EMP_ID="$emp" PLAN_ID="$plan" EFF="$eff" \
    python3 <<'PY' > "$TMP/add.json"
import json, os
print(json.dumps({
  "query": "mutation($in: AddMemberInput!) { addMember(input: $in) { memberId memberName } }",
  "variables": {"in": {
    "firstName": os.environ["FIRST"],
    "lastName": os.environ["LAST"],
    "dob": os.environ["DOB"],
    "employerId": os.environ["EMP_ID"],
    "planId": os.environ["PLAN_ID"],
    "relationship": "subscriber",
    "effectiveDate": os.environ["EFF"],
  }}
}))
PY
  gql_file "$TMP/add.json" | python3 -c "
import sys, json
d = json.load(sys.stdin).get('data', {}).get('addMember') or {}
name = d.get('memberName', '?')
mid = (d.get('memberId') or '-')[:8]
print(f'  + {name:25} ({mid})')
"
}

# ─── 1. Four PENDING members (effective 2026-08-01) ───
step "Adding 4 PENDING members (future-dated enrollments, effective 2026-08-01)"
add_member AARAV   AGARWAL  1992-03-14 "$EMP_SWIGGY" "$PLAN_GOLD"   2026-08-01
add_member ISHA    GUPTA    1995-07-22 "$EMP_SWIGGY" "$PLAN_SILVER" 2026-08-01
add_member KABIR   JAIN     1988-11-05 "$EMP_ZOMATO" "$PLAN_BRONZE" 2026-08-01
add_member ZARA    MALIK    1991-09-18 "$EMP_ZOMATO" "$PLAN_GOLD"   2026-08-01

sleep 2

# ─── 2. Terminate three existing members ───
step "Terminating 3 existing members (coverage ends 2026-06-30)"

terminate_one() {
  local ln=$1
  cat > "$TMP/q_find.json" <<EOF
{"query":"{ searchEnrollments(filter:{lastName:\"$ln\",status:\"active\"},page:{limit:1}){items{memberId memberName planId planName}} }"}
EOF
  local data
  data=$(gql_file "$TMP/q_find.json" | python3 -c "
import sys, json
items = json.load(sys.stdin)['data']['searchEnrollments']['items']
print(json.dumps(items[0]) if items else '{}')
")
  if [ "$data" = "{}" ]; then
    echo "  - no active $ln found, skipping"
    return
  fi
  local mid pid name
  mid=$(echo "$data" | python3 -c "import sys,json; print(json.load(sys.stdin)['memberId'])")
  pid=$(echo "$data" | python3 -c "import sys,json; print(json.load(sys.stdin)['planId'])")
  name=$(echo "$data" | python3 -c "import sys,json; print(json.load(sys.stdin)['memberName'])")
  MEMBER_ID="$mid" PLAN_ID="$pid" python3 <<'PY' > "$TMP/term.json"
import json, os
m = os.environ["MEMBER_ID"]
p = os.environ["PLAN_ID"]
print(json.dumps({
  "query": f'mutation {{ terminateEnrollment(memberId: "{m}", planId: "{p}", validTo: "2026-06-30") }}'
}))
PY
  gql_file "$TMP/term.json" >/dev/null
  echo "  ✗ $name → terminated 2026-06-30"
}

terminate_one REDDY
terminate_one DESAI
terminate_one KHAN

sleep 2

# ─── 3. Plan change (bitemporal saga) ───
step "Plan change saga: one SHARMA member switches Silver → Bronze on 2026-07-01"
cat > "$TMP/q_sharma.json" <<'EOF'
{"query":"{ searchEnrollments(filter:{lastName:\"SHARMA\",status:\"active\"},page:{limit:1}){items{memberId memberName planId employerId}} }"}
EOF
data=$(gql_file "$TMP/q_sharma.json" | python3 -c "
import sys, json
items = json.load(sys.stdin)['data']['searchEnrollments']['items']
print(json.dumps(items[0]) if items else '{}')
")
if [ "$data" != "{}" ]; then
  mid=$(echo "$data" | python3 -c "import sys,json; print(json.load(sys.stdin)['memberId'])")
  old=$(echo "$data" | python3 -c "import sys,json; print(json.load(sys.stdin)['planId'])")
  emp=$(echo "$data" | python3 -c "import sys,json; print(json.load(sys.stdin)['employerId'])")
  name=$(echo "$data" | python3 -c "import sys,json; print(json.load(sys.stdin)['memberName'])")
  MEMBER_ID="$mid" OLD_PLAN="$old" NEW_PLAN="$PLAN_BRONZE" EMPLOYER="$emp" \
    python3 <<'PY' > "$TMP/chg.json"
import json, os
m = os.environ["MEMBER_ID"]
op = os.environ["OLD_PLAN"]
np = os.environ["NEW_PLAN"]
e = os.environ["EMPLOYER"]
print(json.dumps({
  "query": f'mutation {{ changeEnrollmentPlan(memberId: "{m}", oldPlanId: "{op}", newPlanId: "{np}", employerId: "{e}", newValidFrom: "2026-07-01") }}'
}))
PY
  gql_file "$TMP/chg.json" >/dev/null
  echo "  ⟳ $name → Bronze Health starting 2026-07-01"
else
  echo "  - no active SHARMA found, skipping plan change"
fi

sleep 3

# ─── 4. Summary ───
step "Final state"

total_for() {
  local s=$1
  cat > "$TMP/q_cnt.json" <<EOF
{"query":"{ searchEnrollments(filter:{status:\"$s\"},page:{limit:200}){total} }"}
EOF
  gql_file "$TMP/q_cnt.json" | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['searchEnrollments']['total'])"
}

cat > "$TMP/q_all.json" <<'EOF'
{"query":"{ searchEnrollments(filter:{q:null},page:{limit:200}){total} }"}
EOF
TOTAL=$(gql_file "$TMP/q_all.json" | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['searchEnrollments']['total'])")

printf "  %-18s %s\n" "Total enrollments:" "$TOTAL"
for s in active pending termed; do
  printf "  %-18s %s\n" "  $s:" "$(total_for "$s")"
done

echo
c 32 "✅ Demo dataset ready."; echo
echo "   Open http://localhost:3000 and try:"
echo "   • Filter 'Pending' chip      → 4 future-dated enrollments (effective 2026-08-01)"
echo "   • Filter 'Terminated' chip   → 3 terminated members (end 2026-06-30)"
echo "   • Search 'sharma' → click row → timeline drawer"
echo "     shows plan-change bitemporal saga (2 segments)"
echo
