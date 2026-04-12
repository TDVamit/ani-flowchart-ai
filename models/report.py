from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from datetime import datetime, date


class DailyReport(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: Optional[str] = Field(default=None, alias="_id")
    project_id: str
    entry_id: str
    report_date: date
    week_number: int
    day_number: int

    llm_provider: str
    llm_model: str

    executive_summary: str = ""
    key_findings_today: list[str] = []
    patterns_emerging: str = ""
    hypothesis_update: str = ""
    stakeholder_notes: str = ""
    risks_and_flags: list[str] = []
    progress_summary: str = ""
    tomorrow_plan: str = ""
    tomorrow_priorities: list[str] = []

    updated_cumulative_summary: str = ""
    updated_key_findings: list[str] = []
    updated_confirmed_gaps: list[str] = []
    updated_open_questions: list[str] = []
    updated_stakeholder_insights: dict = {}

    generated_at: datetime = Field(default_factory=datetime.utcnow)
    prompt_tokens: int = 0
    completion_tokens: int = 0
