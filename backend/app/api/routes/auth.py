from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func
from typing import Any
import logging

from app.api.routes.schemas import UserCreate, UserResponse, Token, LoginRequest, TokenRefreshRequest
from app.db.session import get_db
from app.db.models.user import User
from app.core import security

router = APIRouter()
logger = logging.getLogger(__name__)


def _normalize_email(email: str) -> str:
    return email.strip().lower()


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(user_in: UserCreate, db: AsyncSession = Depends(get_db)) -> Any:
    try:
        normalized_email = _normalize_email(user_in.email)

        # Check if user already exists
        result = await db.execute(select(User).where(func.lower(User.email) == normalized_email))
        user = result.scalars().first()
        if user:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")
        
        # Create new user
        new_user = User(
            email=normalized_email,
            hashed_password=security.get_password_hash(user_in.password),
            role=user_in.role,
            org_id=user_in.org_id
        )
        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)
        return new_user
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error registering user: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")

@router.post("/login", response_model=Token)
async def login(login_req: LoginRequest, db: AsyncSession = Depends(get_db)) -> Any:
    try:
        normalized_email = _normalize_email(login_req.email)

        # Authenticate user
        result = await db.execute(select(User).where(func.lower(User.email) == normalized_email))
        user = result.scalars().first()
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account not found. Please sign up first.")
        if not security.verify_password(login_req.password, user.hashed_password):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User is inactive")
        
        # Generate tokens
        access_token = security.create_access_token(subject=user.id)
        refresh_token = security.create_refresh_token(subject=user.id)
        return {"access_token": access_token, "refresh_token": refresh_token, "token_type": "bearer"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error logging in user: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")

@router.post("/refresh", response_model=Token)
async def refresh_token(refresh_req: TokenRefreshRequest, db: AsyncSession = Depends(get_db)) -> Any:
    # Minimal logic for now
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Token refresh not fully implemented")

@router.post("/logout")
async def logout():
    return {"message": "Successfully logged out"}
