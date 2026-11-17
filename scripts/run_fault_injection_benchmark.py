"""The one script that produces docs/fault_injection_benchmark_output.* and
the Fault Injection and Compensating Rollback Extension's Measured results
table: 24 injected transport faults (8 TIMEOUT, 8 SERVER_ERROR_5XX, 8
STALE_READ) at varying points across the compound offboarding saga's three
committed mutations, each on its own freshly seeded employee so one run's
compensation can never touch another's rows, plus a 7-employee unfaulted
control confirming the saga itself completes when nothing is injected.
Resets and reseeds the shared offboard_ops_bench database once, same as
scripts/run_benchmark.py.

Run: python -m scripts.run_fault_injection_benchmark
"""

from __future__ import annotations

import asyncio
import json

from src import db, seed_data
from src.faults.transport import FaultSpec, FaultType
from src.orchestrator.mcp_client import McpServerClient
from src.workflows import compound_offboard

STALE_READ_EMPLOYEES = range(1, 9)       # 8 employees, ordinal 3 every time
TIMEOUT_EMPLOYEES = range(9, 17)         # 8 employees
SERVER_ERROR_EMPLOYEES = range(17, 25)   # 8 employees
CONTROL_EMPLOYEES = range(25, 32)        # 7 employees, no fault injected

# ordinal 2 = propose_revoke_access itself; 4 = list_assets_for_employee;
# 5 = propose_return_ticket; 6 = propose_policy_ticket. Each list cycles
# through all four so every commit point (0, 1 or 2 prior commits) is
# exercised by both non-stale fault types.
TIMEOUT_ORDINALS = [2, 4, 5, 6, 2, 4, 5, 6]
SERVER_ERROR_ORDINALS = [4, 5, 6, 2, 4, 5, 6, 2]


def _asset_id_for(employee_id: int, seed_scenario: dict) -> int:
    # the saga's own asset, deliberately the employee's *second* seeded
    # asset (index 1), so it never collides with the first asset's
    # independently pre-seeded OPEN ticket (see src/seed_data.py).
    return seed_scenario["assets_by_employee"][employee_id - 1][1]["asset_id"]


async def _run_group(legacy, seed_scenario, employee_ids, fault_label, ordinals=None, fault_type=None):
    results = []
    for i, employee_id in enumerate(employee_ids):
        fault = None
        if fault_type is not None:
            ordinal = ordinals[i] if ordinals is not None else 3
            fault = FaultSpec(call_ordinal=ordinal, fault_type=fault_type)
        r = await compound_offboard.run_compound_offboard(
            employee_id, _asset_id_for(employee_id, seed_scenario), legacy,
            run_id="fault-injection-run", task_id=f"compound-{employee_id:03d}", fault=fault,
        )
        results.append((fault_label, r))
    return results


async def _run_all(seed_scenario: dict) -> list[tuple[str, compound_offboard.CompoundResult]]:
    results: list[tuple[str, compound_offboard.CompoundResult]] = []
    async with McpServerClient("src.mcp_servers.legacy_directory_server") as legacy:
        results += await _run_group(legacy, seed_scenario, STALE_READ_EMPLOYEES, "STALE_READ",
                                     fault_type=FaultType.STALE_READ)
        results += await _run_group(legacy, seed_scenario, TIMEOUT_EMPLOYEES, "TIMEOUT",
                                     ordinals=TIMEOUT_ORDINALS, fault_type=FaultType.TIMEOUT)
        results += await _run_group(legacy, seed_scenario, SERVER_ERROR_EMPLOYEES, "SERVER_ERROR_5XX",
                                     ordinals=SERVER_ERROR_ORDINALS, fault_type=FaultType.SERVER_ERROR_5XX)
        results += await _run_group(legacy, seed_scenario, CONTROL_EMPLOYEES, "CONTROL_NO_FAULT")
    return results


def main() -> None:
    db.init_schema()
    db.reset()
    seed_scenario = seed_data.seed()

    results = asyncio.run(_run_all(seed_scenario))

    faulted = [(label, r) for label, r in results if label != "CONTROL_NO_FAULT"]
    control = [(label, r) for label, r in results if label == "CONTROL_NO_FAULT"]

    n_faulted = len(faulted)
    n_partial = sum(1 for _, r in faulted if r.partial_write)
    n_clean = n_faulted - n_partial
    n_control_completed = sum(1 for _, r in control if r.status == "completed")

    by_fault_type: dict[str, dict] = {}
    for fault_type, r in faulted:
        d = by_fault_type.setdefault(fault_type, {"n": 0, "clean": 0, "ordinals": []})
        d["n"] += 1
        d["clean"] += int(not r.partial_write)
        d["ordinals"].append(r.fault["call_ordinal"] if r.fault else None)

    report = {
        "faulted_total": n_faulted,
        "zero_partial_writes": n_clean,
        "partial_writes_detected": n_partial,
        "by_fault_type": by_fault_type,
        "control_unfaulted_completed": f"{n_control_completed}/{len(control)}",
        "detail": [
            {
                "fault_type": label,
                "employee_id": r.employee_id,
                "status": r.status,
                "fault": r.fault,
                "completed_mutations": r.completed_mutations,
                "compensated_mutations": r.compensated_mutations,
                "partial_write": r.partial_write,
            }
            for label, r in results
        ],
    }

    lines = []
    lines.append("=== Fault injection and compensating rollback: compound offboarding saga ===\n")
    lines.append(f"faulted tasks: {n_faulted}")
    lines.append(f"0 partial writes after compensation: {n_clean}/{n_faulted}")
    lines.append(f"partial writes detected (compensation did not fully reverse the saga): {n_partial}/{n_faulted}")
    for ft, d in sorted(by_fault_type.items()):
        lines.append(f"  {ft}: {d['clean']}/{d['n']} clean, fault call_ordinal(s) {d['ordinals']}")
    lines.append(f"unfaulted control sagas completed: {n_control_completed}/{len(control)}")
    output_text = "\n".join(lines)
    print(output_text)

    with open("docs/fault_injection_benchmark_output.txt", "w") as f:
        f.write(output_text + "\n")
    with open("docs/fault_injection_benchmark_output.json", "w") as f:
        json.dump(report, f, indent=2, default=str)


if __name__ == "__main__":
    main()
