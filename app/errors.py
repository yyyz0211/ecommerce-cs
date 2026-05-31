"""统一错误码定义 —— 一处定义，全局使用"""

from fastapi import status


class AppError(Exception):
    """应用层异常，由全局处理器统一转为 JSON 响应"""

    def __init__(self, code: str, message: str, http_status: int):
        self.code = code
        self.message = message
        self.http_status = http_status
        super().__init__(message)


# ── 认证 / 用户 ──
INVALID_TOKEN = AppError("INVALID_TOKEN", "无效的令牌", status.HTTP_401_UNAUTHORIZED)
USER_NOT_FOUND = AppError("USER_NOT_FOUND", "用户不存在", status.HTTP_401_UNAUTHORIZED)
WRONG_PASSWORD = AppError("WRONG_PASSWORD", "用户名或密码错误", status.HTTP_401_UNAUTHORIZED)
USERNAME_TAKEN = AppError("USERNAME_TAKEN", "用户名已存在", status.HTTP_409_CONFLICT)

# ── 订单 ──
ORDER_NOT_FOUND = AppError("ORDER_NOT_FOUND", "订单不存在", status.HTTP_404_NOT_FOUND)
ORDER_CANNOT_CANCEL = AppError("ORDER_CANNOT_CANCEL", "", status.HTTP_400_BAD_REQUEST)
LOGISTICS_NOT_FOUND = AppError("LOGISTICS_NOT_FOUND", "暂无物流信息", status.HTTP_404_NOT_FOUND)

# ── 售后 ──
AFTER_SALE_NOT_FOUND = AppError("AFTER_SALE_NOT_FOUND", "售后记录不存在", status.HTTP_404_NOT_FOUND)

# ── 对话 ──
CONVERSATION_NOT_FOUND = AppError("CONVERSATION_NOT_FOUND", "会话不存在", status.HTTP_404_NOT_FOUND)
