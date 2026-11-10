# 全局异常处理器：统一将各类异常转为 {code, msg, data} 响应
# 在 main.py 中通过 register_exception_handlers(app) 注册

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import BizException, ErrorCode
from app.core.response import ResponseModel

logger = logging.getLogger("agent_flow")


def register_exception_handlers(app: FastAPI) -> None:
    """注册所有全局异常处理器到 FastAPI 应用。"""

    # 1. 业务异常（预期内错误）：返回其自身的 code / http_status / msg
    @app.exception_handler(BizException)
    async def biz_exception_handler(
        request: Request, exc: BizException
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.http_status,
            content=ResponseModel.error(code=exc.code, msg=exc.msg).model_dump(),
        )

    # 2. 请求参数校验失败：统一 422，并汇总各字段错误信息
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # 提取形如 "body.content: Field required" 的可读错误摘要
        errors = exc.errors()
        details = []
        for e in errors:
            loc = ".".join(str(x) for x in e.get("loc", []))
            details.append(f"{loc}: {e.get('msg', 'invalid')}")
        msg = "请求参数校验失败: " + "; ".join(details) if details else "请求参数校验失败"
        return JSONResponse(
            status_code=ErrorCode.VALIDATION_ERROR,
            content=ResponseModel.error(
                code=ErrorCode.VALIDATION_ERROR, msg=msg
            ).model_dump(),
        )

    # 3. Starlette/FastAPI HTTPException（含 401/403/404 等）：保留状态码与 headers
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=ResponseModel.error(
                code=exc.status_code, msg=str(exc.detail)
            ).model_dump(),
            headers=exc.headers,
        )

    # 4. 兜底：未预期的服务器内部错误，记录日志但不下发内部细节
    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=ErrorCode.INTERNAL_ERROR,
            content=ResponseModel.error(
                code=ErrorCode.INTERNAL_ERROR,
                msg="服务器内部错误",
            ).model_dump(),
        )
