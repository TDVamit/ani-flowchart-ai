from fastapi import APIRouter, HTTPException, Depends
from database import get_db
from models.project import Project, ProjectBrief
from auth import verify_token
from datetime import datetime
from bson import ObjectId

router = APIRouter(prefix="/api/projects", tags=["projects"], dependencies=[Depends(verify_token)])


@router.post("/")
async def create_project(project: Project):
    db = get_db()
    project_dict = project.model_dump(by_alias=True, exclude={"id"})
    result = await db.projects.insert_one(project_dict)
    return {"id": str(result.inserted_id)}


@router.get("/")
async def list_projects():
    db = get_db()
    cursor = db.projects.find({}).sort("created_at", -1)
    projects = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        projects.append(doc)
    return projects


@router.get("/{project_id}")
async def get_project(project_id: str):
    db = get_db()
    doc = await db.projects.find_one({"_id": ObjectId(project_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Project not found")
    doc["_id"] = str(doc["_id"])
    return doc


@router.put("/{project_id}/brief")
async def update_brief(project_id: str, brief: ProjectBrief):
    db = get_db()
    await db.projects.update_one(
        {"_id": ObjectId(project_id)},
        {"$set": {"brief": brief.model_dump(), "updated_at": datetime.utcnow()}}
    )
    return {"status": "updated"}


@router.get("/{project_id}/context")
async def get_context_store(project_id: str):
    db = get_db()
    doc = await db.context_store.find_one({"project_id": project_id})
    if not doc:
        return {"project_id": project_id, "cumulative_summary": "", "key_findings": [], "total_days_analyzed": 0}
    doc["_id"] = str(doc["_id"])
    return doc


@router.delete("/{project_id}/context")
async def reset_context_store(project_id: str):
    """Reset the rolling context store for a project."""
    db = get_db()
    await db.context_store.delete_one({"project_id": project_id})
    return {"status": "reset"}
