from fastapi import APIRouter, Depends

from backend.app.api import deps
from backend.app.api.deps import authenticate, get_current_user, get_db
from backend.app.core.security import create_access_token
from backend.app.schemas.auth import LoginRequest, TokenResponse, UserOut

auth_router = APIRouter(prefix="/api/auth", tags=["auth"])


@auth_router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db=Depends(get_db)):
    user = authenticate(db, body.username, body.password)
    token = create_access_token(user.username, deps._current_config.jwt_secret)
    return TokenResponse(access_token=token)


@auth_router.get("/me", response_model=UserOut)
def me(user=Depends(get_current_user)):
    return user
