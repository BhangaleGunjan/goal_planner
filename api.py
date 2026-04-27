import json
from fastapi import FastAPI, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from engine import start_session, generate_plan, generate_plan_stream, adapt_plan
from core import validate_goal
from auth import register_user, login_user, get_current_user
from database import (
    init_db, save_plan, get_user_plans, get_plan,
    delete_plan, get_tasks, toggle_task, get_streak, checkin,
    update_plan_data
)

# Init DB on startup
init_db()

app = FastAPI(openapi_url="/api/openapi.json", docs_url="/api/docs")

# ===== REQUEST MODELS =====

class AuthRequest(BaseModel):
    username: str
    password: str

class GoalRequest(BaseModel):
    goal: str

class PlanRequest(BaseModel):
    goal: str
    profile: str | None = None

class SavePlanRequest(BaseModel):
    goal: str
    profile: str | None = None
    plan_data: dict

class TaskToggleRequest(BaseModel):
    plan_id: int
    phase_index: int
    task_index: int

class AdaptRequest(BaseModel):
    task_states: dict
    going_well: str
    difficult: str

# ===== AUTH ROUTES =====

@app.post("/api/auth/register")
def register(req: AuthRequest):
    return register_user(req.username, req.password)

@app.post("/api/auth/login")
def login(req: AuthRequest):
    return login_user(req.username, req.password)

@app.get("/api/auth/me")
def me(user=Depends(get_current_user)):
    return {"user_id": user["id"], "username": user["username"]}

# ===== GOAL / PLAN GENERATION =====

@app.post("/api/plans/questions")
def plans_questions(req: GoalRequest, user=Depends(get_current_user)):
    valid, error = validate_goal(req.goal)
    if not valid:
        raise HTTPException(status_code=400, detail=error)
    try:
        questions = start_session(req.goal)
        return {"questions": questions}
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception:
        raise HTTPException(status_code=500, detail="Something went wrong. Please try again.")

@app.post("/api/plans/generate")
def plans_generate(req: PlanRequest, user=Depends(get_current_user)):
    valid, error = validate_goal(req.goal)
    if not valid:
        raise HTTPException(status_code=400, detail=error)
    try:
        profile_dict = {"notes": req.profile} if req.profile else {}
        plan_data = generate_plan(req.goal, profile_dict)
        return {"plan_data": plan_data}
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception:
        import traceback; traceback.print_exc()
        raise HTTPException(status_code=500, detail="Plan generation failed. Please try again.")

@app.post("/api/start")
def start(req: GoalRequest, user=Depends(get_current_user)):
    valid, error = validate_goal(req.goal)
    if not valid:
        raise HTTPException(status_code=400, detail=error)
    try:
        questions = start_session(req.goal)
        return {"questions": questions}
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception:
        raise HTTPException(status_code=500, detail="Something went wrong. Please try again.")

@app.post("/api/plan/stream")
def plan_stream(req: PlanRequest, user=Depends(get_current_user)):
    valid, error = validate_goal(req.goal)
    if not valid:
        raise HTTPException(status_code=400, detail=error)
    return StreamingResponse(
        generate_plan_stream(req.goal, req.profile),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )

# ===== SAVED PLANS =====

@app.post("/api/plans/save")
def save(req: SavePlanRequest, user=Depends(get_current_user)):
    profile_dict = {"notes": req.profile} if isinstance(req.profile, str) else (req.profile or {})
    plan_id = save_plan(user["id"], req.goal, profile_dict, req.plan_data)
    return {"plan_id": plan_id}

@app.get("/api/plans")
def list_plans(user=Depends(get_current_user)):
    plans = get_user_plans(user["id"])
    result = []
    for p in plans:
        data = json.loads(p["plan_data"])
        tasks = get_tasks(p["id"])
        total = len(tasks)
        done = sum(1 for t in tasks if t["completed"])
        streak = get_streak(p["id"], user["id"])
        result.append({
            "id": p["id"],
            "goal": p["goal"],
            "created_at": p["created_at"],
            "phase_count": len(data.get("phases", [])),
            "total_tasks": total,
            "done_tasks": done,
            "streak": streak["current_streak"] if streak else 0,
        })
    return {"plans": result}

@app.get("/api/plans/{plan_id}")
def get_single_plan(plan_id: int, user=Depends(get_current_user)):
    plan = get_plan(plan_id, user["id"])
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found.")
    tasks = get_tasks(plan_id)
    streak = get_streak(plan_id, user["id"])
    return {
        "id": plan["id"],
        "goal": plan["goal"],
        "profile": json.loads(plan["profile"]),
        "plan_data": json.loads(plan["plan_data"]),
        "created_at": plan["created_at"],
        "tasks": tasks,
        "streak": streak
    }

@app.delete("/api/plans/{plan_id}")
def remove_plan(plan_id: int, user=Depends(get_current_user)):
    delete_plan(plan_id, user["id"])
    return {"ok": True}

# ===== TASKS =====

@app.post("/api/tasks/toggle")
def toggle(req: TaskToggleRequest, user=Depends(get_current_user)):
    plan = get_plan(req.plan_id, user["id"])
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found.")
    new_state = toggle_task(req.plan_id, req.phase_index, req.task_index)
    return {"completed": new_state}

# ===== STREAKS =====

@app.post("/api/plans/{plan_id}/checkin")
def do_checkin(plan_id: int, user=Depends(get_current_user)):
    plan = get_plan(plan_id, user["id"])
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found.")
    result = checkin(plan_id, user["id"])
    return result

# ===== ADAPT =====

@app.post("/api/plans/{plan_id}/adapt")
def adapt(plan_id: int, req: AdaptRequest, user=Depends(get_current_user)):
    plan = get_plan(plan_id, user["id"])
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found.")
    try:
        plan_data = json.loads(plan["plan_data"])
        plan_data["goal"] = plan["goal"]
        updated_plan, first_incomplete = adapt_plan(
            plan_data, req.task_states, req.going_well, req.difficult
        )
        update_plan_data(plan_id, user["id"], updated_plan, first_incomplete)
        return {"plan": updated_plan, "adapted_from_phase": first_incomplete}
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Adaptation failed. Please try again.")

# ===== STATIC (must be last) =====
app.mount("/", StaticFiles(directory="web", html=True), name="web")