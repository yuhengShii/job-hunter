from fastapi import APIRouter, Depends

from backend.app.api.deps import get_current_user, get_db
from backend.app.services import stats as stats_service

stats_router = APIRouter(prefix="/api/stats", tags=["stats"])


@stats_router.get("/overview")
def get_overview(keyword_id: int | None = None, db=Depends(get_db), user=Depends(get_current_user)):
    window = stats_service.get_window_start(db, keyword_id)
    return stats_service.overview(db, window)


@stats_router.get("/salary")
def get_salary(keyword_id: int | None = None, group_by: str = "city", db=Depends(get_db), user=Depends(get_current_user)):
    window = stats_service.get_window_start(db, keyword_id)
    return stats_service.salary_stats(db, window, group_by=group_by)


@stats_router.get("/company")
def get_company(keyword_id: int | None = None, db=Depends(get_db), user=Depends(get_current_user)):
    window = stats_service.get_window_start(db, keyword_id)
    return stats_service.company_stats(db, window)


@stats_router.get("/trend")
def get_trend(keyword_id: int | None = None, days: int = 30, db=Depends(get_db), user=Depends(get_current_user)):
    window = stats_service.get_window_start(db, keyword_id)
    return stats_service.trend_stats(db, window, days=days)


@stats_router.get("/tags")
def get_tags(keyword_id: int | None = None, top_n: int = 10, db=Depends(get_db), user=Depends(get_current_user)):
    window = stats_service.get_window_start(db, keyword_id)
    return stats_service.tag_stats(db, window, top_n=top_n)
