from __future__ import annotations

from app.domain.plan import Plan, UpsertPlanCommand, new_id


def test_new_id_unique() -> None:
    assert new_id() != new_id()


def test_plan_defaults_version_to_one() -> None:
    p = Plan(id=new_id(), plan_code="PPO-BASIC", name="Basic PPO", type="PPO")
    assert p.version == 1
    assert p.attributes == {}


def test_upsert_command_roundtrip() -> None:
    cmd = UpsertPlanCommand(
        plan_code="HMO-1",
        name="Starter HMO",
        type="HMO",
        metal_level="silver",
        attributes={"network": "wide"},
    )
    assert cmd.plan_code == "HMO-1"
    assert cmd.attributes["network"] == "wide"
    assert cmd.metal_level == "silver"
