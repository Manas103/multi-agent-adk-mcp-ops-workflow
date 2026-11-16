"""The declared skills. The first four re-declare the base benchmark's
four task types over the engine's four step kinds (lookup, judgment,
conditional, propose); building those four step kinds is the
"orchestration code" referred to in the README. ALL_LEVEL_SIGNOFF_ROUTING
is a fifth skill, added when `conditional` branching did not exist yet,
so it is what the engine's conditional-branch support was actually built
for. BADGE_VS_ASSET_ROUTING is the sixth skill, added in a later commit
than the first five: it reuses lookup, judgment, conditional and propose
exactly as already built and adds no new step kind, which is the "0 new
orchestration code" claim. See the README, "Declarative Skill Registry
Extension", for the actual `git diff --stat` between the two commits.
"""
from __future__ import annotations

from .models import SkillDecl

REVOKE_ACCESS = SkillDecl(
    name="revoke_access",
    description="Revoke an offboarding employee's directory access.",
    scoped_tools=frozenset({"lookup_employee", "propose_revoke_access"}),
    steps=(
        {"kind": "lookup", "server": "legacy", "tool": "lookup_employee",
         "args": {"employee_id": "task.employee_id"}, "store_as": "employee"},
        {"kind": "propose", "tool": "propose_revoke_access", "args_builder": "revoke_access"},
    ),
)

RECOVER_ASSET = SkillDecl(
    name="recover_asset",
    description="Open an ASSET_RETURN ticket for an employee's outstanding asset.",
    scoped_tools=frozenset({"list_assets_for_employee", "propose_return_ticket"}),
    steps=(
        {"kind": "lookup", "server": "legacy", "tool": "list_assets_for_employee",
         "args": {"employee_id": "task.employee_id"}, "store_as": "assets"},
        {"kind": "propose", "tool": "propose_return_ticket", "args_builder": "return_ticket"},
    ),
)

POLICY_GATED_TICKET = SkillDecl(
    name="policy_gated_ticket",
    description="Open a POLICY_COMPLIANCE ticket citing the policy document that governs it.",
    scoped_tools=frozenset({"search_policies", "get_policy", "propose_policy_ticket"}),
    steps=(
        {"kind": "lookup", "server": "policy", "tool": "search_policies",
         "args": {"query": "task.policy_query"}, "store_as": "search"},
        {"kind": "judgment", "decision": "pick_policy_doc", "store_as": "doc_choice"},
        {"kind": "lookup", "server": "policy", "tool": "get_policy",
         "args": {"doc_id": "ctx.doc_choice"}, "store_as": "policy_detail",
         "skip_if_none": "ctx.doc_choice"},
        {"kind": "propose", "tool": "propose_policy_ticket", "args_builder": "policy_ticket"},
    ),
)

STATUS_UPDATE = SkillDecl(
    name="status_update",
    description="Close the employee's open ticket once its asset has been handled.",
    scoped_tools=frozenset({"list_tickets_for_employee", "update_ticket_status"}),
    steps=(
        {"kind": "lookup", "server": "legacy", "tool": "list_tickets_for_employee",
         "args": {"employee_id": "task.employee_id"}, "store_as": "tickets"},
        {"kind": "judgment", "decision": "pick_ticket_to_close", "store_as": "ticket_choice"},
        {"kind": "propose", "tool": "update_ticket_status", "args_builder": "ticket_status"},
    ),
)

# Fifth skill: the engine's conditional-branch support was built for this
# one. ALL-level access needs the POL-002 sign-off ticket first; anything
# else can be revoked directly.
ALL_LEVEL_SIGNOFF_ROUTING = SkillDecl(
    name="all_level_signoff_routing",
    description="Route an access revocation through the ALL-level sign-off ticket when needed.",
    scoped_tools=frozenset({
        "lookup_employee", "search_policies", "propose_policy_ticket", "propose_revoke_access",
    }),
    steps=(
        {"kind": "lookup", "server": "legacy", "tool": "lookup_employee",
         "args": {"employee_id": "task.employee_id"}, "store_as": "employee"},
        {"kind": "judgment", "decision": "decide_signoff_needed", "store_as": "signoff_choice"},
        {"kind": "conditional", "on": "signoff_choice", "branches": {
            "all_level": (
                {"kind": "lookup", "server": "policy", "tool": "search_policies",
                 "args": {"query": "lit:ALL-level access revocation sign-off required"},
                 "store_as": "search"},
                {"kind": "judgment", "decision": "pick_policy_doc", "store_as": "doc_choice"},
                {"kind": "propose", "tool": "propose_policy_ticket", "args_builder": "policy_ticket"},
            ),
            "standard_or_admin": (
                {"kind": "propose", "tool": "propose_revoke_access", "args_builder": "revoke_access"},
            ),
        }},
    ),
)

# Sixth skill: added by declaration only. Every step kind it uses
# (lookup, judgment, conditional, propose) already exists for the five
# skills above; nothing in engine.py, models.py or proposal_builders.py
# changed to add this one (judge.py gained one new decision function,
# decide_badge_or_asset, the domain-specific judgment criterion itself,
# which is not orchestration code; see README).
BADGE_VS_ASSET_ROUTING = SkillDecl(
    name="badge_vs_asset_routing",
    description="Route an outstanding item to an ASSET_RETURN ticket, or correctly decline "
    "to file one when the item is a badge (handled by security operations, POL-004).",
    scoped_tools=frozenset({"list_assets_for_employee", "propose_return_ticket"}),
    steps=(
        {"kind": "lookup", "server": "legacy", "tool": "list_assets_for_employee",
         "args": {"employee_id": "task.employee_id"}, "store_as": "assets"},
        {"kind": "judgment", "decision": "decide_badge_or_asset", "store_as": "badge_choice"},
        {"kind": "conditional", "on": "badge_choice", "branches": {
            "real_asset_ticket": (
                {"kind": "propose", "tool": "propose_return_ticket", "args_builder": "return_ticket"},
            ),
            "badge_no_ticket": (),
        }},
    ),
)

SKILLS_BY_NAME: dict[str, SkillDecl] = {
    s.name: s for s in (
        REVOKE_ACCESS, RECOVER_ASSET, POLICY_GATED_TICKET, STATUS_UPDATE,
        ALL_LEVEL_SIGNOFF_ROUTING, BADGE_VS_ASSET_ROUTING,
    )
}

# The five skills that existed before BADGE_VS_ASSET_ROUTING was added,
# for the "0 new orchestration code" diff check in
# tests/test_sixth_skill_adds_no_engine_code.py.
SKILLS_BEFORE_SIXTH = (
    "revoke_access", "recover_asset", "policy_gated_ticket", "status_update",
    "all_level_signoff_routing",
)

REAL_MCP_SERVERS = ("src.mcp_servers.legacy_directory_server", "src.mcp_servers.policy_doc_server")
