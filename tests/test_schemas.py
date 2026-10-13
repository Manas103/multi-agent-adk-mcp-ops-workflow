from src.schemas import SchemaValidationError, build_action


def test_revoke_access_valid():
    action = build_action("REVOKE_ACCESS", {
        "employee_id": 1, "access_level": "ADMIN", "reason": "leaving the company", "proposed_by": "test",
    })
    assert action.access_level.value == "ADMIN"


def test_revoke_access_short_reason_rejected():
    try:
        build_action("REVOKE_ACCESS", {
            "employee_id": 1, "access_level": "ADMIN", "reason": "no", "proposed_by": "test",
        })
        assert False, "expected SchemaValidationError"
    except SchemaValidationError:
        pass


def test_create_ticket_asset_return_requires_asset_id():
    try:
        build_action("CREATE_TICKET", {
            "employee_id": 1, "ticket_type": "ASSET_RETURN", "asset_id": None,
            "reason": "returning equipment", "proposed_by": "test",
        })
        assert False, "expected SchemaValidationError"
    except SchemaValidationError:
        pass


def test_create_ticket_policy_compliance_requires_doc_id():
    try:
        build_action("CREATE_TICKET", {
            "employee_id": 1, "ticket_type": "POLICY_COMPLIANCE", "policy_doc_id": "",
            "reason": "citing policy", "proposed_by": "test",
        })
        assert False, "expected SchemaValidationError"
    except SchemaValidationError:
        pass


def test_update_ticket_status_invalid_enum_rejected():
    try:
        build_action("UPDATE_TICKET_STATUS", {
            "ticket_id": 1, "new_status": "DONE", "reason": "closing it out", "proposed_by": "test",
        })
        assert False, "expected SchemaValidationError"
    except SchemaValidationError:
        pass


def test_unknown_action_type_rejected():
    try:
        build_action("DELETE_EVERYTHING", {})
        assert False, "expected SchemaValidationError"
    except SchemaValidationError:
        pass
