"""Knowledgebase: versioned articles, restore, RBAC, activity logging."""
from __future__ import annotations

from app.models.system import AuditLog


def test_create_edit_versions_and_restore(client, auth_headers):
    h = auth_headers("MANAGER")
    # Create.
    r = client.post("/api/v1/kb/articles", headers=h,
                    json={"title": "How to sell", "body": "v1 body", "category": "Sales"})
    assert r.status_code == 201, r.text
    art = r.json()
    aid = art["id"]
    assert art["version_no"] == 1

    # Edit → v2.
    r = client.patch(f"/api/v1/kb/articles/{aid}", headers=h,
                     json={"body": "v2 body", "change_note": "clarified step 2"})
    assert r.status_code == 200
    assert r.json()["version_no"] == 2

    # Version history has both, newest first.
    versions = client.get(f"/api/v1/kb/articles/{aid}/versions", headers=h).json()["items"]
    assert [v["version_no"] for v in versions] == [2, 1]

    # Restore v1 → becomes v3 with v1's body.
    r = client.post(f"/api/v1/kb/articles/{aid}/restore/1", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["version_no"] == 3
    assert body["body"] == "v1 body"


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


def test_seed_kb_history_creates_dated_changelog_and_guides(client, auth_headers, db):
    from scripts.seed_kb_history import CHANGELOG_TITLE, COMMITS, GUIDES, seed
    res = seed(db)
    assert res[CHANGELOG_TITLE] == "seeded"
    # Idempotent at the same content version: a second run is a no-op.
    assert seed(db)[CHANGELOG_TITLE] == "current"

    h = auth_headers("MANAGER")
    arts = client.get("/api/v1/kb/articles?include_archived=true", headers=h).json()["items"]
    titles = {a["title"] for a in arts}
    # Changelog + every how-to guide is present.
    assert CHANGELOG_TITLE in titles
    for title, _cat, _body in GUIDES:
        assert title in titles

    changelog = next(a for a in arts if a["title"] == CHANGELOG_TITLE)
    assert changelog["version_no"] == len(COMMITS)
    versions = client.get(f"/api/v1/kb/articles/{changelog['id']}/versions", headers=h).json()["items"]
    assert len(versions) == len(COMMITS)
    # Versions carry the REAL commit dates and a detailed body.
    assert min(v["changed_at"][:10] for v in versions) == "2026-09-15"
    assert all(len(v["body"]) > 20 for v in versions)  # detailed, not one-liners


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
