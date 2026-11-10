"""AgentFlow LangGraph 状态定义。"""

from typing import TypedDict, Any

from arq import ArqRedis

from app.agent_graph.schemas.intents import Intent


class AgentState(TypedDict, total=False):
    """AgentFlow 工作流状态。"""

    # 当前登录用户 ID
    user_id: int
    # 当前登录用户角色：employee / admin
    user_role: str

    # ARQ 的 Redis 客户端
    redis: ArqRedis

    # 当前用户消息
    current_message: str

    # 历史对话，格式：
    # [{"role": "user", "content": "..."}, ...]
    history: list[dict[str, str]]

    # 意图识别结果
    intent: Intent

    # 意图节点同步抽取的费用操作。
    # None 表示本轮没有做抽取（走短语短路或合并抽取关闭），
    # 空列表表示抽取过但本条消息没有费用信息。
    extracted_operations: list[dict[str, Any]] | None
    extraction_clarification: str | None # 需要向用户追问的内容；无需追问时返回 null

    # 最终回复
    answer: str
    ui_payload: dict[str, Any] | None

    # 工作流执行信息
    workflow_run_uid: str
    conversation_id: int
    trigger_message_uid: str

    # 内部执行元数据，由节点包装器写入
    _step_id: int

    input_tokens: int # AI回复消耗的输入Token数
    output_tokens: int # AI回复消耗的输出Token数
    total_tokens: int # AI回复消耗的总Token数
    llm_calls: int # 本次工作流实际调用大模型的次数

    # 用户通过前端任务卡片明确选择的任务 UID
    selected_task_uid: str | None
    action: str | None

    # 当前会话中可操作的业务任务
    business_tasks: list[dict[str, Any]]

    # 本轮已经确定的目标任务
    selected_business_task: dict[str, Any] | None

    # 当前会话激活的任务
    active_business_task_uid: str | None

    # 是否需要用户选择任务
    task_selection_required: bool

    business_action_ready: bool # 用于标记业务任务创建后是否需要收集信息
    business_action_notice: str | None  # 任务是否创建

    # 查询类型和参数
    query_type: str | None
    query_params: dict[str, Any] | None

    # 用户上下文绑定在当前会话
    agent_context: dict[str, Any] | None

    # 知识库检索上下文
    knowledge_contexts: list[dict[str, Any]]

    # 知识库检索候选数量
    knowledge_candidate_count: int

    # 重排序后的候选数量
    knowledge_reranked_count: int

    # 知识检索是否成功执行
    knowledge_retrieval_completed: bool

    # 知识库回答引用来源
    knowledge_sources: list[dict[str, Any]]





