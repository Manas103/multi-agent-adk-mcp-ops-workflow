"""Mechanically checks the "6th added by declaration with 0 new
orchestration code" claim by diffing the actual commit that declared the
first five skills against the commit that added the sixth
(badge_vs_asset_routing). Pinned to the first commit's real hash rather
than "HEAD~1" because a later, unrelated commit could land between the
two without this test catching the wrong pair; if this repository's
history is ever rebased, update FIVE_SKILLS_COMMIT to whatever commit
still contains exactly revoke_access through all_level_signoff_routing.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

FIVE_SKILLS_COMMIT = "67ac6ba"
REPO_ROOT = Path(__file__).resolve().parents[1]

ENGINE_FILES = (
    "src/registry/engine.py",
    "src/registry/models.py",
    "src/registry/proposal_builders.py",
)


def _diff_stat(paths: tuple[str, ...]) -> str:
    result = subprocess.run(
        ["git", "diff", "--stat", FIVE_SKILLS_COMMIT, "HEAD", "--", *paths],
        cwd=REPO_ROOT, capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()


def test_engine_models_and_proposal_builders_are_unchanged_since_the_fifth_skill():
    diff = _diff_stat(ENGINE_FILES)
    assert diff == "", f"orchestration code changed when the 6th skill was added:\n{diff}"


def test_registry_data_did_change_to_add_the_sixth_skill():
    diff = _diff_stat(("src/registry/registry_data.py",))
    assert diff != "", "expected registry_data.py to gain the 6th skill's declaration"


def test_sixth_skill_is_declared_and_uses_only_existing_step_kinds():
    from src.registry import registry_data

    sixth = registry_data.SKILLS_BY_NAME["badge_vs_asset_routing"]

    def _kinds(steps) -> set[str]:
        found = set()
        for step in steps:
            found.add(step["kind"])
            if step["kind"] == "conditional":
                for branch in step["branches"].values():
                    found |= _kinds(branch)
        return found

    kinds_used_by_sixth = _kinds(sixth.steps)
    kinds_used_by_first_five = set()
    for name in registry_data.SKILLS_BEFORE_SIXTH:
        kinds_used_by_first_five |= _kinds(registry_data.SKILLS_BY_NAME[name].steps)

    assert kinds_used_by_sixth <= kinds_used_by_first_five
