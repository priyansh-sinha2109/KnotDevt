import hashlib
import secrets
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, StringConstraints
from redis.exceptions import RedisError
from sqlalchemy.dialects.postgresql import insert

from app.api.dependencies import DB, Actor
from app.core.cache import redis_client
from app.db.identity import Project, ProjectMembership, Role, WorkspaceMembership
from app.repositories.sources import lock_project
from app.schemas.identity import ProjectView
from app.services.access import audit, require_project, require_workspace_admin

router = APIRouter(tags=["projects"])


class InviteInput(BaseModel):
    email: Annotated[
        str,
        StringConstraints(strip_whitespace=True, max_length=254, pattern=r"^\S+@\S+$"),
    ]


class InviteView(BaseModel):
    code: str


class RedeemInput(BaseModel):
    code: Annotated[
        str, StringConstraints(strip_whitespace=True, pattern=r"^[\w-]{43}$")
    ]


class StoredInvite(InviteInput):
    project_id: UUID
    inviter_id: UUID


def invite_key(code: str) -> str:
    return "knotdevt:invite:" + hashlib.sha256(code.encode()).hexdigest()


@router.post("/projects/{project_id}/invitations", status_code=201)
def issue_invitation(
    project_id: UUID, body: InviteInput, identity: Actor, db: DB, response: Response
) -> InviteView:
    access = require_project(db, project_id, identity.user.id)
    require_workspace_admin(db, access.project.workspace_id, identity.user.id)
    invite = StoredInvite(
        project_id=project_id, inviter_id=identity.user.id, email=body.email.lower()
    )
    code = secrets.token_urlsafe(32)
    try:
        redis_client().set(invite_key(code), invite.model_dump_json(), ex=3600)
    except RedisError:
        raise HTTPException(503, "Invitations are temporarily unavailable") from None
    response.headers["Cache-Control"] = "no-store"
    return InviteView(code=code)


@router.post("/invitations/redeem")
def redeem_invitation(body: RedeemInput, identity: Actor, db: DB) -> ProjectView:
    key = invite_key(body.code)
    invalid = HTTPException(404, "Invitation unavailable for this account")
    try:
        value = redis_client().get(key)
    except RedisError:
        raise HTTPException(503, "Invitations are temporarily unavailable") from None
    if not isinstance(value, bytes):
        raise invalid
    invite = StoredInvite.model_validate_json(value)
    if invite.email != identity.user.email:
        raise invalid
    project = db.get(Project, invite.project_id)
    if project is None:
        raise invalid
    lock_project(db, project.id)
    require_workspace_admin(db, project.workspace_id, invite.inviter_id)
    try:
        if redis_client().getdel(key) != value:
            raise invalid
    except RedisError:
        raise HTTPException(503, "Invitations are temporarily unavailable") from None
    db.execute(
        insert(WorkspaceMembership)
        .values(
            workspace_id=project.workspace_id,
            user_id=identity.user.id,
            role=Role.RECIPIENT,
        )
        .on_conflict_do_nothing()
    )
    db.execute(
        insert(ProjectMembership)
        .values(project_id=project.id, user_id=identity.user.id, role=Role.RECIPIENT)
        .on_conflict_do_nothing()
    )
    access = require_project(db, project.id, identity.user.id)
    audit(db, identity.user.id, "project.invitation_redeemed", project=project)
    db.commit()
    return ProjectView(
        id=project.id,
        workspace_id=project.workspace_id,
        name=project.name,
        role=access.role,
    )
