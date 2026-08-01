from fastapi import APIRouter, Depends

from backend.app.api.deps import get_current_user, get_db
from backend.app.models import Setting
from backend.app.schemas.settings import ScheduleIn, ScheduleOut

settings_router = APIRouter(prefix="/api/settings", tags=["settings"])

_SCHEDULE_KEY = "schedule"
_DEFAULT_SCHEDULE = {"enabled": False, "interval_minutes": 60, "keyword_ids": []}


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
    return body
