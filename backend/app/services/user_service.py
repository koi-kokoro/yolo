"""User service for registration, login and authentication support."""

from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password, verify_password
from app.entity.db_models import User


class UserService:
    """Business logic for users."""

    @staticmethod
    def register(db: Session, username: str, email: str, password: str) -> User:
        """Register a new user."""

        existing_user = db.query(User).filter(User.username == username).first()
        if existing_user:
            raise HTTPException(status_code=400, detail="用户名已存在")

        existing_email = db.query(User).filter(User.email == email).first()
        if existing_email:
            raise HTTPException(status_code=400, detail="邮箱已被注册")

        new_user = User(username=username, email=email, hashed_password=hash_password(password))
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        return new_user

    @staticmethod
    def login(db: Session, username: str, password: str) -> User:
        """Validate username/email and password."""

        user = db.query(User).filter(or_(User.username == username, User.email == username)).first()
        if not user:
            raise HTTPException(status_code=401, detail="无用户")
        if not verify_password(password, user.hashed_password):
            raise HTTPException(status_code=401, detail="密码错误")
        if not user.is_active:
            raise HTTPException(status_code=403, detail="用户已被禁用")

        user.last_login_at = datetime.now()
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def create_access_token_for_user(user: User) -> str:
        """Create a JWT token for a user."""

        return create_access_token(data={"sub": str(user.id)})

    @staticmethod
    def get_user_roles(_db: Session, user: User) -> list[str]:
        """Return user's role names."""

        return [user_role.role.name for user_role in user.user_roles]

    @staticmethod
    def get_user_by_id(db: Session, user_id: int) -> User:
        """Fetch a user by id or raise 404."""

        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")
        return user


user_service = UserService()
