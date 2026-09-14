"""Benfieg chat history: persistence, per-user isolation, and the API."""
from __future__ import annotations

from app.seed.demo_data import seed


def test_ask_saves_a_conversation_and_continues_it(client, auth_headers, db):
    seed(db)
    h = auth_headers("VIEWER")

    r1 = client.post("/api/v1/assistant/ask", headers=h,
                     json={"question": "How is my business doing?"})
    assert r1.status_code == 200, r1.text
    body1 = r1.json()
    cid = body1["conversation_id"]
    assert cid and body1["conversation_title"]

    # Continuing the same conversation reuses it (no second chat is created).
    r2 = client.post("/api/v1/assistant/ask", headers=h,
                     json={"question": "What are my biggest risks?", "conversation_id": cid})
    assert r2.status_code == 200
    assert r2.json()["conversation_id"] == cid

    lst = client.get("/api/v1/assistant/conversations", headers=h)
    assert lst.status_code == 200
    items = lst.json()["items"]
    assert len(items) == 1 and items[0]["id"] == cid
    assert items[0]["message_count"] == 4  # 2 user + 2 assistant

    detail = client.get(f"/api/v1/assistant/conversations/{cid}", headers=h)
    assert detail.status_code == 200
    msgs = detail.json()["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant", "user", "assistant"]
    # The assistant message carries the tool trace so it re-renders with sourcing.
    assert msgs[1]["meta"]["provenance"] == "AI_INTERPRETATION"
    assert "tool_calls" in msgs[1]["meta"]


def test_history_is_per_user(client, auth_headers, db):
    seed(db)
    owner = auth_headers("OWNER")
    viewer = auth_headers("VIEWER")

    made = client.post("/api/v1/assistant/ask", headers=owner,
                       json={"question": "How is my business doing?"})
    cid = made.json()["conversation_id"]

    # A different user cannot see or open the owner's conversation.
    assert client.get("/api/v1/assistant/conversations", headers=viewer).json()["items"] == []
    url = f"/api/v1/assistant/conversations/{cid}"
    assert client.get(url, headers=viewer).status_code == 404
    assert client.delete(url, headers=viewer).status_code == 404


def test_rename_and_delete_conversation(client, auth_headers, db):
    seed(db)
    h = auth_headers("VIEWER")
    cid = client.post("/api/v1/assistant/ask", headers=h,
                      json={"question": "How is my business doing?"}).json()["conversation_id"]

    ren = client.patch(f"/api/v1/assistant/conversations/{cid}", headers=h,
                       json={"title": "Monthly review"})
    assert ren.status_code == 200
    assert client.get(f"/api/v1/assistant/conversations/{cid}", headers=h).json()["title"] == \
        "Monthly review"

    dele = client.delete(f"/api/v1/assistant/conversations/{cid}", headers=h)
    assert dele.status_code == 200
    assert client.get("/api/v1/assistant/conversations", headers=h).json()["items"] == []
