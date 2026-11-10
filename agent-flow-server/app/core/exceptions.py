# 统一业务异常与错误码
# 业务层通过 raise BizException(...) 抛出，由全局异常处理器统一转为 {code, msg, data} 响应

class ErrorCode:
    """统一错误码。code 同时作为业务状态码返回给前端。"""

    SUCCESS = 0          # 成功
    BAD_REQUEST = 400    # 参数错误 / 通用业务错误
    UNAUTHORIZED = 401   # 未认证 / Token 失效
    FORBIDDEN = 403      # 无权限
    NOT_FOUND = 404      # 资源不存在
    CONFLICT = 409       # 资源冲突（如唯一约束冲突）
    VALIDATION_ERROR = 422  # 请求参数校验失败
    INTERNAL_ERROR = 500 # 服务器内部错误

    # 业务自定义错误码可从这里继续扩展（如 1001、1002 ...）
    # 注意：自定义业务码若不在 400-599 区间，需显式指定 http_status


class BizException(Exception):
    """业务异常：业务逻辑主动抛出的、可预期的错误。

    参数：
        msg:        返回给前端的提示信息
        code:       业务状态码（默认 400）
        http_status:HTTP 状态码（默认取 code，若 code 不在 400-599 区间则默认 400）
    """

    def __init__(
        self,
        msg: str = "业务处理失败",
        code: int = ErrorCode.BAD_REQUEST,
        http_status: int | None = None,
    ) -> None:
        self.code = code
        self.msg = msg
        if http_status is not None:
            self.http_status = http_status
        elif 400 <= code <= 599:
            self.http_status = code
        else:
            self.http_status = ErrorCode.BAD_REQUEST
        super().__init__(msg)






# Rag工作流异常
"""
导入流程自定义异常类

统一错误处理，提供更清晰的错误信息
"""


class ImportProcessError(Exception):
    """导入流程基础异常"""

    def __init__(self, message: str, cause: Exception = None):
        self.cause = cause
        super().__init__(message)

    def __str__(self):
        parts = [super().__str__()]
        if self.cause:
            parts.append(f"(原因: {self.cause})")
        return " ".join(parts)


class ConfigurationError(ImportProcessError):
    """配置错误：环境变量缺失或配置值无效"""
    pass


class FileProcessingError(ImportProcessError):
    """文件处理错误：文件不存在、格式错误、读写失败"""
    pass


class PdfConversionError(FileProcessingError):
    """PDF 转换错误：MinerU 转换失败"""
    pass


class ImageProcessingError(FileProcessingError):
    """图片处理错误：图片总结、上传失败"""
    pass


class DocumentSplitError(ImportProcessError):
    """文档切分错误：切分逻辑异常"""
    pass


class EmbeddingError(ImportProcessError):
    """向量化错误：模型调用失败、向量生成异常"""
    pass


class LLMError(ImportProcessError):
    """LLM 调用错误：API 调用失败、响应解析失败"""
    pass


class StorageError(ImportProcessError):
    """存储错误：数据库操作失败"""
    pass


class MinioError(StorageError):
    """MinIO 存储错误"""
    pass


class ValidationError(ImportProcessError):
    """数据验证错误：输入数据不符合预期"""
    pass
