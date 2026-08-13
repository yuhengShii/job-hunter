from fastapi import APIRouter, Depends

from backend.app.api import deps
from backend.app.api.deps import get_current_user, get_db
from backend.app.core.exceptions import AppError
from backend.app.core.site_security import decrypt_password, encrypt_password
from backend.app.models import ScrapeTask, SiteCredential, TaskStatus
from backend.app.schemas.site_credential import (
    SiteCredentialCreate,
    SiteCredentialOut,
    SiteCredentialUpdate,
)

site_credentials_router = APIRouter(prefix="/api/site-credentials", tags=["site-credentials"])

_RUNNING = (TaskStatus.QUEUED.value, TaskStatus.IN_PROGRESS.value)


def _key() -> bytes:
    return deps._current_config.site_secret_key


@site_credentials_router.get("", response_model=list[SiteCredentialOut])
def list_credentials(site: str | None = None, db=Depends(get_db), user=Depends(get_current_user)):
    q = db.query(SiteCredential)
    if site:
        q = q.filter(SiteCredential.site == site)
    return q.order_by(SiteCredential.created_at.desc()).all()


@site_credentials_router.post("", response_model=SiteCredentialOut)
def create_credential(body: SiteCredentialCreate, db=Depends(get_db), user=Depends(get_current_user)):
    site = body.site.strip()
    username = body.username.strip()
    if not site or not username or not body.password:
        raise AppError("site/username/password 均不能为空", 400)
    if db.query(SiteCredential).filter_by(site=site, username=username).first():
        raise AppError("该站点已存在同账号", 409)
    cred = SiteCredential(
        site=site,
        username=username,
        password_enc=encrypt_password(body.password, _key()),
        remark=body.remark,
    )
    db.add(cred)
    db.commit()
    db.refresh(cred)
    return cred


@site_credentials_router.put("/{cred_id}", response_model=SiteCredentialOut)
def update_credential(cred_id: int, body: SiteCredentialUpdate, db=Depends(get_db), user=Depends(get_current_user)):
    cred = db.get(SiteCredential, cred_id)
    if cred is None:
        raise AppError("凭据不存在", 404)
    cred.remark = body.remark
    if body.password:
        cred.password_enc = encrypt_password(body.password, _key())
    db.commit()
    db.refresh(cred)
    return cred


@site_credentials_router.delete("/{cred_id}")
def delete_credential(cred_id: int, db=Depends(get_db), user=Depends(get_current_user)):
    cred = db.get(SiteCredential, cred_id)
    if cred is None:
        raise AppError("凭据不存在", 404)
    if db.query(ScrapeTask).filter(
        ScrapeTask.login_credential_id == cred_id,
        ScrapeTask.status.in_(_RUNNING),
    ).first():
        raise AppError("该凭据被进行中/排队中的任务引用，不能删除", 409)
    db.query(ScrapeTask).filter(ScrapeTask.login_credential_id == cred_id).update(
        {ScrapeTask.login_credential_id: None}
    )
    db.delete(cred)
    db.commit()
    return {"ok": True}
