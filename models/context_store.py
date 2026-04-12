from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from datetime import datetime


class ContextStore(BaseModel):
    """
    The rolling cumulative summary — updated by Claude at the end of each analysis.
    This is the key to long-running context: Claude compresses all prior findings
    into this document, which is fed back in as context for the next session.
    """
    model_config = ConfigDict(populate_by_name=True)

    id: Optional[str] = Field(default=None, alias="_id")
    project_id: str

    cumulative_summary: str = ""
    key_findings: list[str] = []
    confirmed_gaps: list[str] = []
    open_questions: list[str] = []
    stakeholder_insights: dict = {}
    last_plan: str = ""

    last_updated: datetime = Field(default_factory=datetime.utcnow)
    total_days_analyzed: int = 0
