from fastapi import APIRouter, Depends

from backend.app.api.deps import get_current_user, get_db
from backend.app.core.exceptions import AppError
from backend.app.models import Keyword
from backend.app.schemas.keyword import KeywordCreate, KeywordOut, KeywordUpdate

keywords_router = APIRouter(prefix="/api/keywords", tags=["keywords"])


def _raise_dup(kw: str, city: str) -> None:
    raise AppError(f"关键字已存在: {kw}（地区 {city}）", 409)


@keywords_router.get("", response_model=list[KeywordOut])
def list_keywords(db=Depends(get_db), user=Depends(get_current_user)):
    return db.query(Keyword).order_by(Keyword.id).all()


@keywords_router.post("", response_model=KeywordOut)
def create_keyword(body: KeywordCreate, db=Depends(get_db), user=Depends(get_current_user)):
    if db.query(Keyword).filter_by(keyword=body.keyword, city=body.city).first():
        _raise_dup(body.keyword, body.city)
    kw = Keyword(keyword=body.keyword, scrape_mode=body.scrape_mode, city=body.city)
    db.add(kw)
    db.commit()
    db.refresh(kw)
    return kw


@keywords_router.put("/{keyword_id}", response_model=KeywordOut)
def update_keyword(keyword_id: int, body: KeywordUpdate, db=Depends(get_db), user=Depends(get_current_user)):
    kw = db.get(Keyword, keyword_id)
    if kw is None:
        raise AppError("关键字不存在", 404)
    new_kw = body.keyword if body.keyword is not None else kw.keyword
    new_city = body.city if body.city is not None else kw.city
    if body.keyword is not None or body.city is not None:
        if db.query(Keyword).filter(
            Keyword.keyword == new_kw, Keyword.city == new_city, Keyword.id != keyword_id
        ).first():
            _raise_dup(new_kw, new_city)
        kw.keyword = new_kw
        kw.city = new_city
    if body.scrape_mode is not None:
        kw.scrape_mode = body.scrape_mode
    db.commit()
    db.refresh(kw)
    return kw


@keywords_router.delete("/{keyword_id}")
def delete_keyword(keyword_id: int, db=Depends(get_db), user=Depends(get_current_user)):
    kw = db.get(Keyword, keyword_id)
    if kw is None:
        raise AppError("关键字不存在", 404)
    db.delete(kw)
    db.commit()
    return {"ok": True}


@keywords_router.post("/{keyword_id}/toggle", response_model=KeywordOut)
def toggle_keyword(keyword_id: int, db=Depends(get_db), user=Depends(get_current_user)):
    kw = db.get(Keyword, keyword_id)
    if kw is None:
        raise AppError("关键字不存在", 404)
    kw.enabled = not kw.enabled
    db.commit()
    db.refresh(kw)
    return kw
