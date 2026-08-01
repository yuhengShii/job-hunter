from fastapi import APIRouter, Depends

from backend.app.api import deps
from backend.app.api.deps import get_current_user, get_db
from backend.app.core.exceptions import AppError
from backend.app.models import Keyword, ScrapeTask, TaskStatus
from backend.app.schemas.task import TaskCreate, TaskOut

tasks_router = APIRouter(prefix="/api/tasks", tags=["tasks"])

_RUNNING = (TaskStatus.QUEUED.value, TaskStatus.IN_PROGRESS.value)


@tasks_router.post("", response_model=TaskOut)
def create_task(body: TaskCreate, db=Depends(get_db), user=Depends(get_current_user)):
    kw = db.get(Keyword, body.keyword_id)
    if kw is None:
        raise AppError("关键字不存在", 404)
    if body.mode != "playwright":
        raise AppError("v1 仅支持 playwright 模式", 400)
    if body.max_pages is not None and (body.max_pages < 1 or body.max_pages > deps._current_config.max_pages):
        raise AppError(f"max_pages 需在 1-{deps._current_config.max_pages} 之间", 400)
    if db.query(ScrapeTask).filter(ScrapeTask.keyword_id == body.keyword_id, ScrapeTask.status.in_(_RUNNING)).first():
        raise AppError("该关键字已有进行中的任务", 409)
    task = ScrapeTask(
        keyword_id=body.keyword_id,
        mode=body.mode,
        status=TaskStatus.QUEUED.value,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@tasks_router.get("", response_model=list[TaskOut])
def list_tasks(db=Depends(get_db), user=Depends(get_current_user)):
    return db.query(ScrapeTask).order_by(ScrapeTask.created_at.desc()).all()


@tasks_router.get("/{task_id}", response_model=TaskOut)
def get_task(task_id: int, db=Depends(get_db), user=Depends(get_current_user)):
    task = db.get(ScrapeTask, task_id)
    if task is None:
        raise AppError("任务不存在", 404)
    return task


@tasks_router.delete("/{task_id}")
def delete_task(task_id: int, db=Depends(get_db), user=Depends(get_current_user)):
    task = db.get(ScrapeTask, task_id)
    if task is None:
        raise AppError("任务不存在", 404)
    if task.status == TaskStatus.IN_PROGRESS.value:
        raise AppError("进行中的任务不能删除", 400)
    db.delete(task)
    db.commit()
    return {"ok": True}
