from src.si_signoff import tool_catalog


def test_rank_candidates_picks_the_package_aware_tool_for_a_specific_intent():
    intent = "cascade the package segment together with its board segments for this channel"
    ranked = tool_catalog.rank_candidates(intent, list(tool_catalog.CASCADE_CANDIDATES))
    assert ranked[0][0] == "cascade_package_and_board"


def test_rank_candidates_ties_on_an_ambiguous_layer_mention():
    """cascade_board_only's own docstring says "no package layer", so an
    intent that only says "package layer" without "segment"/"together"
    ties both candidates and falls to the alphabetical tie-break; a real,
    disclosed finding (see README Findings), not a bug being masked."""
    intent = "cascade the stackup's package layer together with the board transmission lines"
    ranked = tool_catalog.rank_candidates(intent, list(tool_catalog.CASCADE_CANDIDATES))
    assert ranked[0][1] == ranked[1][1]
    assert ranked[0][0] == "cascade_board_only"


def test_rank_candidates_picks_board_only_for_a_specific_intent():
    intent = "cascade this board-only stackup, no package layer present, into one network"
    ranked = tool_catalog.rank_candidates(intent, list(tool_catalog.CASCADE_CANDIDATES))
    assert ranked[0][0] == "cascade_board_only"


def test_rank_candidates_picks_pam4_for_a_specific_simulate_intent():
    intent = "run the multi-level PAM4 simulation step for this cascaded channel"
    ranked = tool_catalog.rank_candidates(intent, list(tool_catalog.SIMULATE_CANDIDATES))
    assert ranked[0][0] == "simulate_pam4_channel"


def test_satisfiable_candidates_respects_required_inputs():
    assert tool_catalog.satisfiable_candidates(set()) == ["intake_channel"]
    assert set(tool_catalog.satisfiable_candidates({"channel_id"})) == {
        "intake_channel", "cascade_board_only", "cascade_package_and_board",
    }
