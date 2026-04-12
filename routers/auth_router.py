from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from auth import create_access_token, check_credentials

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest):
    if not check_credentials(body.username, body.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )
    token = create_access_token(body.username)
    return LoginResponse(access_token=token)


@router.get("/me")
async def me(username: str = None):
    """Lightweight check — actual validation is done client-side."""
    return {"username": username or "authenticated"}
