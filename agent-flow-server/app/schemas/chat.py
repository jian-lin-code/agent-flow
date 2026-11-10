from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# 请求创建对话
class ConversationCreateRequest(BaseModel):
    title: str = "新对话"

# 返回会话
class ConversationResponse(BaseModel):
    uid: str
    title: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

# 修改会话标题
class ConversationUpdateRequest(BaseModel):
    title: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="新的会话标题",
    )

# 删除会话
class ConversationDeleteResponse(BaseModel):
    conversation_uid: str
    deleted: bool

# 返回会话列表
class ConversationListResponse(BaseModel):
    items: list[ConversationResponse]
    total: int


# 消息请求协议
class MessageSendRequest(BaseModel):
    content: str = Field(
        min_length=1,
        max_length=10000,
        description="用户发送的消息",
    )

    action: str | None = Field(
        default=None,
        description="前端业务交互动作",
    )

    selected_task_uid: UUID | None = Field(
        default=None,
        description="用户明确选择的业务任务 UID",
    )

# 消息
class MessageItem(BaseModel):
    uid: str
    role: str
    content: str
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    extra_data: dict | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

# 返回聊天消息列表
class MessageListResponse(BaseModel):
    conversation_uid: str
    items: list[MessageItem]
    total: int


# 会话内业务任务列表（右侧"相关任务"面板）
class ConversationBusinessTaskListResponse(BaseModel):
    conversation_uid: str
    active_business_task_uid: str | None = None
    total: int
    items: list[dict]

# 工作流信息
class RunInfo(BaseModel):
    uid: str
    status: str

# 返回聊天消息
class MessageSendResponse(BaseModel):
    conversation_uid: str
    user_message: MessageItem
    assistant_message: MessageItem | None = None
    run: RunInfo

# 工作流状态查询接口 ---- 响应
class WorkflowRunStatusResponse(BaseModel):
    conversation_uid: str
    run_uid: str
    status: str
    error_message: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    # 本次运行实际使用的模型，供右侧执行面板展示"执行引擎"
    model_name: str | None = None
    # 运行耗时（毫秒），由 started_at / finished_at 计算，未结束时为 None
    duration_ms: int | None = None





