#!/usr/bin/env bash
# Seed a rich demo dataset so reviewers see every state — active, terminated,
# pending (future effective), corrected (bitemporal).
#
# Runs AFTER `make seed` + `make ingest`. Uses the BFF GraphQL mutations so the
# full end-to-end pipeline (BFF → services → outbox → Pub/Sub → projector)
# gets exercised for every row.
set -euo pipefail

BFF=http://localhost:4000
T=11111111-1111-1111-1111-111111111111
H_CT="Content-Type: application/json"
H_T="X-Tenant-Id: $T"

c() { printf "\033[%sm%s\033[0m" "$1" "$2"; }
step() { echo; c 36 "▸ $1"; echo; }

gql() {
  local q=$1
  curl -sf -X POST "$BFF/graphql" -H "$H_CT" -H "$H_T" -d "$q"
}

# ─── Wait for BFF + eligibility_view to be ready ───
for _ in $(seq 1 30); do
  if curl -sf "$BFF/livez" >/dev/null 2>&1; then break; fi
  sleep 1
done

# ─── Resolve employer + plan IDs from the seeded refs ───
step "Resolving employer + plan IDs"
EMP_SWIGGY=$(gql '{"query":"{ groupAdmin { id name } }"}' \
  | python3 -c "import sys,json; print(next(e['id'] for e in json.load(sys.stdin)['data']['groupAdmin'] if e['name']=='Swiggy'))")
EMP_ZOMATO=$(gql '{"query":"{ groupAdmin { id name } }"}' \
  | python3 -c "import sys,json; print(next(e['id'] for e in json.load(sys.stdin)['data']['groupAdmin'] if e['name']=='Zomato'))")
PLAN_GOLD=$(gql '{"query":"{ plans { id planCode } }"}' \
  | python3 -c "import sys,json; print(next(p['id'] for p in json.load(sys.stdin)['data']['plans'] if p['planCode']=='PLAN-GOLD'))")
PLAN_SILVER=$(gql '{"query":"{ plans { id planCode } }"}' \
  | python3 -c "import sys,json; print(next(p['id'] for p in json.load(sys.stdin)['data']['plans'] if p['planCode']=='PLAN-SILVER'))")
PLAN_BRONZE=$(gql '{"query":"{ plans { id planCode } }"}' \
  | python3 -c "import sys,json; print(next(p['id'] for p in json.load(sys.stdin)['data']['plans'] if p['planCode']=='PLAN-BRONZE'))")

echo "  Swiggy=$EMP_SWIGGY"
echo "  Zomato=$EMP_ZOMATO"
echo "  Plans: GOLD=$PLAN_GOLD SILVER=$PLAN_SILVER BRONZE=$PLAN_BRONZE"

# ─── Helper: add a member ───
add_member() {
  local first=$1 last=$2 dob=$3 emp=$4 plan=$5 eff=$6
  gql "$(python3 -c "import json; print(json.dumps({'query':'mutation(\$in:AddMemberInput!){addMember(input:\$in){memberId memberName}}','variables':{'in':{'firstName':'$first','lastName':'$last','dob':'$dob','employerId':'$emp','planId':'$plan','relationship':'subscriber','effectiveDate':'$eff'}}}))")" \
    | python3 -c "import sys,json; r=json.load(sys.stdin); d=r.get('data',{}).get('addMember') or {}; print(f\"  + {d.get('memberName','?'):25} ({d.get('memberId','-')[:8]})\")"
}

# ─── 1. Four PENDING members (effective in the future) ───
step "Adding 4 PENDING members (effective 2026-08-01) — future-dated enrollments"
add_member AARAV AGARWAL 1992-03-14 "$EMP_SWIGGY" "$PLAN_GOLD" 2026-08-01
add_member ISHA GUPTA 1995-07-22 "$EMP_SWIGGY" "$PLAN_SILVER" 2026-08-01
add_member KABIR JAIN 1988-11-05 "$EMP_ZOMATO" "$PLAN_BRONZE" 2026-08-01
add_member ZARA MALIK 1991-09-18 "$EMP_ZOMATO" "$PLAN_GOLD" 2026-08-01

