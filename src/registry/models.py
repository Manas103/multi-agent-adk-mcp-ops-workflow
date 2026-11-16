"""The typed skill declaration: name, scoped tools, and an ordered list of
steps. A step is a small declarative dict, one of four shapes (see
engine.py for what each means and enforces):

  {"kind": "lookup", "server": "legacy"|"policy", "tool": <name>,
   "args": {<tool kwarg>: <path>}, "store_as": <context key>}
  {"kind": "judgment", "decision": <name registered in judge.DECISIONS>,
   "store_as": <context key>}
  {"kind": "conditional", "on": <context key holding a judgment's
   stored value>, "branches": {<value>: [<step>, ...]}}
  {"kind": "propose", "tool": <name>, "args_builder": <name registered
   in proposal_builders.BUILDERS>, "store_as": <context key, optional>}

A <path> is "task.<field>" (read an attribute off the Task) or
"ctx.<key>[.<subkey-or-index>]*" (read out of the growing run context).
Adding a 6th skill is adding one SkillDecl built only from these four
step shapes; see tests/test_sixth_skill_adds_no_engine_code.py.
"""
from __future__ import annotations

import dataclasses
from typing import Any

Step = dict[str, Any]


@dataclasses.dataclass(frozen=True)
class SkillDecl:
    name: str
    description: str
    scoped_tools: frozenset[str]
    steps: tuple[Step, ...]


class RegistryScopeError(Exception):
    """Raised when a step references a tool outside its skill's
    scoped_tools. Exists to make "each skill declares the tools it may
    call" a property the engine enforces, not a convention a step
    author could silently violate."""
