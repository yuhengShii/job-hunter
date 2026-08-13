from fastapi import APIRouter, Depends

from backend.app.api.deps import get_current_user, get_db
from backend.app.core.exceptions import AppError
from backend.app.models import ApplyTask, Favorite, Job, SiteCredential, TaskStatus
from backend.app.schemas.apply import ApplyTaskCreate, ApplyTaskOut

apply_router = APIRouter(prefix="/api/apply", tags=["apply"])

_RUNNING = (TaskStatus.QUEUED.value, TaskStatus.IN_PROGRESS.value)


def _resolve_targets(db, job_ids: list[str] | None) -> list[dict]:
    """解析投递目标为 [{job_id, title, job_url, city}]；job_ids 缺省 = 全部收藏。"""
    if job_ids is not None:
        ids = list(dict.fromkeys(job_ids))
        jobs = {j.job_id: j for j in db.query(Job).filter(Job.job_id.in_(ids)).all()}
        return [
            {
                "job_id": jid,
                "title": jobs[jid].title,
                "job_url": jobs[jid].job_url,
                "city": jobs[jid].city,
            }
            for jid in ids
            if jid in jobs
        ]
    fav_job_ids = [f.job_id for f in db.query(Favorite).order_by(Favorite.created_at).all()]
    jobs = {j.job_id: j for j in db.query(Job).filter(Job.job_id.in_(fav_job_ids)).all()}
    return [
        {
            "job_id": jid,
            "title": jobs[jid].title,
            "job_url": jobs[jid].job_url,
            "city": jobs[jid].city,
        }
        for jid in fav_job_ids
        if jid in jobs
    ]


@apply_router.post("", response_model=ApplyTaskOut)
def create_apply_task(body: ApplyTaskCreate, db=Depends(get_db), user=Depends(get_current_user)):
    cred = db.get(SiteCredential, body.credential_id)
    if cred is None:
        raise AppError("登录凭据不存在", 400)
    if cred.site != "51job":
        raise AppError("v1 仅支持 51job 投递", 400)
    if db.query(ApplyTask).filter(ApplyTask.status.in_(_RUNNING)).first():
        raise AppError("已有进行中/排队中的投递任务", 409)
    targets = _resolve_targets(db, body.job_ids)
    if not targets:
        raise AppError("没有可投递的职位", 400)
    results = [
        {
            "job_id": t["job_id"],
            "title": t["title"],
            "job_url": t["job_url"],
            "city": t["city"],
            "status": "pending",
            "message": "",
        }
        for t in targets
    ]
    task = ApplyTask(
        credential_id=cred.id,
        credential_username=cred.username,
        status=TaskStatus.QUEUED.value,
        results=results,
        total_count=len(results),
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@apply_router.get("", response_model=list[ApplyTaskOut])
def list_apply_tasks(db=Depends(get_db), user=Depends(get_current_user)):
    return db.query(ApplyTask).order_by(ApplyTask.created_at.desc()).all()


@apply_router.get("/{task_id}", response_model=ApplyTaskOut)
def get_apply_task(task_id: int, db=Depends(get_db), user=Depends(get_current_user)):
    task = db.get(ApplyTask, task_id)
    if task is None:
        raise AppError("投递任务不存在", 404)
    return task


@apply_router.delete("/{task_id}")
def delete_apply_task(task_id: int, db=Depends(get_db), user=Depends(get_current_user)):
    task = db.get(ApplyTask, task_id)
    if task is None:
        raise AppError("投递任务不存在", 404)
    if task.status == TaskStatus.IN_PROGRESS.value:
        raise AppError("进行中的投递任务不能删除", 400)
    db.delete(task)
    db.commit()
    return {"ok": True}
