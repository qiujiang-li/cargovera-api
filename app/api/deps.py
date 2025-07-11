from fastapi import Depends, HTTPException, status, Request, Header
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.core.security import decode_access_token
from app.crud.user import get_user_by_email
from app.models.user import User

async def get_token_from_cookie_or_header(
    request: Request,
    authorization: str = Header(None),
) -> str:
    token = request.cookies.get("access_token")
    if not token and authorization and authorization.startswith("Bearer "):
        token = authorization[len("Bearer "):]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return token

async def get_current_user(token: str =Depends(get_token_from_cookie_or_header), db: AsyncSession = Depends(get_db)) -> User:
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = await db.get(User, payload.get("user_id"))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

async def get_current_admin(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )
    return current_user