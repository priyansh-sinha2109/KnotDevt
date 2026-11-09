from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db.identity import Role
from app.db.session import engine
from app.db.sources import SourceRevision
from app.services.access import require_project
from app.workers.celery_app import execute
from tests.support import FIXTURES, client_for, project_with


def test_graph_permissions_pagination_and_text_search() -> None:
    project, [(lead_id, reviewer), (_, other)] = project_with(Role.REVIEWER, Role.ADMIN)
    with client_for(reviewer) as lead, client_for(other) as admin:
        import_path = f"/api/v1/projects/{project}/imports"
        source_path = f"/api/v1/projects/{project}/sources"
        claims = f"/api/v1/projects/{project}/claims"
        for name in ("issues", "conversations"):
            job = lead.post(
                import_path,
                content=(FIXTURES / f"{name}.json").read_bytes(),
                headers={"Content-Type": "application/json"},
            ).json()["id"]
            execute(job)

        items = {
            item["original_id"]: item for item in lead.get(source_path).json()["items"]
        }
        assert (
            lead.get(source_path, params={"query": "PAY-21"}).json()["items"][0][
                "original_id"
            ]
            == "PAY-21"
        )
        assert (
            admin.get(source_path, params={"query": "FINANCE-ONLY-227"}).json()["items"]
            == []
        )
        assert (
            lead.get(source_path, params={"query": "rollback"}).json()["items"][0][
                "original_id"
            ]
            == "M-07"
        )

        def pointer(source: str, relation: str = "supports") -> dict:
            item = items[source]
            return {
                "revision_id": item["revision_id"],
                "start": 0,
                "end": len(item["excerpt"]),
                "quote": item["excerpt"],
                "relation": relation,
            }

        friday = lead.post(
            claims,
            json={
                "kind": "decision",
                "status": "proposed",
                "statement": "Friday proposal",
                "evidence": [pointer("PAY-21")],
            },
        ).json()["id"]
        monday = lead.post(
            claims,
            json={
                "kind": "decision",
                "status": "accepted",
                "statement": "Monday conditional release",
                "evidence": [pointer("M-07"), pointer("C-19", "requires")],
                "relationships": [{"target_id": friday, "relation": "supersedes"}],
            },
        ).json()["id"]
        mixed = lead.post(
            claims,
            json={
                "kind": "risk",
                "statement": "Private FINANCE-ONLY concern",
                "evidence": [pointer("M-07"), pointer("FIN-12")],
                "relationships": [{"target_id": monday, "relation": "requires"}],
            },
        ).json()["id"]
        invalid = pointer("M-07")
        invalid["quote"] = "x" * invalid["end"]
        assert (
            lead.post(
                claims,
                json={
                    "kind": "decision",
                    "statement": "Invalid span",
                    "evidence": [invalid],
                },
            ).status_code
            == 422
        )
        assert (
            admin.post(
                claims,
                json={
                    "kind": "risk",
                    "statement": "Hidden reference",
                    "evidence": [pointer("FIN-12")],
                },
            ).status_code
            == 422
        )
        assert admin.get(f"/api/v1/claims/{mixed}/tree").status_code == 404

        tree = f"/api/v1/claims/{monday}/tree"
        page = admin.get(tree, params={"limit": 2}).json()
        assert len(page["branches"]) == 2
        assert page["next_offset"] == 2
        tail = admin.get(tree, params={"offset": 2}).json()
        assert tail["next_offset"] is None
        assert len(tail["branches"]) == 1
        assert tail["branches"][0]["related_claim"]["relation"] == "supersedes"
        outline = admin.get(f"/api/v1/claims/{monday}/outline")
        assert "M-07" in outline.text and "FINANCE-ONLY" not in outline.text

    with Session(engine()) as db:
        role = db.execute(
            text(
                "SELECT rolsuper, rolbypassrls FROM pg_roles "
                "WHERE rolname = current_user"
            )
        ).one()
        assert tuple(role) == (False, False)
        assert db.scalar(select(SourceRevision.id).limit(1)) is None
        require_project(db, project, lead_id)
        assert db.scalar(select(SourceRevision.id).limit(1)) is not None
        db.commit()
        assert db.scalar(select(SourceRevision.id).limit(1)) is None
