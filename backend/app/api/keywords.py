from fastapi import APIRouter, Depends

from backend.app.api.deps import get_current_user, get_db
from backend.app.core.exceptions import AppError
from backend.app.models import Keyword
from backend.app.schemas.keyword import KeywordCreate, KeywordOut, KeywordUpdate

keywords_router = APIRouter(prefix="/api/keywords", tags=["keywords"])


@keywords_router.get("", response_model=list[KeywordOut])
def list_keywords(db=Depends(get_db), user=Depends(get_current_user)):
    return db.query(Keyword).order_by(Keyword.id).all()


@keywords_router.post("", response_model=KeywordOut)
def create_keyword(body: KeywordCreate, db=Depends(get_db), user=Depends(get_current_user)):
    if db.query(Keyword).filter_by(keyword=body.keyword).first():
        raise AppError(f"关键字已存在: {body.keyword}", 409)
    kw = Keyword(keyword=body.keyword, scrape_mode=body.scrape_mode)
    db.add(kw)
    db.commit()
    db.refresh(kw)
    return kw


@keywords_router.put("/{keyword_id}", response_model=KeywordOut)
def update_keyword(keyword_id: int, body: KeywordUpdate, db=Depends(get_db), user=Depends(get_current_user)):
    kw = db.get(Keyword, keyword_id)
    if kw is None:
        raise AppError("关键字不存在", 404)
    if body.keyword is not None:
        if db.query(Keyword).filter(Keyword.keyword == body.keyword, Keyword.id != keyword_id).first():
            raise AppError(f"关键字已存在: {body.keyword}", 409)
        kw.keyword = body.keyword
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
