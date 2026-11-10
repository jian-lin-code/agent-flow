"""AgentFlow LangGraph 工作流。"""

from langgraph.graph import END, START, StateGraph

from app.agent_graph.nodes.knowledge_query.knowledge_answer import handle_knowledge_answer, handle_knowledge_no_result
from app.agent_graph.nodes.small_talk import handle_small_talk
from app.agent_graph.state import AgentState
from app.agent_graph.step_tracker import with_step_tracking
from app.utils.logger import logger
from app.agent_graph.schemas.intents import Intent, BusinessQueryType
# 意图识别
from app.agent_graph.nodes.classify_intent import classify_intent
# 生成回复
# 加载用户上下文
from app.agent_graph.nodes.load_business_task_context import load_business_task_context
# 确定目标业务
from app.agent_graph.nodes.resolve_business_task import resolve_business_task
# 报销业务相关
from app.agent_graph.nodes.expense.business_action import handle_business_action
from app.agent_graph.nodes.expense.provide_information import handle_provide_information
from app.agent_graph.nodes.expense.confirm_action import handle_confirm_action
from app.agent_graph.nodes.expense.confirm_resume import handle_confirm_resume
from app.agent_graph.nodes.expense.reject_resume import handle_reject_resume
from app.agent_graph.nodes.expense.cancel_action import handle_cancel_action
from app.agent_graph.nodes.expense.resume_action import (
    handle_resume_action,
    handle_select_resume_task,
)
# 业务查询相关
from app.agent_graph.nodes.business_query.handle_business_query import handle_business_query
from app.agent_graph.nodes.business_query.expense_list import handle_expense_list
from app.agent_graph.nodes.business_query.expense_detail import handle_expense_detail
from app.agent_graph.nodes.business_query.expense_progress import handle_expense_progress
from app.agent_graph.nodes.business_query.expense_approval_history import handle_expense_approval_history
from app.agent_graph.nodes.business_query.expense_pre_review import handle_expense_pre_review
from app.agent_graph.nodes.business_query.expense_statistics import handle_expense_statistics
# 知识库检索相关
from app.agent_graph.nodes.knowledge_query.knowledge_retrieval import handle_knowledge_query
from app.agent_graph.nodes.unknown import handle_unknown







# 意图 ---> 节点
INTENT_NODE_MAPPING = {
    Intent.BUSINESS_ACTION: "handle_business_action",
    Intent.BUSINESS_QUERY: "handle_business_query",
    Intent.KNOWLEDGE_QUERY: "handle_knowledge_query",
    Intent.PROVIDE_INFORMATION: "resolve_business_task",
    Intent.CONFIRM_ACTION: "resolve_business_task",
    Intent.CANCEL_ACTION: "resolve_business_task",
    Intent.RESUME_ACTION: "handle_resume_action",
    Intent.CONFIRM_RESUME: "handle_confirm_resume",
    Intent.REJECT_RESUME: "handle_reject_resume",
    Intent.SMALL_TALK: "handle_small_talk",
    Intent.UNKNOWN: "handle_unknown",
}

# 业务查询类型 ---> 节点
BUSINESS_QUERY_NODE_MAPPING = {
    BusinessQueryType.EXPENSE_LIST.value: "handle_expense_list",
    BusinessQueryType.EXPENSE_DETAIL.value: "handle_expense_detail",
    BusinessQueryType.EXPENSE_PROGRESS.value: "handle_expense_progress",
    BusinessQueryType.EXPENSE_APPROVAL_HISTORY.value: "handle_expense_approval_history",
    BusinessQueryType.EXPENSE_PRE_REVIEW.value: "handle_expense_pre_review",
    BusinessQueryType.EXPENSE_STATISTICS.value: "handle_expense_statistics",
}

# 节点 ---> 方法
NODE_FUNCTIONS = {
    # 报销业务相关
    "handle_business_action": handle_business_action,
    "handle_provide_information": handle_provide_information,
    "handle_confirm_action": handle_confirm_action,
    "handle_cancel_action": handle_cancel_action,
    "handle_resume_action": handle_resume_action,
    "handle_select_resume_task": handle_select_resume_task,
    "handle_confirm_resume": handle_confirm_resume,
    "handle_reject_resume": handle_reject_resume,
    "handle_small_talk": handle_small_talk,
    "handle_unknown": handle_unknown,

    # 业务查询子节点
    "handle_business_query": handle_business_query,
    "handle_expense_list": handle_expense_list,
    "handle_expense_detail": handle_expense_detail,
    "handle_expense_progress": handle_expense_progress,
    "handle_expense_approval_history": handle_expense_approval_history,
    "handle_expense_pre_review": handle_expense_pre_review,
    "handle_expense_statistics": handle_expense_statistics,

    # 知识库检索
    "handle_knowledge_query": handle_knowledge_query,
    "handle_knowledge_answer": handle_knowledge_answer,
    "handle_knowledge_no_result": handle_knowledge_no_result,

}


