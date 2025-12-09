"""
认证API（简化版，无需额外依赖）
"""
from fastapi import APIRouter, Depends, HTTPException, status, Header
from pydantic import BaseModel
from datetime import datetime, timedelta
from typing import Optional
import hashlib
import secrets
from loguru import logger

from config import settings

router = APIRouter()

# ============================================
# 数据模型
# ============================================

class UserLogin(BaseModel):
    username: str
    password: str

class UserInfo(BaseModel):
    id: int
    username: str
    name: str
    role: str
    email: str

class Token(BaseModel):
    access_token: str
    token_type: str
    user: UserInfo

# ============================================
# 简单的认证实现（无需外部依赖）
# ============================================

# 活跃Token存储（生产环境应使用Redis）
active_tokens = {}

def hash_password(password: str) -> str:
    """密码哈希"""
    salt = settings.SECRET_KEY
    return hashlib.sha256(f"{password}{salt}".encode()).hexdigest()

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码"""
    return hash_password(plain_password) == hashed_password

def create_access_token(user_id: int, username: str) -> str:
    """创建访问Token"""
    token = secrets.token_urlsafe(32)
    active_tokens[token] = {
        'user_id': user_id,
        'username': username,
        'created_at': datetime.now(),
        'expires_at': datetime.now() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    }
    return token

def verify_token(token: str) -> Optional[dict]:
    """验证Token"""
    token_data = active_tokens.get(token)
    if not token_data:
        return None
    
    if datetime.now() > token_data['expires_at']:
        del active_tokens[token]
        return None
    
    return token_data

# ============================================
# Mock用户数据
# ============================================

MOCK_USERS = {
    'admin': {
        'id': 1,
        'username': 'admin',
        'password_hash': hash_password('admin123'),
        'name': '超级管理员',
        'role': 'super_admin',
        'email': 'admin@example.com'
    },
    'viewer': {
        'id': 2,
        'username': 'viewer',
        'password_hash': hash_password('viewer123'),
        'name': '观摩者',
        'role': 'viewer',
        'email': 'viewer@example.com'
    }
}

# ============================================
# 依赖函数
# ============================================

async def get_current_user(authorization: Optional[str] = Header(None)) -> UserInfo:
    """获取当前用户（从Header中的Token）"""
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供认证信息"
        )
    
    token = authorization.replace('Bearer ', '')
    token_data = verify_token(token)
    
    if not token_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token无效或已过期"
        )
    
    username = token_data['username']
    user = MOCK_USERS.get(username)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在"
        )
    
    return UserInfo(
        id=user['id'],
        username=user['username'],
        name=user['name'],
        role=user['role'],
        email=user['email']
    )

# ============================================
# API端点
# ============================================

@router.post("/login", response_model=Token)
async def login(user_login: UserLogin):
    """
    用户登录
    """
    user = MOCK_USERS.get(user_login.username)
    
    if not user or not verify_password(user_login.password, user['password_hash']):
        logger.warning(f"登录失败: {user_login.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误"
        )
    
    # 创建token
    access_token = create_access_token(user['id'], user['username'])
    
    logger.info(f"✅ 用户登录成功: {user['username']}")
    
    return Token(
        access_token=access_token,
        token_type="bearer",
        user=UserInfo(
            id=user['id'],
            username=user['username'],
            name=user['name'],
            role=user['role'],
            email=user['email']
        )
    )

@router.post("/logout")
async def logout(current_user: UserInfo = Depends(get_current_user)):
    """用户登出"""
    logger.info(f"用户登出: {current_user.username}")
    # 清理token（简化版，不完整）
    return {"code": 200, "message": "登出成功"}

@router.get("/info", response_model=UserInfo)
async def get_user_info(current_user: UserInfo = Depends(get_current_user)):
    """获取当前用户信息"""
    return current_user

@router.post("/change-password")
async def change_password(
    old_password: str,
    new_password: str,
    current_user: UserInfo = Depends(get_current_user)
):
    """修改密码"""
    user = MOCK_USERS.get(current_user.username)
    
    if not verify_password(old_password, user['password_hash']):
        raise HTTPException(status_code=400, detail="原密码错误")
    
    # 更新密码
    user['password_hash'] = hash_password(new_password)
    
    logger.info(f"用户修改密码: {current_user.username}")
    
    return {"code": 200, "message": "密码修改成功"}
