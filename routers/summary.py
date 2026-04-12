"""
Public summary router — no auth required.
Exposes read-only engagement data for the /summary page.
Returns everything about current progress and daily inputs,
but strips next-day plans/priorities from report data.
"""

from fastapi import APIRouter, HTTPException
from database import get_db
from bson import ObjectId

router = APIRouter(prefix="/api/summary", tags=["summary"])


@router.get("/projects")
async def list_projects_public():
    """List all projects (name + id only) for the public selector."""
    db = get_db()
    cursor = db.projects.find({}, {"brief.engagement_name": 1, "brief.client_name": 1}).sort("created_at", -1)
    projects = []
    async for doc in cursor:
        projects.append({
            "_id": str(doc["_id"]),
            "engagement_name": doc["brief"]["engagement_name"],
            "client_name": doc["brief"]["client_name"],
        })
    return projects


@router.get("/{project_id}")
async def get_project_summary(project_id: str):
    """
    Full public summary for a project.

    Returns:
    - project brief (engagement info)
    - context store (current cumulative progress, findings, gaps, questions, stakeholders)
    - all daily entries (inputs only — findings, annotations, plan review, transcripts, docs)
    - reports (executive summary, findings, patterns, hypothesis, stakeholder notes,
               risks, progress — NO tomorrow plan/priorities)
    """
    db = get_db()

    project_doc = await db.projects.find_one({"_id": ObjectId(project_id)})
    if not project_doc:
        raise HTTPException(status_code=404, detail="Project not found")
    project_doc["_id"] = str(project_doc["_id"])

    context_doc = await db.context_store.find_one({"project_id": project_id})
    if context_doc:
        context_doc["_id"] = str(context_doc["_id"])

    # All entries sorted by date ascending
    entries = []
    async for doc in db.daily_entries.find({"project_id": project_id}).sort("entry_date", 1):
        doc["_id"] = str(doc["_id"])
        entries.append(doc)

    # Reports — strip next-day data
    reports = []
    async for doc in db.reports.find({"project_id": project_id}).sort("report_date", 1):
        doc["_id"] = str(doc["_id"])
        # Remove next-day fields
        for field in (
            "tomorrow_plan", "tomorrow_priorities",
            "updated_cumulative_summary", "updated_key_findings",
            "updated_confirmed_gaps", "updated_open_questions",
            "updated_stakeholder_insights",
        ):
            doc.pop(field, None)
        reports.append(doc)

    return {
        "project": project_doc,
        "context": context_doc,
        "entries": entries,
        "reports": reports,
    }
