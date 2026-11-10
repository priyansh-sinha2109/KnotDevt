from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, SecretStr, StringConstraints

from app.db.identity import Role


class LoginInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: Annotated[
        str,
        StringConstraints(strip_whitespace=True, max_length=254, pattern=r"^\S+@\S+$"),
    ]
    password: Annotated[SecretStr, StringConstraints(min_length=1, max_length=256)]


class RegistrationInput(LoginInput):
    password: Annotated[SecretStr, StringConstraints(min_length=12, max_length=256)]


class SessionView(BaseModel):
    user_id: UUID
    email: str
    csrf_token: str


class ProjectInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)
    ]


class ProjectView(BaseModel):
    id: UUID
    workspace_id: UUID
    name: str
    role: Role


class RoleInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Role


class MembershipView(BaseModel):
    user_id: UUID
    role: Role
