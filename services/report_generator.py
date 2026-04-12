"""
Orchestrates the full analysis pipeline:
1. Fetch project, entry, context store from DB
2. Build the briefing prompt
3. Call LLM
4. Parse JSON response
5. Save report to DB
6. Update context store
"""

import json
import re
from datetime import datetime
from database import get_db
from models.report import DailyReport
from models.context_store import ContextStore
from models.project import Project
from models.daily_entry import DailyEntry
from services.llm_service import LLMService
from services.context_builder import build_analysis_prompt
from bson import ObjectId


class ReportGenerator:

    def __init__(self, provider: str = None, model: str = None):
        self.llm = LLMService(provider=provider, model=model)

    async def run_analysis(
        self,
        project_id: str,
        entry_id: str,
        extra_user_prompt: str = None
    ) -> DailyReport:
        db = get_db()

        # 1. Fetch all needed documents
        project_doc = await db.projects.find_one({"_id": ObjectId(project_id)})
        entry_doc = await db.daily_entries.find_one({"_id": ObjectId(entry_id)})
        context_doc = await db.context_store.find_one({"project_id": project_id})

        if not project_doc or not entry_doc:
            raise ValueError("Project or entry not found")

        # Convert to pydantic models
        project = Project(**{**project_doc, "_id": str(project_doc["_id"])})
        entry = DailyEntry(**{**entry_doc, "_id": str(entry_doc["_id"])})

        if context_doc:
            context_store = ContextStore(**{**context_doc, "_id": str(context_doc["_id"])})
        else:
            context_store = ContextStore(project_id=project_id)

        # 2. Build prompts
        system_prompt, user_message = build_analysis_prompt(
            project, entry, context_store, extra_user_prompt
        )

        # 3. Call LLM
        llm_response = await self.llm.complete(
            system_prompt=system_prompt,
            user_message=user_message,
            max_tokens=8000,
            temperature=0.3
        )

        # 4. Parse JSON response
        raw = llm_response["content"].strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            # Try extracting JSON block via regex
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if match:
                parsed = json.loads(match.group())
            else:
                raise ValueError(f"Failed to parse LLM JSON response: {raw[:500]}")

        # 5. Build report object
        report = DailyReport(
            project_id=project_id,
            entry_id=entry_id,
            report_date=entry.entry_date,
            week_number=entry.week_number,
            day_number=entry.day_number,
            llm_provider=self.llm.provider,
            llm_model=self.llm.model,
            executive_summary=parsed.get("executive_summary", ""),
            key_findings_today=parsed.get("key_findings_today", []),
            patterns_emerging=parsed.get("patterns_emerging", ""),
            hypothesis_update=parsed.get("hypothesis_update", ""),
            stakeholder_notes=parsed.get("stakeholder_notes", ""),
            risks_and_flags=parsed.get("risks_and_flags", []),
            progress_summary=parsed.get("progress_summary", ""),
            tomorrow_plan=parsed.get("tomorrow_plan", ""),
            tomorrow_priorities=parsed.get("tomorrow_priorities", []),
            updated_cumulative_summary=parsed.get("updated_cumulative_summary", ""),
            updated_key_findings=parsed.get("updated_key_findings", []),
            updated_confirmed_gaps=parsed.get("updated_confirmed_gaps", []),
            updated_open_questions=parsed.get("updated_open_questions", []),
            updated_stakeholder_insights=parsed.get("updated_stakeholder_insights", {}),
            prompt_tokens=llm_response["prompt_tokens"],
            completion_tokens=llm_response["completion_tokens"]
        )

        # 6. Save report to DB
        report_dict = report.model_dump(by_alias=True, exclude={"id"})
        result = await db.reports.insert_one(report_dict)
        report.id = str(result.inserted_id)

        # 7. Update context store
        updated_context = {
            "project_id": project_id,
            "cumulative_summary": parsed.get("updated_cumulative_summary", context_store.cumulative_summary),
            "key_findings": parsed.get("updated_key_findings", context_store.key_findings),
            "confirmed_gaps": parsed.get("updated_confirmed_gaps", context_store.confirmed_gaps),
            "open_questions": parsed.get("updated_open_questions", context_store.open_questions),
            "stakeholder_insights": parsed.get("updated_stakeholder_insights", context_store.stakeholder_insights),
            "last_plan": parsed.get("tomorrow_plan", ""),
            "total_days_analyzed": context_store.total_days_analyzed + 1,
            "last_updated": datetime.utcnow()
        }

        await db.context_store.update_one(
            {"project_id": project_id},
            {"$set": updated_context},
            upsert=True
        )

        # 8. Mark entry as analysis completed
        await db.daily_entries.update_one(
            {"_id": ObjectId(entry_id)},
            {"$set": {"analysis_triggered": True, "analysis_completed": True}}
        )

        return report
