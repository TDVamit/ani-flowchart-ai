from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from datetime import datetime
from bson import ObjectId


class PyObjectId(str):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v, info=None):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid ObjectId")
        return str(v)


class ProjectBrief(BaseModel):
    """The static project brief — written once, used in every analysis session."""
    engagement_name: str
    client_name: str
    fde_name: str
    engagement_goal: str
    deliverable_description: str
    week_count: int = 4
    key_contacts: list[dict] = []
    org_structure: str = ""
    core_hypothesis: str = ""
    custom_context: str = ""


class Project(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    brief: ProjectBrief
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = True
    current_week: int = 1
    current_day: int = 1
