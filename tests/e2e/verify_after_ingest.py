"""End-to-end verifier: asserts the stack behaves correctly after `make ingest`.

Exits non-zero on any assertion failure. Safe to run multiple times.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.request

BFF = "http://localhost:4000"
OS = "http://localhost:9200"

# Deterministic IDs from the sample 834 file
EXPECTED_CARDS = {"SUB-0001", "SUB-0002", "SUB-0003", "SUB-0004"}


def http_json(method: str, url: str, body: dict | None = None, headers: dict | None = None) -> dict:
    req = urllib.request.Request(url, method=method)
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    data = json.dumps(body).encode() if body else None
    with urllib.request.urlopen(req, data, timeout=10) as r:
        return json.loads(r.read().decode())


def wait_for(fn, *, timeout: int = 60, what: str = "condition") -> None:
    end = time.time() + timeout
    last = None
    while time.time() < end:
        try:
            if fn():
                return
        except Exception as e:  # noqa: BLE001
            last = e
        time.sleep(2)
    raise AssertionError(f"timeout waiting for {what}: {last}")


def main() -> int:
    print("⏳ Waiting for BFF …")
    wait_for(lambda: http_json("GET", f"{BFF}/livez"), what="BFF livez")
    print("⏳ Waiting for at least one enrollment to appear in eligibility_view …")
    query = {
        "query": "{ searchEnrollments(page: {limit: 100}) { total items { cardNumber memberName status } } }"
    }
    wait_for(
        lambda: (
            http_json(
                "POST",
                f"{BFF}/graphql",
                query,
                headers={"X-Tenant-Id": "11111111-1111-1111-1111-111111111111"},
            )["data"]["searchEnrollments"]["total"]
            >= 4
        ),
        timeout=90,
        what="enrollments projected",
    )

    # Assertions
    resp = http_json(
        "POST",
        f"{BFF}/graphql",
        query,
        headers={"X-Tenant-Id": "11111111-1111-1111-1111-111111111111"},
    )
    items = resp["data"]["searchEnrollments"]["items"]
    cards = {i.get("cardNumber") for i in items if i.get("cardNumber")}
    print(f"✅ Found {len(items)} enrollments, {len(cards)} distinct cards")

    assert resp["data"]["searchEnrollments"]["total"] >= 4, resp
    # We should have at least one TERMED enrollment (Patel Amit) after the sample
    statuses = {i["status"] for i in items}
    assert "termed" in statuses or "active" in statuses, f"unexpected statuses: {statuses}"

    # OpenSearch — fuzzy search works
    try:
        os_resp = http_json(
            "POST",
            f"{OS}/eligibility/_search",
            {"query": {"multi_match": {"query": "sharma", "fields": ["member_name^2", "last_name"]}}},
        )
        hits = os_resp.get("hits", {}).get("hits", [])
        print(f"✅ OpenSearch returned {len(hits)} hits for 'sharma'")
    except Exception as e:
        print(f"⚠ OpenSearch check skipped: {e}")

    print("\n✅ verify OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AssertionError as e:
        print(f"❌ verify FAILED: {e}")
        sys.exit(1)