def route_by_intent(state: AgentState) -> str:
    """根据识别出的意图决定后续执行路径。"""

    intent = state.get("intent", Intent.UNKNOWN)

    logger.info(f'intent：{intent}')

    if isinstance(intent, str):
        try:
            intent = Intent(intent)
        except ValueError:
            intent = Intent.UNKNOWN

    return INTENT_NODE_MAPPING.get(
        intent,
        INTENT_NODE_MAPPING[Intent.UNKNOWN],
    )


def route_after_task_resolution(state: AgentState) -> str:
    """任务解析后，决定继续执行还是直接结束。"""
    # 显式选择任务只负责建立当前轮次的任务上下文，
    # 不应该继续进入补充信息、确认或取消节点。
    if state.get("action") == "select_business_task":
        return END

    if state.get("task_selection_required"): # 任务无法确定 让用户选择
        return END

    if state.get("answer"):
        return END

    intent = state.get("intent", Intent.UNKNOWN)

    if isinstance(intent, str):
        try:
            intent = Intent(intent)
        except ValueError:
            intent = Intent.UNKNOWN

    return {
        Intent.PROVIDE_INFORMATION: "handle_provide_information",
        Intent.CONFIRM_ACTION: "handle_confirm_action",
        Intent.CANCEL_ACTION: "handle_cancel_action",
    }.get(intent, END)


def build_agent_graph():
    """创建并编译 AgentFlow 工作流。"""

    graph = StateGraph(AgentState)

    graph.add_node(
        "load_business_task_context",
        with_step_tracking("load_business_task_context",load_business_task_context),
    )

    graph.add_node(
        "classify_intent",
        with_step_tracking("classify_intent", classify_intent),
    )

    graph.add_node(
        "resolve_business_task",
        with_step_tracking(
            "resolve_business_task",
            resolve_business_task,
        ),
    )

    for node_name, node_func in NODE_FUNCTIONS.items():
        graph.add_node(
            node_name,
            with_step_tracking(node_name, node_func),
        )

    graph.add_edge(START, "load_business_task_context")

    def route_after_task_context(state: AgentState) -> str:
        """加载业务任务上下文后，根据显式 action 决定路由。"""
        action = state.get("action")

        # 用户显式选择已有业务任务。
        if action == "select_business_task":
            return "resolve_business_task"

        # 用户显式选择要恢复的已取消任务。
        # 这是前端业务动作，不需要经过 LLM 意图识别。
        if action == "select_resume_task":
            return "handle_select_resume_task"

        return "classify_intent"

    graph.add_conditional_edges(
        "load_business_task_context",
        route_after_task_context,
        {
            "resolve_business_task": "resolve_business_task",
            "handle_select_resume_task": "handle_select_resume_task",
            "classify_intent": "classify_intent",
        },
    )

    graph.add_conditional_edges(
        "classify_intent",
        route_by_intent,
        {
            **{
                node_name: node_name
                for node_name in NODE_FUNCTIONS
            },
            "resolve_business_task": "resolve_business_task",
        },
    )

    graph.add_conditional_edges(
        "resolve_business_task",
        route_after_task_resolution,
        {
            END: END,
            "handle_provide_information": "handle_provide_information",
            "handle_confirm_action": "handle_confirm_action",
            "handle_cancel_action": "handle_cancel_action",
        },
    )

    def route_after_business_action(state: AgentState) -> str:
        """报销任务创建成功后，继续提取费用信息。"""
        if state.get("business_action_ready"):
            return "handle_provide_information"

        return END

    graph.add_conditional_edges(
        "handle_business_action",
        route_after_business_action,
        {
            "handle_provide_information": "handle_provide_information",
            END: END,
        },
    )

    for node_name in NODE_FUNCTIONS:
        if node_name not in {
            "handle_business_action",
            "handle_business_query",
            "handle_knowledge_query",
        }:
            graph.add_edge(node_name, END)

    def route_business_query(state: AgentState) -> str:
        """根据业务查询类型决定业务查询节点。"""

        # 入口节点已经生成错误提示，直接结束
        if state.get("answer"):
            return END

        query_type = state.get("query_type")

        if isinstance(query_type, BusinessQueryType):
            query_type = query_type.value

        return BUSINESS_QUERY_NODE_MAPPING.get(query_type, END)

    graph.add_conditional_edges(
        "handle_business_query",
        route_business_query,
        {
            **{
                node_name: node_name
                for node_name in BUSINESS_QUERY_NODE_MAPPING.values()
            },
            END: END,
        },
    )

    # 根据知识库检索结果决定下一步执行的节点
    def route_after_knowledge_retrieval(state: AgentState) -> str:
        """根据是否检索到有效知识上下文选择回答分支。"""
        knowledge_contexts = state.get("knowledge_contexts") or []

        if knowledge_contexts:
            return "handle_knowledge_answer"

        return "handle_knowledge_no_result"

    graph.add_conditional_edges(
        "handle_knowledge_query",
        route_after_knowledge_retrieval,
        {
            "handle_knowledge_answer": "handle_knowledge_answer",
            "handle_knowledge_no_result": "handle_knowledge_no_result",
        },
    )

    return graph.compile()