"""Connection and port configuration, read from environment variables so the
benchmark never collides with another project's Postgres schema on the same
shared instance."""

import os

PG_HOST = os.environ.get("OFFBOARD_PG_HOST", "127.0.0.1")
PG_PORT = int(os.environ.get("OFFBOARD_PG_PORT", "5432"))
PG_DB = os.environ.get("OFFBOARD_PG_DB", "offboard_ops_bench")
PG_USER = os.environ.get("OFFBOARD_PG_USER", "offboard_app")
PG_PASSWORD = os.environ.get("OFFBOARD_PG_PASSWORD", "offboard_app")

# Step budget: the minimum number of tool calls a correctly-scoped agent
# needs to complete each task type. No slack is given for a wrong first
# guess; see docs/benchmark_output.txt and the README's Findings section for
# why that is the whole point of the comparison.
STEP_BUDGET_BY_TASK_TYPE = {
    "revoke_access": 2,       # lookup_employee, propose_revoke_access
    "recover_asset": 2,       # list_assets_for_employee, propose_return_ticket
    "policy_gated_ticket": 3, # search_policies, get_policy, propose_policy_ticket
    "status_update": 2,       # lookup employee's ticket (list via employee), update_ticket_status
}

MAX_SELF_REFLECTION_ATTEMPTS = 3

APPROVAL_API_PORT = int(os.environ.get("OFFBOARD_APPROVAL_PORT", "0"))
