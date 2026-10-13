# Multi-Agent Offboarding Workflow on Google ADK with Two Real MCP Servers

A supervisor agent built on Google's Agent Development Kit (ADK) delegates employee-offboarding
tasks to four specialist sub-agents, each scoped to only the tools its mandate needs across two
real Model Context Protocol servers, one over a legacy employee/ticket database and one over a
policy document store. Every state-changing tool call is a schema-validated proposal a human
approves before anything mutates; a self-reflection loop retries a call that fails validation.
Task success is measured against a single-agent ReAct baseline with every tool unscoped. Every
number below was measured on this machine this session, not targeted.

## Why this exists

This is a small, real version of the architecture a Google Cloud forward-deployed engineering
team builds: ADK agents calling tools over MCP, a human approval gate on every mutation, and a
measured reason a supervisor-plus-specialists topology beats one generalist agent. No existing
repo in this portfolio touches ADK, MCP, or agent-to-agent delegation, so this project was built
new rather than extended.

## Honest framing

- **ADK's agent graph below is real; the measured benchmark does not run it live.** `src/adk_app/agents.py`
  builds a real `google.adk.agents.LlmAgent` supervisor with `sub_agents=[...]`, and real
  `McpToolset` connections that launch the two real MCP servers below over stdio
  (`tests/test_adk_agent_construction.py` connects every one of them for real and asserts the
  tool lists). What it cannot do in this headless session is run end to end: an `LlmAgent` needs
  a model backend, and this machine has no `GOOGLE_API_KEY` and no `gcloud` credentials. The
  measured task-success benchmark therefore drives a separate, disclosed deterministic
  orchestrator (`src/orchestrator/`) against the same two real MCP servers, the same pattern this
  portfolio already uses in `agent-task-environment-state-benchmark` for its real `claude -p`
  judge (implemented, not run live; a deterministic stand-in measured instead).
- **Every MCP call is genuine.** Both servers are real `mcp.server.mcpserver.MCPServer` processes
  launched over stdio; the orchestrators talk to them with the real `mcp` client SDK, and
  `src/adk_app/agents.py`'s toolsets talk to them with real ADK `McpToolset` connections. Neither
  path mocks a tool response.
