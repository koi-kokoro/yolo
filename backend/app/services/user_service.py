"""
用户服务层

职责：
  - 用户注册、登录、鉴权
  - 用户列表查询（分页）
  - 用户详情查询
  - 更新个人信息（手机号、邮箱）
  - 修改密码
  - 角色列表查询

架构：
  UserService 是无状态的纯服务，被 user.py API 层调用。
  所有数据库查询逻辑和会话管理集中在此层，API 层只负责参数校验和响应格式化。
"""

from hmac import compare_digest
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload

from app.config.settings import settings
from app.core.logger import get_logger
from app.core.security import create_access_token, hash_password, verify_password
from app.database.session import SessionLocal
from app.entity.db_models import Role, User, UserRole

logger = get_logger(__name__)


class UserService:
    """用户服务"""

    @staticmethod
    def register(
        db: Session,
        username: str,
        email: str,
        password: str,
        admin_code: Optional[str] = None,
    ) -> User:
        """
        用户注册

        Args:
            db: 数据库会话
            username: 用户名
            email: 邮箱
            password: 明文密码

        Returns:
            新创建的用户对象

        Raises:
            HTTPException: 管理员代码错误、用户名或邮箱已存在
        """
        requested_admin = bool(admin_code and admin_code.strip())
        if requested_admin and (
            not settings.ADMIN_REGISTRATION_CODE
            or not compare_digest(admin_code.strip(), settings.ADMIN_REGISTRATION_CODE)
        ):
            raise HTTPException(status_code=400, detail="管理员代码错误")

        # Validate the code before any user row is added.
        existing_user = db.query(User).filter(User.username == username).first()
        if existing_user:
            raise HTTPException(status_code=400, detail="用户名已存在")

        existing_email = db.query(User).filter(User.email == email).first()
        if existing_email:
            raise HTTPException(status_code=400, detail="邮箱已被注册")

        new_user = User(
            username=username,
            email=email,
            hashed_password=hash_password(password),
            is_superuser=requested_admin,
        )
        db.add(new_user)
        if requested_admin:
            admin_role = (
                db.query(Role)
                .filter(Role.name.in_(["admin", "administrator", "superuser"]))
                .order_by(Role.id)
                .first()
            )
            if admin_role:
                db.flush()
                db.add(UserRole(user=new_user, role=admin_role))
        db.commit()
        db.refresh(new_user)

        return new_user
        # 移除了 try...finally 中的 db.close()

    @staticmethod
    def login(db: Session, username: str, password: str) -> User:
        """
        用户登录

        Args:
            db: 数据库会话
            username: 用户名
            password: 明文密码

        Returns:
            登录成功的用户对象

        Raises:
            HTTPException: 用户名或密码错误
        """
        # 移除原有的 db = SessionLocal()，直接使用传入的 db
        user = (
            db.query(User)
            .options(joinedload(User.user_roles).joinedload(UserRole.role))
            .filter(User.username == username)
            .first()
        )
        if not user:
            raise HTTPException(status_code=401, detail="用户名不存在")

        if not verify_password(password, user.hashed_password):
            raise HTTPException(status_code=401, detail="密码错误")

        return user

    @staticmethod
    def create_access_token_for_user(user: User) -> str:
        """为用户生成 JWT Token"""
        return create_access_token(data={"sub": str(user.id)})

    @staticmethod
    def get_user_roles(db: Session, user: User) -> list[str]:
        """
        获取用户的角色标识列表

        Args:
            db: 数据库会话
            user: 用户对象
        """
        return [ur.role.name for ur in user.user_roles]

    @staticmethod
    def get_user_by_id(db: Session, user_id: int) -> User:
        """
        根据 ID 获取用户

        Args:
            db: 数据库会话
            user_id: 用户 ID

        Returns:
            用户对象

        Raises:
            HTTPException: 用户不存在
        """
        # 移除原有的 db = SessionLocal() 和 try...finally 中的 db.close()
        # 直接使用传入的 db，生命周期由 FastAPI 的 Depends(get_db) 自动管理
        user = (
            db.query(User)
            .options(joinedload(User.user_roles).joinedload(UserRole.role))
            .filter(User.id == user_id)
            .first()
        )
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")
        return user

    @staticmethod
    def list_users(
        page: int = 1,
        page_size: int = 20,
        keyword: Optional[str] = None,
    ) -> dict:
        """
        获取用户列表（分页）

        Args:
            page: 页码（从 1 开始）
            page_size: 每页数量
            keyword: 用户名/邮箱关键词

        Returns:
            包含分页信息和用户列表的字典
        """
        db = SessionLocal()
        try:
            query = db.query(User)

            if keyword:
                query = query.filter(
                    (User.username.ilike(f"%{keyword}%"))
                    | (User.email.ilike(f"%{keyword}%"))
                )

            total = query.count()
            users = (
                query.order_by(User.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
                .all()
            )

            items = []
            for u in users:
                roles = [ur.role.name for ur in u.user_roles]
                items.append(
                    {
                        "id": u.id,
                        "username": u.username,
                        "email": u.email,
                        "phone": u.phone,
                        "is_active": u.is_active,
                        "is_superuser": u.is_superuser,
                        "roles": roles,
                        "last_login_at": u.last_login_at.isoformat()
                        if u.last_login_at
                        else None,
                        "created_at": u.created_at.isoformat()
                        if u.created_at
                        else None,
                    }
                )

            return {
                "total": total,
                "page": page,
                "page_size": page_size,
                "items": items,
            }
        finally:
            db.close()

    @staticmethod
    def list_roles() -> list:
        """
        获取系统中所有角色列表

        Returns:
            角色列表
        """
        db = SessionLocal()
        try:
            roles = db.query(Role).all()
            return [
                {
                    "id": r.id,
                    "name": r.name,
                    "display_name": r.display_name,
                    "description": r.description,
                    "is_system": r.is_system,
                }
                for r in roles
            ]
        finally:
            db.close()

    @staticmethod
    def update_profile(
        user_id: int, phone: Optional[str] = None, email: Optional[str] = None
    ) -> dict:
        """
        更新用户个人信息（手机号、邮箱）

        Args:
            user_id: 用户 ID
            phone: 手机号（可选）
            email: 邮箱（可选）

        Returns:
            更新后的用户信息

        Raises:
            HTTPException: 用户不存在或邮箱已被使用
        """
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                raise HTTPException(status_code=404, detail="用户不存在")

            if phone is not None:
                user.phone = phone
            if email is not None:
                existing = (
                    db.query(User)
                    .filter(User.email == email, User.id != user_id)
                    .first()
                )
                if existing:
                    raise HTTPException(
                        status_code=400, detail="该邮箱已被其他用户使用"
                    )
                user.email = email

            db.commit()
            db.refresh(user)

            logger.info("用户 %s 更新了个人信息", user.username)

            return {
                "message": "个人信息已更新",
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "phone": user.phone,
                },
            }
        finally:
            db.close()

    @staticmethod
    def change_password(user_id: int, old_password: str, new_password: str) -> dict:
        """
        修改用户密码

        Args:
            user_id: 用户 ID
            old_password: 旧密码
            new_password: 新密码

        Returns:
            操作结果消息

        Raises:
            HTTPException: 用户不存在或旧密码不正确
        """
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                raise HTTPException(status_code=404, detail="用户不存在")

            if not verify_password(old_password, user.hashed_password):
                raise HTTPException(status_code=400, detail="旧密码不正确")

            user.hashed_password = hash_password(new_password)
            db.commit()

            logger.info("用户 %s 修改了密码", user.username)

            return {"message": "密码修改成功"}
        finally:
            db.close()


user_service = UserService()
