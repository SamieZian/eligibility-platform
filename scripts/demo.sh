#!/usr/bin/env bash
# Reviewer demo — shows the whole platform end-to-end in ~3 minutes.
#
#   - boots the stack
#   - seeds payers / employers / plans
#   - ingests an 18-member 834
#   - ingests an 8-member CSV (proves alternative format)
#   - adds a member via the BFF GraphQL mutation
#   - exercises Groups admin (creates a payer)
#   - prints search results
#   - shows you the URLs to open
#
# Stop with Ctrl+C at any point — `make down` to clean up.
set -euo pipefail
cd "$(dirname "$0")/.."

BFF=http://localhost:4000
TENANT=11111111-1111-1111-1111-111111111111
H="X-Tenant-Id: $TENANT"

c_blue=$'\e[34m'; c_green=$'\e[32m'; c_yellow=$'\e[33m'; c_dim=$'\e[2m'; c_reset=$'\e[0m'
say() { printf "${c_blue}▶ %s${c_reset}\n" "$*"; }
ok()  { printf "${c_green}✓ %s${c_reset}\n" "$*"; }
warn(){ printf "${c_yellow}⚠ %s${c_reset}\n" "$*"; }
hr()  { printf "${c_dim}%.0s─${c_reset}" {1..72}; printf "\n"; }

gql() {
  curl -sS -X POST "$BFF/graphql" -H 'Content-Type: application/json' -H "$H" -d "$1"
}

hr
say "Step 1/8 — bring up the stack (this takes ~30s if images already built)"
make up >/dev/null 2>&1 || warn "make up returned non-zero (already up?)"
ok "stack up"

hr
say "Step 2/8 — wait 12 s for projector + workers to settle"
sleep 12

hr
say "Step 3/8 — seed payers / employers / plans"
docker compose exec -T bff python -m app.cli seed 2>&1 | tail -1
ok "seed complete"

hr
say "Step 4/8 — ingest 18-member 834 file (samples/834_demo.x12)"
RESP=$(curl -sS -X POST "$BFF/files/eligibility" -H "$H" -F 'file=@samples/834_demo.x12')
echo "  $RESP"
sleep 10
ok "834 ingestion processed"

hr
say "Step 5/8 — ingest 8-member CSV (samples/members_demo.csv)"
RESP=$(curl -sS -X POST "$BFF/files/eligibility" -H "$H" -F 'file=@samples/members_demo.csv')
echo "  $RESP"
sleep 8
ok "CSV ingestion processed (proves the platform handles both formats)"

hr
say "Step 6/8 — Add Member via GraphQL (orchestrates member + atlas in one call)"
EMP=$(gql '{"query":"{ employers(search:\"Swiggy\"){ id } }"}' | python3 -c 'import json,sys;print(json.load(sys.stdin)["data"]["employers"][0]["id"])')
PLAN=$(gql '{"query":"{ plans { id planCode } }"}' | python3 -c 'import json,sys;d=json.load(sys.stdin);print([p["id"] for p in d["data"]["plans"] if p["planCode"]=="PLAN-GOLD"][0])')
ADD=$(gql "{\"query\":\"mutation { addMember(input: {firstName: \\\"DEMO\\\", lastName: \\\"REVIEWER\\\", dob: \\\"1990-01-01\\\", employerId: \\\"$EMP\\\", planId: \\\"$PLAN\\\", subgroupName: \\\"SWIGGY-A\\\", effectiveDate: \\\"2026-01-01\\\"}) { memberId memberName } }\"}")
echo "  $ADD"
sleep 5
ok "member added"

hr
say "Step 7/8 — Groups admin: create a new payer (CRUD demo)"
PAYER=$(gql '{"query":"mutation { createPayer(name: \"BCBS Demo\") { id name } }"}')
echo "  $PAYER"
ok "payer created"

hr
say "Step 8/8 — Search the eligibility view"
echo "  Quick search 'reviewer':"
gql '{"query":"{ searchEnrollments(filter:{q:\"reviewer\"},page:{limit:5}){ total items{memberName employerName subgroupName planName} } }"}' | python3 -m json.tool 2>/dev/null | sed 's/^/    /'

echo ""
echo "  All-data summary:"
gql '{"query":"{ searchEnrollments(page:{limit:1}){ total } payers{name} plans{planCode} groupAdmin{name subgroups{name}} }"}' | python3 -c '
import json,sys
d = json.load(sys.stdin)["data"]
total = d["searchEnrollments"]["total"]
payers = [p["name"] for p in d["payers"]]
plans = [p["planCode"] for p in d["plans"]]
print("    total enrollments  : %d" % total)
print("    payers             : %s" % payers)
print("    plans              : %s" % plans)
for g in d["groupAdmin"]:
    sg = [s["name"] for s in g["subgroups"]]
    print("    employer %-10s: subgroups=%s" % (g["name"], sg))
'

hr
ok "demo complete"
echo ""
echo "  Open these in your browser:"
echo "    http://localhost:3000              ← React Eligibility Console"
echo "    http://localhost:3000/#/groups     ← Groups admin"
echo "    http://localhost:3000/#/upload     ← File upload page"
echo "    http://localhost:3000/#/about      ← About + repo links"
echo ""
echo "    http://localhost:4000/graphql      ← BFF GraphQL playground"
echo "    http://localhost:16686             ← Jaeger traces"
echo "    http://localhost:9001              ← MinIO (minio/minio12345)"
echo "    http://localhost:9200              ← OpenSearch"
echo ""
echo "  Try in the UI:"
echo "    1. Eligibility tab → click any row → see bitemporal timeline"
echo "    2. Type 'sharma' in the quick search"
echo "    3. Click + Add New Member, leave card blank, submit → it auto-generates"
echo "    4. Groups tab → toggle plan visibility, add a subgroup"
echo "    5. Upload tab → drag samples/834_replace.x12 to test full-file replace"
echo ""
echo "  Stop with: make down   (or 'make clean' to also wipe volumes)"
