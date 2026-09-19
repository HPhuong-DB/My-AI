from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from services.goal_service import create_goal, get_goal, list_goals, update_goal
from services.planner_service import create_plan, get_plan, update_step

router = APIRouter()


class GoalCreatePayload(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: str = Field(default="", max_length=10000)
    priority: int = Field(default=3, ge=1, le=5)
    target_date: str | None = None


class GoalUpdatePayload(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=10000)
    status: str | None = None
    priority: int | None = Field(default=None, ge=1, le=5)
    progress: int | None = Field(default=None, ge=0, le=100)
    target_date: str | None = None


class PlanPayload(BaseModel):
    steps: list[dict] | None = Field(default=None, max_length=30)


class StepUpdatePayload(BaseModel):
    status: str | None = None
    progress: int | None = Field(default=None, ge=0, le=100)


@router.post("/goals")
async def create_goal_endpoint(payload: GoalCreatePayload, user_id: str = Query("default", min_length=1, max_length=100)):
    try:
        goal = create_goal(user_id, payload.title, payload.description, payload.priority, payload.target_date)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if goal is None:
        raise HTTPException(status_code=503, detail="Không thể lưu goal")
    return {"ok": True, "goal": goal}


@router.get("/goals")
async def list_goals_endpoint(user_id: str = Query("default", min_length=1, max_length=100), include_archived: bool = False):
    return {"user_id": user_id, "goals": list_goals(user_id, include_archived)}


@router.get("/goals/{goal_id}")
async def get_goal_endpoint(goal_id: int, user_id: str = Query("default", min_length=1, max_length=100)):
    goal = get_goal(goal_id, user_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy goal")
    return {"user_id": user_id, "goal": goal, "steps": get_plan(goal_id, user_id)}


@router.patch("/goals/{goal_id}")
async def update_goal_endpoint(goal_id: int, payload: GoalUpdatePayload, user_id: str = Query("default", min_length=1, max_length=100)):
    try:
        goal = update_goal(goal_id, user_id, payload.title, payload.description, payload.status, payload.priority, payload.progress, payload.target_date)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if goal is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy goal")
    return {"ok": True, "goal": goal}


@router.post("/goals/{goal_id}/plan")
async def create_plan_endpoint(goal_id: int, payload: PlanPayload = PlanPayload(), user_id: str = Query("default", min_length=1, max_length=100)):
    try:
        steps = create_plan(goal_id, user_id, payload.steps)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"ok": True, "goal_id": goal_id, "steps": steps}


@router.get("/goals/{goal_id}/steps")
async def get_plan_endpoint(goal_id: int, user_id: str = Query("default", min_length=1, max_length=100)):
    return {"goal_id": goal_id, "user_id": user_id, "steps": get_plan(goal_id, user_id)}


@router.patch("/goals/steps/{step_id}")
async def update_step_endpoint(step_id: int, payload: StepUpdatePayload, user_id: str = Query("default", min_length=1, max_length=100)):
    try:
        step = update_step(step_id, user_id, payload.status, payload.progress)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if step is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy goal step")
    return {"ok": True, "step": step}
