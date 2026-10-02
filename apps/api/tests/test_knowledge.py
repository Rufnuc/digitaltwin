"""Knowledgebase: versioned articles, tags, pin, feedback, RBAC, activity logging."""
from __future__ import annotations

from app.models.system import AuditLog


def test_create_edit_versions_tags(client, auth_headers):
    h = auth_headers("MANAGER")
    r = client.post("/api/v1/kb/articles", headers=h,
                    json={"title": "How to sell", "body": "v1 body", "category": "Sales",
                          "tags": ["sales", "pos"]})
    assert r.status_code == 201, r.text
    art = r.json()
    aid = art["id"]
    assert art["version_no"] == 1
    assert art["tags"] == ["sales", "pos"]

    r = client.patch(f"/api/v1/kb/articles/{aid}", headers=h,
                     json={"body": "v2 body", "change_note": "clarified step 2"})
    assert r.status_code == 200
    assert r.json()["version_no"] == 2

    versions = client.get(f"/api/v1/kb/articles/{aid}/versions", headers=h).json()["items"]
    assert [v["version_no"] for v in versions] == [2, 1]


def test_pin_and_feedback(client, auth_headers):
    h = auth_headers("MANAGER")
    aid = client.post("/api/v1/kb/articles", headers=h,
                      json={"title": "Pinned doc", "body": "x"}).json()["id"]
    # Pin → appears in list as pinned.
    assert client.post(f"/api/v1/kb/articles/{aid}/pin", headers=h, json={"pinned": True}).status_code == 200
    lst = client.get("/api/v1/kb/articles", headers=h).json()
    assert any(a["id"] == aid and a["pinned"] for a in lst["items"])

    # Feedback: yes, then change to no — counts stay consistent (one vote per user).
    r = client.post(f"/api/v1/kb/articles/{aid}/feedback", headers=h, json={"helpful": True}).json()
    assert r["helpful_yes"] == 1 and r["helpful_no"] == 0
    r = client.post(f"/api/v1/kb/articles/{aid}/feedback", headers=h, json={"helpful": False}).json()
    assert r["helpful_yes"] == 0 and r["helpful_no"] == 1
    detail = client.get(f"/api/v1/kb/articles/{aid}", headers=h).json()
    assert detail["my_vote"] is False


def test_edits_are_written_to_activity_log(client, auth_headers, db):
    h = auth_headers("MANAGER")
    client.post("/api/v1/kb/articles", headers=h, json={"title": "Policy", "body": "x"})
    logs = db.query(AuditLog).filter_by(action="KB_EDIT").count()
    assert logs >= 1


def test_staff_cannot_access_knowledgebase(client, auth_headers):
    r = client.get("/api/v1/kb/articles", headers=auth_headers("STAFF"))
    assert r.status_code == 403
    r = client.post("/api/v1/kb/articles", headers=auth_headers("STAFF"),
                    json={"title": "x", "body": "y"})
    assert r.status_code == 403


def test_seed_guides_visible_changelog_internal(client, auth_headers, db):
    from app.services import knowledgebase as kb
    from scripts.seed_kb_history import CHANGELOG_TITLE, COMMITS, GUIDES, seed
    res = seed(db)
    assert res[CHANGELOG_TITLE] == "seeded"
    assert seed(db)[CHANGELOG_TITLE] == "current"  # idempotent

    # The owner/manager (not a developer) sees the guides but NOT the dev changelog.
    h = auth_headers("MANAGER")
    arts = client.get("/api/v1/kb/articles?include_archived=true", headers=h).json()["items"]
    titles = {a["title"] for a in arts}
    assert CHANGELOG_TITLE not in titles
    for title, _cat, _body in GUIDES:
        assert title in titles

    # A developer (is_dev=True at the service layer) does see the detailed changelog.
    items, _cats, _tags = kb.list_articles(db, include_archived=True, is_dev=True)
    changelog = next(a for a in items if a["title"] == CHANGELOG_TITLE)
    assert changelog["internal"] is True
    assert changelog["version_no"] == len(COMMITS)
    versions = kb.list_versions(db, changelog["id"])
    assert min(v["changed_at"][:10] for v in versions) == "2026-09-15"
    assert all(len(v["body"]) > 20 for v in versions)


def test_internal_article_hidden_from_non_developer(db):
    from app.services import knowledgebase as kb
    art = kb.create_article(db, title="Dev notes", body="secret build notes",
                            category="Build History", user_id=1, internal=True)
    # Owner/staff (not dev): not in list, not readable.
    items, _c, _t = kb.list_articles(db, is_dev=False)
    assert all(a["id"] != art.id for a in items)
    assert kb.get_article(db, art.id, is_dev=False) is None
    # Developer: visible and readable.
    items_dev, _c, _t = kb.list_articles(db, is_dev=True)
    assert any(a["id"] == art.id for a in items_dev)
    assert kb.get_article(db, art.id, is_dev=True) is not None


def test_seed_does_not_clobber_human_articles(client, auth_headers, db):
    from scripts.seed_kb_history import CHANGELOG_TITLE, seed
    # A human writes an article that happens to share the changelog title.
    client.post("/api/v1/kb/articles", headers=auth_headers("MANAGER"),
                json={"title": CHANGELOG_TITLE, "body": "my own notes"})
    assert seed(db)[CHANGELOG_TITLE] == "skip-human"
    detail = client.get(f"/api/v1/kb/articles", headers=auth_headers("MANAGER")).json()["items"]
    mine = next(a for a in detail if a["title"] == CHANGELOG_TITLE)
    got = client.get(f"/api/v1/kb/articles/{mine['id']}", headers=auth_headers("MANAGER")).json()
    assert got["body"] == "my own notes"  # untouched
