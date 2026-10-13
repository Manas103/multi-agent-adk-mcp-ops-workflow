"""FastAPI app exposing the approval queue to a human reviewer, and the app
this project would deploy to Cloud Run (it reads its listen port from the
$PORT env var per Cloud Run's contract). See the README's Honest framing for
why `gcloud run deploy` was not run this session.

Run: uvicorn src.approval.api:app --host 0.0.0.0 --port $PORT
"""

from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException

from . import gate

app = FastAPI(title="Offboarding Approval Queue")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/pending-actions")
def pending_actions(status: str = "PROPOSED") -> dict:
    return {"actions": gate.list_pending(status=status)}


@app.post("/approve/{action_id}")
def approve(action_id: int, approved_by: str = "reviewer") -> dict:
    try:
        return gate.approve_action(action_id, approved_by)
    except gate.ActionNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except gate.ActionAlreadyResolved as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
