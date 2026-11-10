# 全局统一响应格式
# 通过自定义 APIRoute，把每个接口的业务返回值自动包装成 {code, msg, data}
# 成功：统一包装为 {code:0, msg:"success", data:...}
# 异常：不再在此捕获，统一交由 core/handlers.py 注册的全局异常处理器处理

import json
from typing import Any, Callable, Awaitable, TypeVar, Generic, Optional
from fastapi.routing import APIRoute
from pydantic import BaseModel
from starlette.requests import Request
from starlette.responses import Response, JSONResponse

# 定义一个泛型变量，代表 data 的类型
T = TypeVar("T")

class ResponseModel(BaseModel, Generic[T]):
    code: int = 0           # 业务状态码，0 表示成功
    msg: str = "success"      # 提示信息
    data: Optional[T] = None  # 实际数据，可能是单个对象、列表，也可能是 None

    @classmethod
    def success(cls, data: T = None, msg: str = "success") -> "ResponseModel[T]":
        """成功时的快捷返回"""
        return cls(code=0, msg=msg, data=data)

    @classmethod
    def error(cls, code: int = 400, msg: str = "error") -> "ResponseModel[T]":
        """失败时的快捷返回"""
        return cls(code=code, msg=msg, data=None)

class UnifiedResponseRoute(APIRoute):
    """自定义路由类：统一包装成功响应（异常交给全局处理器）"""

    def get_route_handler(self) -> Callable[[Request], Awaitable[Response]]:
        original_route_handler = super().get_route_handler()

        async def custom_route_handler(request: Request) -> Response:
            # 执行原始接口逻辑，拿到已序列化的 Response 对象
            # 若接口抛异常，会向上传递给全局异常处理器（core/handlers.py）
            response = await original_route_handler(request)

            # FastAPI 已经把业务返回值序列化到 response.body 里（JSON 字符串）
            # 反序列化拿回原始业务数据，再统一包装
            try:
                body_bytes = response.body
                payload = json.loads(body_bytes) if body_bytes else None
            except Exception:  # noqa: BLE001
                # 无法解析 body（如非 JSON 响应），原样透传
                return response

            # 统一包装成 {code, msg, data}
            wrapped = JSONResponse(
                status_code=200,
                content=ResponseModel.success(payload).model_dump(),
            )
            # 关键修复：把原始响应携带的 BackgroundTasks 转移到新包装响应上，
            # 否则 add_task 注册的后台任务（如 process_document）永远不会执行。
            # Starlette 在响应发送后通过 response.background 触发后台任务。
            wrapped.background = response.background
            return wrapped

        return custom_route_handler