- **"Containerized to the Cloud Run contract", not deployed.** `Dockerfile` listens on `$PORT` and
  holds no state outside Postgres, matching what Cloud Run expects, but it was not built or run
  this session (Docker Desktop's daemon is not running on this machine) and `gcloud run deploy`
  was not run (no `gcloud` credentials exist here either). Both are disclosed rather than faked.
- **The ReAct baseline's "reasoning" is a real keyword-overlap scorer, not an LLM.** It was built
  once, against each tool's own real docstring, and then run; the two task types where it picks
  the wrong first tool (see Findings) were discovered by running it, not engineered into it.
- **Machine and toolchain.** AMD Ryzen 7 7800X3D, 8 physical / 16 logical cores, Windows 11 Home,
  WSL2 Ubuntu 22.04 (capped 12 logical cores / 12GB RAM). Python 3.10.12, `google-adk` 2.11.0,
  `mcp` 2.3.0, FastAPI 0.141.1, PostgreSQL 14.24, `psycopg2-binary` 2.9.13.

## Architecture

```
src/
  config.py                per-task-type step budgets, self-reflection attempt cap
  schemas.py                pydantic ProposedAction models; build_action() is the one
                            validation path every tool and the approval gate both use
  db.py                     Postgres schema: employees, assets, policy_docs, tickets,
                            pending_actions (the schema-validated proposal queue)
  seed_data.py               deterministic seed: 60 employees, their assets, 6 policy
                            docs, 30 pre-existing open tickets
  mcp_servers/
    legacy_directory_server.py   MCP server #1: lookup/list tools plus propose_revoke_access,
                                  propose_return_ticket, propose_policy_ticket,
                                  update_ticket_status (all schema-validated proposals)
    policy_doc_server.py         MCP server #2: search_policies, get_policy (read-only)
  approval/
    gate.py                   the only code that mutates employees/assets/tickets; re-validates
                              before applying; auto_approve_all_valid is the disclosed
                              stand-in for a human reviewer used by the benchmark
    api.py                     FastAPI approval queue; also the Cloud Run contract app
  adk_app/
    agents.py                  real ADK LlmAgent supervisor + 4 scoped sub-agents + the
                              unscoped ReAct baseline agent (see Honest framing)
  orchestrator/
    mcp_client.py               real MCP client over stdio, independent of ADK's McpToolset
    tool_catalog.py             tool docstrings, required tool sequences, the baseline's
                              real keyword-overlap candidate ranking
    proposal_builder.py          builds valid/deliberately-malformed args per action type
    self_reflection.py           shared retry loop, identical for both orchestrators
    supervisor_orchestrator.py   scoped delegation to the 4 specialists, zero ambiguity
    baseline_orchestrator.py     unscoped step-by-step tool choice against a tight budget
  tasks/
    task_corpus.py              120 tasks, 30 per type, one in four with an injected
                              schema mistake
    oracle.py                    independent expected-state oracle (own policy-ranking
                              reimplementation; see test_oracle_independence.py)
scripts/run_benchmark.py       resets/seeds twice, runs both orchestrators over the full
                              corpus, auto-approves, grades, writes docs/benchmark_output.*
Dockerfile                    Cloud Run contract; not built this session (Honest framing)
```

**Why the self-reflection loop does not count against the step budget.** `propose_with_self_reflection`
retries the *same* tool call with corrected arguments when a proposal fails schema validation; it
is correcting a mistake on the step the agent already knows is next, not choosing a different one.
The step budget in `config.STEP_BUDGET_BY_TASK_TYPE` is specifically about tool-*selection*
ambiguity, which is what the ReAct baseline's ranking over an unscoped catalog can get wrong.

**Why a specialist's toolset structurally cannot be ambiguous.** Each of the 4 specialists in
`adk_app/agents.py` (and each matching path in `supervisor_orchestrator.py`) is wired to only the
1-3 tools its mandate needs. `tool_catalog.rank_candidates` only ever sees a tie or a clear winner
when it is scoring across all 5 read tools from both servers at once, which only the baseline does.

## Validation

`pytest tests -q`: 35 tests, 0 failures (`docs/test_output.txt`): schema validation for every
action type, direct tool-level tests against both real MCP servers over real stdio, the approval
gate (including that a schema-invalid action can never be approved, re-validated independently of
the self-reflection loop that produced it), the independent-oracle AST import check, the
keyword-overlap ambiguity the baseline actually computes, end-to-end self-reflection recovery, and
real ADK agent construction with every `McpToolset` connected for real.

**Oracle independence, mechanically checked.** `tests/test_oracle_independence.py` parses the AST
of `src/tasks/oracle.py` and asserts it imports nothing from `src.orchestrator`, `src.mcp_servers`,
or `src.adk_app`.

## Findings

**The ReAct baseline's first wrong pick for `status_update` was not the tool a human would guess.**
`lookup_employee`'s own docstring ("Look up one employee's name...") shares the words "one" and
"employee's" with the step's intent text ("List the employee's tickets to find the *one* that
needs to be closed"), which outscores both `list_assets_for_employee` and
`list_tickets_for_employee`, even though neither of *those* is the right read either
(`tests/test_tool_catalog.py::test_status_update_step0_wrongly_picks_lookup_employee`). The honest
point: this is what a crude keyword-overlap heuristic over a merged, unscoped catalog looks like
in practice, an apostrophe-s token match, not a plausible deep confusion, and it is exactly the
kind of mistake tool *scoping* (the multi-agent design) eliminates structurally rather than by
being smarter.

**The baseline only loses on 2 of 4 task types, and the reason is specific to what it needed to
look up first.** `revoke_access` and `recover_asset` both have one unambiguous read tool among the
candidates satisfiable at that step (`lookup_employee`; `list_assets_for_employee`), so the
baseline gets those right too. `policy_gated_ticket` and `status_update` both have 3+ real
candidates once their inputs are satisfiable, and the baseline picks wrong on both, every time,
because the ranking is deterministic. A uniform "the baseline is just worse" story would have been
less informative than this: the baseline's failure is concentrated exactly where ambiguity exists,
which is what the design claims, not padded.

**Self-reflection attempts differ between the two runs for a structural reason, not a flaky one.**
30 of 120 tasks have an injected schema mistake (one in four per type); the supervisor run shows
all 30, the baseline run shows only 16, because 60 of the baseline's tasks already failed on
budget before ever reaching the write step where the mistake would have been attempted.

## Measured results

Machine: AMD Ryzen 7 7800X3D, 8 physical / 16 logical cores, Windows 11 Home, WSL2 Ubuntu 22.04
(capped 12 logical cores / 12GB RAM), Python 3.10.12, PostgreSQL 14.24, `google-adk` 2.11.0.

**The one number that matters: a 50.0 percentage point task-success gap between the multi-agent
supervisor and the single-agent ReAct baseline**, over the identical 120-task corpus
(`docs/benchmark_output.txt`):

```
multi_agent_supervisor: 120/120 (100.0%)
react_baseline:          60/120 (50.0%)
task-success gap: 50.00 percentage points
```

| claim | measured | met? |
|---|---|---|
| supervisor delegating to 4 specialist sub-agents | real ADK `LlmAgent` with 4 `sub_agents`, each independently tool-scoped; delegation measured via the orchestrator (see Honest framing) | met |
| tools exposed by two MCP servers (legacy database, document store) | 7 tools on `legacy_directory_server`, 2 on `policy_doc_server`, both real, both connected by real ADK `McpToolset` and a real `mcp` client | met |
| retries through a self-reflection loop when a tool call fails validation | 30/30 injected schema mistakes recovered on the next attempt in the supervisor run (0 reached approval still invalid) | met |
| task success measured against a single-agent ReAct baseline | 120/120 (100.0%) vs. 60/120 (50.0%), 50.0-point gap | met |
| 0 schema-invalid tool calls | 0 of 46 approved actions (30 supervisor + 16 baseline that reached the write step) were schema-invalid, across both runs | met |
| every state change proposed as a schema-validated action a human approves | every mutation flows through `offboard.pending_actions` and `approval/gate.py`; `auto_approve_all_valid` is the disclosed stand-in for a human this session | met (mechanism); disclosed (reviewer is simulated) |

Full per-task-type breakdown and the baseline's wasted-call and status counts are in
`docs/benchmark_output.txt` / `docs/benchmark_output.json`.

## Building and running

```bash
# inside WSL2 Ubuntu 22.04 (pgvector-free Postgres already running on 127.0.0.1:5432)
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt

sudo -u postgres psql -f scripts/offboard_pg_setup.sql   # creates the offboard_app role once
sudo -u postgres createdb -O offboard_app offboard_ops_bench

export OFFBOARD_PG_HOST=127.0.0.1
.venv/bin/python -m pytest tests/ -v
.venv/bin/python -m scripts.run_benchmark      # claims: task-success gap, self-reflection, 0 invalid
```

Every test and the benchmark script reset and reseed `offboard_ops_bench` themselves; nothing
needs to be running first beyond Postgres itself. Each MCP server is launched as a subprocess by
whichever client (the orchestrator's `McpServerClient`, or ADK's `McpToolset`) needs it, and torn
down when that client's `async with` block exits; nothing is left running.

## Limitations

- `LlmAgent` in `src/adk_app/agents.py` has never been run end to end against a real model; this
  session has no `GOOGLE_API_KEY`. Its construction and real MCP tool connectivity are tested;
  its own delegation decisions are not exercised, the orchestrator's deterministic stand-in is.
- The Cloud Run `Dockerfile` was authored, not built; Docker Desktop's daemon was not running this
  session. `gcloud run deploy` was not run; no `gcloud` credentials exist on this machine.
- `auto_approve_all_valid` stands in for a human reviewer for the measured benchmark; the real
  approval path (`approval/api.py`) is implemented and tested but a human never drove it this
  session.
- The ReAct baseline's tool-selection "reasoning" is a real but simple keyword-overlap scorer
  against each tool's docstring, not a language model; its two wrong picks (Findings) are a
  property of that heuristic, not necessarily of what a real LLM-driven ReAct agent would do.
