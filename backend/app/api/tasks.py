from fastapi import APIRouter, Depends

from backend.app.api import deps
from backend.app.api.deps import get_current_user, get_db
from backend.app.core.exceptions import AppError
from backend.app.models import Keyword, ScrapeTask, SiteCredential, TaskStatus
from backend.app.schemas.task import TaskCreate, TaskOut

tasks_router = APIRouter(prefix="/api/tasks", tags=["tasks"])

_RUNNING = (TaskStatus.QUEUED.value, TaskStatus.IN_PROGRESS.value)


def _task_out(task: ScrapeTask, db) -> dict:
    data = {
        "id": task.id,
        "keyword_id": task.keyword_id,
        "mode": task.mode,
        "max_pages": task.max_pages,
        "status": task.status,
        "total_pages": task.total_pages,
        "total_found": task.total_found,
        "success_count": task.success_count,
        "failed_count": task.failed_count,
        "last_page": task.last_page,
        "start_time": task.start_time,
        "end_time": task.end_time,
        "error_message": task.error_message,
        "created_at": task.created_at,
        "login_credential_id": task.login_credential_id,
        "login_username": None,
    }
    if task.login_credential_id:
        cred = db.get(SiteCredential, task.login_credential_id)
        data["login_username"] = cred.username if cred else None
    return data


@tasks_router.post("", response_model=TaskOut)
def create_task(body: TaskCreate, db=Depends(get_db), user=Depends(get_current_user)):
    kw = db.get(Keyword, body.keyword_id)
    if kw is None:
        raise AppError("关键字不存在", 404)
    if body.mode != "playwright":
        raise AppError("v1 仅支持 playwright 模式", 400)
    if body.max_pages is not None and (body.max_pages < 1 or body.max_pages > deps._current_config.max_pages):
        raise AppError(f"max_pages 需在 1-{deps._current_config.max_pages} 之间", 400)
    if body.login_credential_id is not None and db.get(SiteCredential, body.login_credential_id) is None:
        raise AppError("登录凭据不存在", 400)
    if db.query(ScrapeTask).filter(ScrapeTask.keyword_id == body.keyword_id, ScrapeTask.status.in_(_RUNNING)).first():
        raise AppError("该关键字已有进行中的任务", 409)
    task = ScrapeTask(
        keyword_id=body.keyword_id,
        mode=body.mode,
        max_pages=body.max_pages,
        login_credential_id=body.login_credential_id,
        status=TaskStatus.QUEUED.value,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return _task_out(task, db)


@tasks_router.get("", response_model=list[TaskOut])
def list_tasks(db=Depends(get_db), user=Depends(get_current_user)):
    tasks = db.query(ScrapeTask).order_by(ScrapeTask.created_at.desc()).all()
    return [_task_out(t, db) for t in tasks]


@tasks_router.get("/{task_id}", response_model=TaskOut)
def get_task(task_id: int, db=Depends(get_db), user=Depends(get_current_user)):
    task = db.get(ScrapeTask, task_id)
    if task is None:
        raise AppError("任务不存在", 404)
    return _task_out(task, db)


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
