"""
用户与权限查询 API 路由

接口列表：
  - GET  /api/user/list        用户列表（管理员/对话查询）
  - GET  /api/user/{user_id}   用户详情
  - PUT  /api/user/profile     更新个人信息
  - PUT  /api/user/password    修改密码
  - GET  /api/user/roles       获取所有角色列表
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.api.auth import get_current_user
from app.core.logger import get_logger
from app.services.user_service import user_service

logger = get_logger(__name__)

router = APIRouter(prefix="/api/user", tags=["用户管理"])


@router.get("/list", summary="用户列表")
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: Optional[str] = Query(None, description="用户名/邮箱关键词"),
    _current_user=Depends(get_current_user),
):
    """
    获取用户列表（分页）

    可在对话中通过 Agent Tool 调用此接口回答"有哪些用户"
    """
    return user_service.list_users(page=page, page_size=page_size, keyword=keyword)


@router.get("/roles", summary="获取所有角色")
async def list_roles(
    _current_user=Depends(get_current_user),
):
    """获取系统中所有角色列表"""
    roles = user_service.list_roles()
    return {"roles": roles}


@router.put("/profile", summary="更新个人信息")
async def update_profile(
    phone: Optional[str] = None,
    email: Optional[str] = None,
    current_user=Depends(get_current_user),
):
    """更新当前用户的个人信息（手机号、邮箱）"""
    return user_service.update_profile(
        user_id=current_user.id, phone=phone, email=email
    )


@router.put("/password", summary="修改密码")
async def change_password(
    old_password: str,
    new_password: str,
    current_user=Depends(get_current_user),
):
    """修改当前用户的密码"""
    return user_service.change_password(
        user_id=current_user.id,
        old_password=old_password,
        new_password=new_password,
    )
