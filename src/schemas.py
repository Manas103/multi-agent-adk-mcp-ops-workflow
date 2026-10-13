"""Pydantic schemas for every state-changing action a tool can propose.

Every one of these is the JSON-schema-validated payload the human approval
gate reviews before anything in Postgres actually changes. A tool call that
cannot build one of these (missing field, wrong enum, employee id that does
not exist) is a schema-invalid call; the self-reflection loop in
src/adk_app/router_model.py is what turns a schema-invalid first attempt into
a valid second one, and src/approval/gate.py is the only code path allowed to
apply an approved action to the database.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


class AccessLevel(str, Enum):
    STANDARD = "STANDARD"
    ADMIN = "ADMIN"
    ALL = "ALL"


class TicketType(str, Enum):
    ASSET_RETURN = "ASSET_RETURN"
    POLICY_COMPLIANCE = "POLICY_COMPLIANCE"


class TicketStatus(str, Enum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    CLOSED = "CLOSED"


class ProposedAction(BaseModel):
    """Base shape every proposal shares: the acting specialist and a non-empty
    justification. Subclasses add the fields specific to the mutation."""

    employee_id: int
    reason: str = Field(min_length=8)
    proposed_by: str

    @field_validator("reason")
    @classmethod
    def reason_must_be_substantive(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("reason must not be blank")
        return v


class RevokeAccessAction(ProposedAction):
    action_type: Literal["REVOKE_ACCESS"] = "REVOKE_ACCESS"
    access_level: AccessLevel


class CreateTicketAction(ProposedAction):
    action_type: Literal["CREATE_TICKET"] = "CREATE_TICKET"
    ticket_type: TicketType
    asset_id: Optional[int] = None
    policy_doc_id: Optional[str] = None

    @field_validator("asset_id")
    @classmethod
    def asset_required_for_asset_return(cls, v, info):
        if info.data.get("ticket_type") == TicketType.ASSET_RETURN and v is None:
            raise ValueError("asset_id is required for an ASSET_RETURN ticket")
        return v

    @field_validator("policy_doc_id")
    @classmethod
    def policy_required_for_compliance(cls, v, info):
        if info.data.get("ticket_type") == TicketType.POLICY_COMPLIANCE and not v:
            raise ValueError("policy_doc_id is required for a POLICY_COMPLIANCE ticket")
        return v


class UpdateTicketStatusAction(BaseModel):
    action_type: Literal["UPDATE_TICKET_STATUS"] = "UPDATE_TICKET_STATUS"
    ticket_id: int
    new_status: TicketStatus
    proposed_by: str
    reason: str = Field(min_length=8)


ACTION_TYPES = {
    "REVOKE_ACCESS": RevokeAccessAction,
    "CREATE_TICKET": CreateTicketAction,
    "UPDATE_TICKET_STATUS": UpdateTicketStatusAction,
}


class SchemaValidationError(Exception):
    """Raised by an MCP tool when raw arguments cannot build a ProposedAction.
    Carries the pydantic error text back to the caller so the self-reflection
    loop has something concrete to correct against."""

    def __init__(self, action_type: str, raw_args: dict, pydantic_error: str):
        self.action_type = action_type
        self.raw_args = raw_args
        self.pydantic_error = pydantic_error
        super().__init__(f"{action_type} failed schema validation: {pydantic_error}")


def build_action(action_type: str, raw_args: dict):
    """The one place raw tool-call arguments become a validated action or a
    SchemaValidationError. Both MCP servers and the test suite call this
    directly so there is exactly one validation path, not one per tool."""

    model = ACTION_TYPES.get(action_type)
    if model is None:
        raise SchemaValidationError(action_type, raw_args, f"unknown action_type '{action_type}'")
    try:
        return model(**raw_args)
    except Exception as exc:  # pydantic.ValidationError plus the enum/lookup errors above
        raise SchemaValidationError(action_type, raw_args, str(exc)) from exc
