"""MCP server #2: the policy document store. Two read-only tools over the
six offboarding policy documents in offboard.policy_docs. This server never
proposes an action; it only lets PolicyResearchAgent find the document id a
TicketingAgent then cites when it calls propose_policy_ticket on the other
server.

Run standalone: python -m src.mcp_servers.policy_doc_server
"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from .. import db

server = MCPServer(
    name="policy-docs",
    instructions="Read-only search over offboarding policy documents. "
                 "search_policies(query) ranks documents by keyword overlap; "
                 "get_policy(doc_id) returns one document's full body.",
)


def _tokenize(text: str) -> set[str]:
    return {w.strip(".,()").lower() for w in text.split() if len(w) > 2}


@server.tool()
def search_policies(query: str) -> dict:
    """Rank policy documents by word overlap with the query. Returns the
    doc_id, title and overlap score for every document with a nonzero score,
    most relevant first."""
    query_terms = _tokenize(query)
    with db.cursor() as cur:
        cur.execute("SELECT doc_id, title, body FROM offboard.policy_docs")
        rows = cur.fetchall()

    scored = []
    for row in rows:
        doc_terms = _tokenize(row["title"] + " " + row["body"])
        overlap = len(query_terms & doc_terms)
        if overlap > 0:
            scored.append({"doc_id": row["doc_id"], "title": row["title"], "score": overlap})
    scored.sort(key=lambda r: (-r["score"], r["doc_id"]))
    return {"query": query, "results": scored}


@server.tool()
def get_policy(doc_id: str) -> dict:
    """Return one policy document's full title and body by id."""
    with db.cursor() as cur:
        cur.execute("SELECT doc_id, title, body FROM offboard.policy_docs WHERE doc_id = %s", (doc_id,))
        row = cur.fetchone()
    if row is None:
        return {"found": False, "doc_id": doc_id}
    return {"found": True, **dict(row)}


def main() -> None:
    server.run()


if __name__ == "__main__":
    main()
