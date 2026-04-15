"""Generate a richer 834 demo file with 18 members across Swiggy + Zomato.

Mix: subscribers + dependents, both employers, both subgroups, all 3 plans.
Output: samples/834_demo.x12
"""

from __future__ import annotations

from pathlib import Path

OUT = Path(__file__).parent / "834_demo.x12"

# (rel_code, sub_indicator, last, first, ssn, dob_yyyymmdd, gender, employer_ref, group_ref, plan_code, coverage)
MEMBERS = [
    # Swiggy subscribers + dependents
    (
        "18",
        "Y",
        "SHARMA",
        "PRIYA",
        "111000001",
        "19900215",
        "F",
        "ICICI_SWIGGY_POLICY",
        "SWIGGY-A",
        "PLAN-GOLD",
        "FAM",
    ),
    (
        "01",
        "N",
        "SHARMA",
        "ROHIT",
        "111000002",
        "19880712",
        "M",
        "ICICI_SWIGGY_POLICY",
        "SWIGGY-A",
        "PLAN-GOLD",
        "FAM",
    ),
    (
        "18",
        "Y",
        "KAUR",
        "SIMRAN",
        "111000003",
        "19920804",
        "F",
        "ICICI_SWIGGY_POLICY",
        "SWIGGY-A",
        "PLAN-GOLD",
        "IND",
    ),
    (
        "18",
        "Y",
        "REDDY",
        "VIKRAM",
        "111000004",
        "19870518",
        "M",
        "ICICI_SWIGGY_POLICY",
        "SWIGGY-B",
        "PLAN-SILVER",
        "IND",
    ),
    (
        "01",
        "N",
        "REDDY",
        "ANANYA",
        "111000005",
        "19890322",
        "F",
        "ICICI_SWIGGY_POLICY",
        "SWIGGY-B",
        "PLAN-SILVER",
        "FAM",
    ),
    (
        "19",
        "N",
        "REDDY",
        "AARAV",
        "111000006",
        "20150610",
        "M",
        "ICICI_SWIGGY_POLICY",
        "SWIGGY-B",
        "PLAN-SILVER",
        "FAM",
    ),
    (
        "18",
        "Y",
        "DESAI",
        "MEERA",
        "111000007",
        "19951225",
        "F",
        "ICICI_SWIGGY_POLICY",
        "SWIGGY-A",
        "PLAN-BRONZE",
        "IND",
    ),
    (
        "18",
        "Y",
        "JOSHI",
        "RAVI",
        "111000008",
        "19830409",
        "M",
        "ICICI_SWIGGY_POLICY",
        "SWIGGY-B",
        "PLAN-GOLD",
        "IND",
    ),
    (
        "18",
        "Y",
        "MENON",
        "DEEPA",
        "111000009",
        "19911128",
        "F",
        "ICICI_SWIGGY_POLICY",
        "SWIGGY-A",
        "PLAN-SILVER",
        "IND",
    ),
    # Zomato subscribers + dependents
    (
        "18",
        "Y",
        "PATEL",
        "AMIT",
        "222000001",
        "19851120",
        "M",
        "ICICI_ZOMATO_POLICY",
        "ZOMATO-A",
        "PLAN-SILVER",
        "IND",
    ),
    (
        "18",
        "Y",
        "NAIR",
        "ARJUN",
        "222000002",
        "19810308",
        "M",
        "ICICI_ZOMATO_POLICY",
        "ZOMATO-A",
        "PLAN-SILVER",
        "IND",
    ),
    (
        "18",
        "Y",
        "IYER",
        "KAVYA",
        "222000003",
        "19930812",
        "F",
        "ICICI_ZOMATO_POLICY",
        "ZOMATO-B",
        "PLAN-GOLD",
        "FAM",
    ),
    (
        "01",
        "N",
        "IYER",
        "RAHUL",
        "222000004",
        "19920215",
        "M",
        "ICICI_ZOMATO_POLICY",
        "ZOMATO-B",
        "PLAN-GOLD",
        "FAM",
    ),
    (
        "18",
        "Y",
        "GUPTA",
        "ROHAN",
        "222000005",
        "19900715",
        "M",
        "ICICI_ZOMATO_POLICY",
        "ZOMATO-A",
        "PLAN-BRONZE",
        "IND",
    ),
    (
        "18",
        "Y",
        "SINGH",
        "POOJA",
        "222000006",
        "19840903",
        "F",
        "ICICI_ZOMATO_POLICY",
        "ZOMATO-B",
        "PLAN-GOLD",
        "IND",
    ),
    (
        "18",
        "Y",
        "KHAN",
        "FARHAN",
        "222000007",
        "19961014",
        "M",
        "ICICI_ZOMATO_POLICY",
        "ZOMATO-A",
        "PLAN-SILVER",
        "IND",
    ),
    (
        "18",
        "Y",
        "RAO",
        "LATHA",
        "222000008",
        "19790527",
        "F",
        "ICICI_ZOMATO_POLICY",
        "ZOMATO-A",
        "PLAN-BRONZE",
        "IND",
    ),
    (
        "18",
        "Y",
        "VERMA",
        "NIKHIL",
        "222000009",
        "19981201",
        "M",
        "ICICI_ZOMATO_POLICY",
        "ZOMATO-B",
        "PLAN-SILVER",
        "IND",
    ),
]

EFFECTIVE = "20260101"


def build() -> str:
    parts: list[str] = []
    parts.append(
        "ISA*00*          *00*          *ZZ*SENDER         *ZZ*RECEIVER       *260414*0930*U*00501*000000200*0*P*:~"
    )
    parts.append("GS*BE*SENDER*RECEIVER*20260414*0930*200*X*005010X220A1~")
    parts.append("ST*834*0001*005010X220A1~")
    parts.append("BGN*00*TXNDEMO*20260414*0930****2~")
    parts.append("REF*38*ICICI_DEMO_POLICY~")
    parts.append(f"DTP*303*D8*{EFFECTIVE}~")

    for rel, sub_ind, last, first, ssn, dob, gender, emp_ref, grp_ref, plan, cov in MEMBERS:
        parts.append(f"INS*{sub_ind}*{rel}*021*20*A***FT~")
        parts.append(f"REF*38*{emp_ref}~")
        parts.append(f"REF*0F*{ssn}~")
        parts.append(f"REF*1L*{grp_ref}~")
        parts.append(f"NM1*IL*1*{last}*{first}****34*{ssn}~")
        parts.append(f"DMG*D8*{dob}*{gender}~")
        parts.append(f"HD*021**HLT*{plan}*{cov}~")
        parts.append(f"DTP*348*D8*{EFFECTIVE}~")

    parts.append("SE*0*0001~")
    parts.append("GE*1*200~")
    parts.append("IEA*1*000000200~")
    return "".join(parts)


if __name__ == "__main__":
    OUT.write_text(build())
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes, {len(MEMBERS)} INS loops)")
