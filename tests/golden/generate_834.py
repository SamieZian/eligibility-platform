"""Generate deterministic golden ANSI X12 834 files under tests/golden/.

Files produced:
    * 834_sample.x12   — small illustrative file (ADD + CANCEL + CORRECTION)
    * 834_replace.x12  — full-file-replace (BGN08=22), 2 subscribers
    * 834_large.x12    — 1000 ADD synthetic members for load tests

Run this script directly to (re)generate the goldens:

    python3 tests/golden/generate_834.py

Determinism: every value is either hard-coded or seeded from ``random.Random(42)``.
"""

from __future__ import annotations

import random
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent


# ---------------------------------------------------------------------------
# Envelope helpers — all use the canonical 834 delimiters
#   element = '*'    component = ':'    segment = '~'
# ---------------------------------------------------------------------------

ISA_CTRL = "000000001"
GS_CTRL = "1"
ST_CTRL = "0001"


def _isa(ctrl: str = ISA_CTRL) -> str:
    # Carefully 106 characters long through the terminating '~'.
    return (
        "ISA*00*          *00*          *ZZ*SENDER         "
        "*ZZ*RECEIVER       *260414*0930*U*00501*"
        f"{ctrl}*0*P*:~"
    )


def _gs(ctrl: str = GS_CTRL) -> str:
    return f"GS*BE*SENDER*RECEIVER*20260414*0930*{ctrl}*X*005010X220A1~"


def _ge(count: int, ctrl: str = GS_CTRL) -> str:
    return f"GE*{count}*{ctrl}~"


def _iea(count: int, ctrl: str = ISA_CTRL) -> str:
    return f"IEA*{count}*{ctrl}~"


def _st(ctrl: str = ST_CTRL) -> str:
    return f"ST*834*{ctrl}*005010X220A1~"


def _se(segment_count: int, ctrl: str = ST_CTRL) -> str:
    return f"SE*{segment_count}*{ctrl}~"


def _bgn(txn_id: str, action: str = "2") -> str:
    """BGN08 action: 2=Original, 4=Change, 22=Replace."""
    return f"BGN*00*{txn_id}*20260414*0930****{action}~"


# ---------------------------------------------------------------------------
# Member loop (2000) helpers
# ---------------------------------------------------------------------------

def _member(
    *,
    maint: str,
    subscriber_ind: str,
    relationship: str,
    benefit_status: str,
    last: str,
    first: str,
    ssn: str,
    dob: str,
    gender: str,
    plan: str | None,
    level: str | None,
    effective: str | None,
    termination: str | None,
    sponsor_ref: str = "ICICI_SWIGGY_POLICY",
    group_ref: str = "GRP-001",
) -> list[str]:
    segs: list[str] = []
    segs.append(f"INS*{subscriber_ind}*{relationship}*{maint}*20*{benefit_status}***FT~")
    segs.append(f"REF*38*{sponsor_ref}~")
    segs.append(f"REF*0F*{ssn}~")
    segs.append(f"REF*1L*{group_ref}~")
    segs.append(f"NM1*IL*1*{last}*{first}****34*{ssn}~")
    segs.append(f"DMG*D8*{dob}*{gender}~")
    if plan is not None:
        segs.append(f"HD*{maint}**HLT*{plan}*{level or 'IND'}~")
    if effective:
        segs.append(f"DTP*348*D8*{effective}~")
    if termination:
        segs.append(f"DTP*349*D8*{termination}~")
    return segs


def _assemble(bgn_action: str, member_blocks: list[list[str]], txn_id: str = "TXN0001") -> str:
    header_segs = [
        _st(),
        _bgn(txn_id, bgn_action),
        "REF*38*ICICI_SWIGGY_POLICY~",
        "DTP*303*D8*20260101~",
    ]
    inner: list[str] = []
    for block in member_blocks:
        inner.extend(block)
    se_count = len(header_segs) + len(inner) + 1  # +1 for SE itself
    body = "".join(header_segs) + "".join(inner) + _se(se_count)
    return _isa() + _gs() + body + _ge(1) + _iea(1)


# ---------------------------------------------------------------------------
# 1) Sample demo file
# ---------------------------------------------------------------------------

