from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from app.schemas.auth import Token, LoginRequest, RegisterRequest,ForgotPasswordRequest, ResetPasswordRequest
from app.core.security import create_access_token, hash_password
from app.core.email_token import generate_reset_token, verify_reset_token, generate_email_token, verify_email_token
from app.core.email import send_email
from app.core.config import settings
from app.crud.user import authenticate_user, get_user_by_email
from app.models.user import User
from sqlalchemy import select
from app.db.session import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_current_user
import uuid
from app.schemas.user import UserMeSchema
import logging
logger = logging.getLogger("auth")
router = APIRouter()

@router.post("/login", response_model=Token)
async def login(request: LoginRequest, db: AsyncSession = Depends(get_db)):
    logger.info(f"Login request received for {request.email}")
    user = await authenticate_user(db, request.email, request.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.is_email_verified:
        logger.warning(f"Email not verified for {request.email}")
        token = generate_email_token(user.email)
        verification_link = f"{settings.app_name}/auth/verify?token={token}"

        send_email(
            to_email=user.email,
            subject="Verify your email",
            body=f"Click this link to verify your email: {verification_link}"
        ) 
        raise HTTPException(status_code=403, detail="Email not verified. A new verification link has been sent to your inbox.")
    
    if not user.is_active:
        logger.warning(f"Account not active for {request.email}")
        raise HTTPException(status_code=403, detail="Account is not active")
    
    token = create_access_token({
        "user_id": str(user.id),
        "name": user.name,
        "role": "admin" if user.is_admin else "user",
        "email": user.email,
    })
    response = JSONResponse(content={"message": "Login successful"})
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=False,  # True if HTTPS
        samesite="lax",
        max_age=60 * 60 * 24,
    )
    logger.info(f"Login successful for {user.id} {request.email}")
    return response

@router.post("/get-token", response_model=Token)
async def login(request: LoginRequest, db: AsyncSession = Depends(get_db)):
    logger.info(f"API User Get token request received for {request.email}")
    user = await authenticate_user(db, request.email, request.password)
    if not user:
        logger.warning(f"Invalid credentials for {request.email}")
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.is_email_verified:
        logger.warning(f"Email not verified for {request.email}")
        token = generate_email_token(user.email)
        verification_link = f"{settings.app_name}/auth/verify?token={token}"

        send_email(
            to_email=user.email,
            subject="Verify your email",
            body=f"Click this link to verify your email: {verification_link}"
        ) 
        raise HTTPException(status_code=403, detail="Email not verified. A new verification link has been sent to your inbox.")
    
    if not user.is_active:
        logger.warning(f"Account not active for {request.email}")
        raise HTTPException(status_code=403, detail="Account is not active")
    
    token = create_access_token({
        "user_id": str(user.id),
        "name": user.name,
        "role": "admin" if user.is_admin else "user",
        "email": user.email,
    })  
    logger.info(f"API User Get token request successful for {request.email}")
    return {"access_token": token}

@router.post("/logout")
async def logout(current_user: User = Depends(get_current_user)):
    logger.info(f"Logout request received for user {current_user.id}")
    response = JSONResponse(content={"message": "Logged out"})
    response.delete_cookie("access_token")
    logger.info(f"Logout request successful for user {current_user.id}")
    return response


@router.post("/register")
async def register(request: RegisterRequest, db: AsyncSession = Depends(get_db)):
    logger.info(f"Register request received for {request.email}")
    existing = await get_user_by_email(db, request.email)
    if existing:
        logger.warning(f"Email already registered for {request.email}")
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(id=uuid.uuid4(), email=request.email, password_hash=hash_password(request.password), name=request.name, phone=request.phone)
    db.add(user)
    await db.commit()
    token = generate_email_token(user.email)
    verification_link = f"{settings.app_name}/auth/verify?token={token}"

    send_email(
        to_email=user.email,
        subject="Verify your email",
        body=f"Click this link to verify your email: {verification_link}"
    ) 

    return {"message":"Please check your email for verification"}

@router.get("/me", response_model=UserMeSchema)
async def read_user_me(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # await db.refresh(current_user)
    # user = UserSchema.from_orm(current_user)
    # return user
    stmt = select(User).where(User.id == current_user.id)
    result = await db.execute(stmt)
    fresh_user = result.scalar_one()
    return UserMeSchema.from_orm(fresh_user)

@router.get("/verify")
async def verify_email(token: str, db: AsyncSession = Depends(get_db)):
    logger.info(f"Verify email request received")
    try:
        email = verify_email_token(token)
        logger.info(f"Verify email request successful for {email}")
    except Exception:
        logger.warning(f"Invalid or expired token")
        raise HTTPException(status_code=400, detail="Invalid or expired token")

    user = await get_user_by_email(db, email)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.is_email_verified:
        return {"message": "Email already verified"}

    user.is_email_verified = True
    await db.commit()
    logger.info(f"Verify email request successful for {email}")
    return {"message": "Email verified successfully"}


@router.post("/forgot-password")
async def forgot_password(request: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    logger.info(f"Forgot password request received for {request.email}")
    user = await get_user_by_email(db, request.email)
    if user:
        logger.info(f"Forgot password request successful for {request.email}")
        token = generate_reset_token(user.email)
        reset_link = f"{settings.app_name}/reset-password?token={token}"
        # TODO: Implement send_email() for real
        logger.debug(f"[DEV MODE] Send this reset link to user: {reset_link}")
        send_email(user.email, "[theshipbuddy] reset your password", reset_link)
    return {"message": "If your email is registered, you will receive a reset link."}

@router.post("/reset-password")
async def reset_password(payload: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    logger.info(f"Reset password request received for {payload.email}")
    try:
        email = verify_reset_token(payload.token)
        logger.info(f"Reset password request successful for {payload.email}")
    except Exception:
        logger.warning(f"Invalid or expired token")
        raise HTTPException(status_code=400, detail="Invalid or expired token")

    user = await get_user_by_email(db, email)
    if not user:
        logger.warning(f"User not found for {request.email}")
        raise HTTPException(status_code=404, detail="User not found")

    user.password_hash = hash_password(payload.new_password)
    await db.commit()
    logger.info(f"Reset password request successful for {payload.email}")
    return {"message": "Password has been reset successfully."}

