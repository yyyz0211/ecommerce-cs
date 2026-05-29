"""用户相关 Pydantic 模型：请求与响应"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# --- 注册 ---

class UserRegisterRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=50, description="用户名")
    password: str = Field(..., min_length=6, max_length=128, description="密码")
    phone: Optional[str] = Field(None, max_length=20)


class UserRegisterResponse(BaseModel):
    id: int
    username: str

    model_config = {"from_attributes": True}


# --- 登录 ---

class UserLoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# --- 修改个人信息 ---

class UserUpdateRequest(BaseModel):
    phone: Optional[str] = Field(None, max_length=20, description="手机号")
    default_address: Optional[str] = Field(None, max_length=255, description="默认收货地址")


# --- 用户信息 ---

class UserInfoResponse(BaseModel):
    id: int
    username: str
    phone: Optional[str] = None
    default_address: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}
