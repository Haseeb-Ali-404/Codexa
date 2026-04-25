from pydantic import BaseModel
from typing import List, Literal, Optional


class Signup(BaseModel):
    """
    Payload for creating a new user.
    """
    name: str
    email: str
    password: str
    confirm_password: str


class Login(BaseModel):
    """
    Payload for logging in an existing user.
    """
    email: str
    password: str


class ChatPayload(BaseModel):
    """
    Payload for sending a chat message.
    project_id is Optional because new projects start with None.
    """
    user_id: str
    chat_id: Optional[str]  # None = create a new project
    message: str


class ChatRenamePayload(BaseModel):
    user_id: str
    title: str

class ProjectPayload(BaseModel):
    user_id: str
    title: str
    description: Optional[str] = None
    chat_id: str
    code_language: Optional[str] = "Python"
    code: Optional[str] = None
    

class GeneratePayload(BaseModel):
    """
    Payload for generating a new project manually (if needed).
    """
    user_id: str
    project_name: str
    description: Optional[str] = None


class PreviewStartPayload(BaseModel):
    """
    Payload for starting project preview execution.
    Defaults to local mode when omitted for backwards compatibility.
    """
    mode: Optional[Literal["local", "docker"]] = None


class AssetGenerationPayload(BaseModel):
    description: Optional[str] = None
    force: bool = False
    include_uml: Optional[bool] = None
    diagram_types: Optional[List[str]] = None