sleep 2

# ─── 2. Terminate three existing members ───
step "Terminating 3 existing members (end coverage 2026-06-30)"

for ln in "REDDY" "DESAI" "KHAN"; do
  data=$(gql "$(python3 -c "import json; print(json.dumps({'query':'{ searchEnrollments(filter:{lastName:\"$ln\",status:\"active\"},page:{limit:1}){items{memberId memberName planId planName}} }'}))")" \
    | python3 -c "import sys,json; items=json.load(sys.stdin)['data']['searchEnrollments']['items']; print(json.dumps(items[0]) if items else '{}')")
  if [ "$data" = "{}" ]; then echo "  - no active $ln found, skipping"; continue; fi
  mid=$(echo "$data" | python3 -c "import sys,json; print(json.load(sys.stdin)['memberId'])")
  pid=$(echo "$data" | python3 -c "import sys,json; print(json.load(sys.stdin)['planId'])")
  name=$(echo "$data" | python3 -c "import sys,json; print(json.load(sys.stdin)['memberName'])")
  gql "$(python3 -c "print('{\"query\":\"mutation { terminateEnrollment(memberId: \\\"$mid\\\", planId: \\\"$pid\\\", validTo: \\\"2026-06-30\\\") }\"}')" )" >/dev/null
  echo "  ✗ $name → terminated 2026-06-30"
done

sleep 2

# ─── 3. Plan change (saga — bitemporal correction) on one active member ───
step "Plan change saga for one member (SILVER → BRONZE starting 2026-07-01)"
data=$(gql '{"query":"{ searchEnrollments(filter:{lastName:\"SHARMA\",status:\"active\"},page:{limit:1}){items{memberId memberName planId employerId}} }"}' \
  | python3 -c "import sys,json; items=json.load(sys.stdin)['data']['searchEnrollments']['items']; print(json.dumps(items[0]) if items else '{}')")

if [ "$data" != "{}" ]; then
  mid=$(echo "$data" | python3 -c "import sys,json; print(json.load(sys.stdin)['memberId'])")
  old=$(echo "$data" | python3 -c "import sys,json; print(json.load(sys.stdin)['planId'])")
  emp=$(echo "$data" | python3 -c "import sys,json; print(json.load(sys.stdin)['employerId'])")
  name=$(echo "$data" | python3 -c "import sys,json; print(json.load(sys.stdin)['memberName'])")
  gql "$(python3 -c "print('{\"query\":\"mutation { changeEnrollmentPlan(memberId: \\\"$mid\\\", oldPlanId: \\\"$old\\\", newPlanId: \\\"$PLAN_BRONZE\\\", employerId: \\\"$emp\\\", newValidFrom: \\\"2026-07-01\\\") }\"}')" )" >/dev/null
  echo "  ⟳ $name → plan change to Bronze Health from 2026-07-01"
fi

sleep 3

# ─── 4. Final summary ───
step "Final state"
gql '{"query":"{ searchEnrollments(filter:{q:null},page:{limit:100}){ total } }"}' \
  | python3 -c "import sys,json; print(f'  Total enrollments: {json.load(sys.stdin)[\"data\"][\"searchEnrollments\"][\"total\"]}')"

for s in active pending termed; do
  n=$(gql "$(python3 -c "print('{\"query\":\"{ searchEnrollments(filter:{status:\\\"$s\\\"},page:{limit:100}){total} }\"}')" )" \
    | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['searchEnrollments']['total'])")
  printf "    %-12s %s\n" "$s" "$n"
done

echo
c 32 "✅ Demo dataset ready. Open http://localhost:3000 and try:"; echo
echo "   • Filter 'Pending' chip      → 4 future-dated enrollments"
echo "   • Filter 'Terminated' chip   → 3 terminated members"
echo "   • Search 'sharma' → click row → timeline drawer"
echo "     shows plan-change bitemporal saga (2 segments)"
echo
