from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from pydantic import BaseModel
from typing import Optional
from services.report_generator import ReportGenerator
from database import get_db
from auth import verify_token
from bson import ObjectId

router = APIRouter(prefix="/api/analysis", tags=["analysis"], dependencies=[Depends(verify_token)])


class AnalysisRequest(BaseModel):
    project_id: str
    entry_id: str
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    extra_prompt: Optional[str] = None


class AnalysisStatus(BaseModel):
    status: str  # "pending" | "running" | "completed" | "failed"
    report_id: Optional[str] = None
    error: Optional[str] = None


# In-memory job tracker (for a single-user tool this is fine)
_jobs: dict = {}


@router.post("/trigger")
async def trigger_analysis(request: AnalysisRequest, background_tasks: BackgroundTasks):
    """Trigger end-of-day analysis. Runs in background."""
    job_id = f"{request.project_id}_{request.entry_id}"
    _jobs[job_id] = {"status": "running", "report_id": None, "error": None}

    background_tasks.add_task(
        _run_analysis_job,
        job_id,
        request.project_id,
        request.entry_id,
        request.llm_provider,
        request.llm_model,
        request.extra_prompt
    )

    return {"job_id": job_id, "status": "running"}


@router.get("/status/{job_id}")
async def get_analysis_status(job_id: str):
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return _jobs[job_id]


@router.get("/report/{report_id}")
async def get_report(report_id: str):
    db = get_db()
    report = await db.reports.find_one({"_id": ObjectId(report_id)})
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    report["_id"] = str(report["_id"])
    return report


@router.get("/reports/{project_id}")
async def list_reports(project_id: str):
    db = get_db()
    cursor = db.reports.find({"project_id": project_id}).sort("report_date", -1)
    reports = []
    async for r in cursor:
        r["_id"] = str(r["_id"])
        reports.append(r)
    return reports


async def _run_analysis_job(job_id, project_id, entry_id, provider, model, extra_prompt):
    try:
        generator = ReportGenerator(provider=provider, model=model)
        report = await generator.run_analysis(project_id, entry_id, extra_prompt)
        _jobs[job_id] = {"status": "completed", "report_id": report.id, "error": None}
    except Exception as e:
        _jobs[job_id] = {"status": "failed", "report_id": None, "error": str(e)}
