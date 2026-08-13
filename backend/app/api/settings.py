from fastapi import APIRouter, Depends

from backend.app.api import deps
from backend.app.api.deps import get_current_user, get_db
from backend.app.core.exceptions import AppError
from backend.app.models import Setting, SiteCredential
from backend.app.schemas.settings import ScheduleIn, ScheduleOut, ScraperLoginIn, ScraperLoginOut
from backend.app.services.scheduler import apply_active_schedule

settings_router = APIRouter(prefix="/api/settings", tags=["settings"])

_SCHEDULE_KEY = "schedule"
_DEFAULT_SCHEDULE = {"enabled": False, "interval_minutes": 60, "keyword_ids": []}

_SCRAPER_LOGIN_KEY = "scraper_login"
_DEFAULT_SCRAPER_LOGIN = {"enabled": False, "credential_id": None}


@settings_router.get("/scraper")
def get_scraper_config(user=Depends(get_current_user)):
    """抓取器全局配置（只读），供前端约束 per-task max_pages 输入上限。"""
    cfg = deps._current_config
    return {"max_pages": cfg.max_pages, "headful": cfg.headful}


@settings_router.get("/schedule", response_model=ScheduleOut)
def get_schedule(db=Depends(get_db), user=Depends(get_current_user)):
    row = db.query(Setting).filter_by(key=_SCHEDULE_KEY).first()
    value = row.value if row else _DEFAULT_SCHEDULE
    return ScheduleOut(**value)


@settings_router.put("/schedule", response_model=ScheduleOut)
def put_schedule(body: ScheduleIn, db=Depends(get_db), user=Depends(get_current_user)):
    row = db.query(Setting).filter_by(key=_SCHEDULE_KEY).first()
    if row is None:
        row = Setting(key=_SCHEDULE_KEY, value=body.model_dump())
        db.add(row)
    else:
        row.value = body.model_dump()
    db.commit()
    apply_active_schedule()
    return body


@settings_router.get("/scraper-login", response_model=ScraperLoginOut)
def get_scraper_login(db=Depends(get_db), user=Depends(get_current_user)):
    row = db.query(Setting).filter_by(key=_SCRAPER_LOGIN_KEY).first()
    return ScraperLoginOut(**(row.value if row else _DEFAULT_SCRAPER_LOGIN))


@settings_router.put("/scraper-login", response_model=ScraperLoginOut)
def put_scraper_login(body: ScraperLoginIn, db=Depends(get_db), user=Depends(get_current_user)):
    if body.credential_id is not None and db.get(SiteCredential, body.credential_id) is None:
        raise AppError("凭据不存在", 400)
    row = db.query(Setting).filter_by(key=_SCRAPER_LOGIN_KEY).first()
    if row is None:
        row = Setting(key=_SCRAPER_LOGIN_KEY, value=body.model_dump())
        db.add(row)
    else:
        row.value = body.model_dump()
    db.commit()
    return body