def _build_sample() -> str:
    blocks: list[list[str]] = []

    # a) Subscriber SHARMA PRIYA — ADD, Swiggy Gold Family
    blocks.append(_member(
        maint="021", subscriber_ind="Y", relationship="18", benefit_status="A",
        last="SHARMA", first="PRIYA", ssn="123456789", dob="19900215", gender="F",
        plan="PLAN-GOLD", level="FAM", effective="20260101", termination=None,
        sponsor_ref="ICICI_SWIGGY_POLICY", group_ref="SWIGGY-A",
    ))
    # b) Spouse dep of Priya — ADD
    blocks.append(_member(
        maint="021", subscriber_ind="N", relationship="01", benefit_status="A",
        last="SHARMA", first="ROHIT", ssn="123456790", dob="19880712", gender="M",
        plan="PLAN-GOLD", level="FAM", effective="20260101", termination=None,
        sponsor_ref="ICICI_SWIGGY_POLICY", group_ref="SWIGGY-A",
    ))
    # c) Subscriber PATEL AMIT — ADD, Zomato Silver Individual
    blocks.append(_member(
        maint="021", subscriber_ind="Y", relationship="18", benefit_status="A",
        last="PATEL", first="AMIT", ssn="234567891", dob="19851120", gender="M",
        plan="PLAN-SILVER", level="IND", effective="20260101", termination=None,
        sponsor_ref="ICICI_ZOMATO_POLICY", group_ref="ZOMATO-A",
    ))
    # d) Subscriber KAUR SIMRAN — ADD, Swiggy Gold Individual
    blocks.append(_member(
        maint="021", subscriber_ind="Y", relationship="18", benefit_status="A",
        last="KAUR", first="SIMRAN", ssn="345678912", dob="19920804", gender="F",
        plan="PLAN-GOLD", level="IND", effective="20260101", termination=None,
        sponsor_ref="ICICI_SWIGGY_POLICY", group_ref="SWIGGY-A",
    ))
    # e) Subscriber NAIR ARJUN — ADD, Zomato Silver Individual
    blocks.append(_member(
        maint="021", subscriber_ind="Y", relationship="18", benefit_status="A",
        last="NAIR", first="ARJUN", ssn="456789123", dob="19810308", gender="M",
        plan="PLAN-SILVER", level="IND", effective="20260101", termination=None,
        sponsor_ref="ICICI_ZOMATO_POLICY", group_ref="ZOMATO-A",
    ))
    # TERMINATE (024) of Patel Amit
    blocks.append(_member(
        maint="024", subscriber_ind="Y", relationship="18", benefit_status="I",
        last="PATEL", first="AMIT", ssn="234567891", dob="19851120", gender="M",
        plan="PLAN-SILVER", level="IND", effective=None, termination="20260331",
        sponsor_ref="ICICI_ZOMATO_POLICY", group_ref="ZOMATO-A",
    ))
    # CORRECTION (030) of Kaur Simran — new effective 20260115
    blocks.append(_member(
        maint="030", subscriber_ind="Y", relationship="18", benefit_status="A",
        last="KAUR", first="SIMRAN", ssn="345678912", dob="19920804", gender="F",
        plan="PLAN-GOLD", level="IND", effective="20260115", termination=None,
        sponsor_ref="ICICI_SWIGGY_POLICY", group_ref="SWIGGY-A",
    ))

    return _assemble(bgn_action="2", member_blocks=blocks, txn_id="TXN0001")


# ---------------------------------------------------------------------------
# 2) Replace file (BGN08 = 22)
# ---------------------------------------------------------------------------

def _build_replace() -> str:
    blocks = [
        _member(
            maint="021", subscriber_ind="Y", relationship="18", benefit_status="A",
            last="SHARMA", first="PRIYA", ssn="123456789", dob="19900215", gender="F",
            plan="PLAN-GOLD", level="FAM", effective="20260101", termination=None,
            sponsor_ref="ICICI_SWIGGY_POLICY", group_ref="SWIGGY-A",
        ),
        _member(
            maint="021", subscriber_ind="Y", relationship="18", benefit_status="A",
            last="KAUR", first="SIMRAN", ssn="345678912", dob="19920804", gender="F",
            plan="PLAN-GOLD", level="IND", effective="20260115", termination=None,
            sponsor_ref="ICICI_SWIGGY_POLICY", group_ref="SWIGGY-A",
        ),
    ]
    return _assemble(bgn_action="22", member_blocks=blocks, txn_id="TXN0002")


# ---------------------------------------------------------------------------
# 3) Large synthetic file (1000 ADD members)
# ---------------------------------------------------------------------------

_LAST_NAMES = [
    "SHARMA", "PATEL", "KAUR", "NAIR", "REDDY", "IYER", "KHAN",
    "SINGH", "GUPTA", "MENON", "RAO", "VERMA", "BANERJEE", "DAS",
]
_FIRST_NAMES_F = [
    "PRIYA", "SIMRAN", "ANJALI", "DIVYA", "MEERA", "KAVYA", "RIYA",
    "POOJA", "SWATI", "NEHA",
]
_FIRST_NAMES_M = [
    "AMIT", "ARJUN", "ROHIT", "VIKRAM", "RAHUL", "KARAN", "ADITYA",
    "SANJAY", "NIKHIL", "SURESH",
]


def _build_large(n: int = 1000) -> str:
    rng = random.Random(42)
    blocks: list[list[str]] = []
    for i in range(n):
        gender = rng.choice(["M", "F"])
        first = rng.choice(_FIRST_NAMES_M if gender == "M" else _FIRST_NAMES_F)
        last = rng.choice(_LAST_NAMES)
        # Deterministic 9-digit synthetic ID.
        ssn = f"{(900000000 + i):09d}"
        year = 1960 + (i % 45)
        month = 1 + (i % 12)
        day = 1 + (i % 28)
        dob = f"{year:04d}{month:02d}{day:02d}"
        if i % 2 == 0:
            sponsor = "ICICI_SWIGGY_POLICY"
            group = "SWIGGY-A"
            plan = "PLAN-GOLD"
        else:
            sponsor = "ICICI_ZOMATO_POLICY"
            group = "ZOMATO-A"
            plan = "PLAN-SILVER"
        blocks.append(_member(
            maint="021", subscriber_ind="Y", relationship="18", benefit_status="A",
            last=last, first=first, ssn=ssn, dob=dob, gender=gender,
            plan=plan, level="IND", effective="20260101", termination=None,
            sponsor_ref=sponsor, group_ref=group,
        ))
    return _assemble(bgn_action="2", member_blocks=blocks, txn_id="TXN0003")


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    outputs = {
        "834_sample.x12": _build_sample(),
        "834_replace.x12": _build_replace(),
        "834_large.x12": _build_large(1000),
    }
    for name, content in outputs.items():
        path = OUT_DIR / name
        path.write_text(content, encoding="latin-1")
        print(f"wrote {path} ({len(content):,} bytes)")


if __name__ == "__main__":
    main()
