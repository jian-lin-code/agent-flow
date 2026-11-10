"""意图识别节点：使用 LLM 判断用户当前消息的意图。"""


import re
from langchain_core.messages import HumanMessage, SystemMessage
from app.agent_graph.history import build_history_messages
from app.agent_graph.schemas.intents import Intent, IntentResult, BusinessQueryType
from app.agent_graph.prompt_manager import render_prompt
from app.agent_graph.state import AgentState
from app.agent_graph.token_usage import (
    create_usage_callback,
    get_token_usage,
    accumulate_token_usage,
)
from app.core.config import settings
from app.utils.llm import get_llm_model
from app.utils.logger import logger

# ================= 常量定义 =================

# 注入 prompt 的已有明细字段，避免上下文过长。
EXISTING_ITEM_FIELDS = ("id", "category", "amount", "expense_date")
MAX_EXISTING_ITEMS = 10

# 1. 提交确认
CONFIRM_PHRASES = {
    "确认", "确认提交", "确认报销", "确认一下", "确认无误",
    "确定", "确定提交", "确定报销", "确定了",
    "提交", "提交报销", "提交申请", "提交吧", "帮我提交",
    "可以提交", "同意提交", "那就提交", "直接提交", "现在提交",
    "没问题提交", "没问题", "没问题了", "可以", "可以了",
    "行", "行吧", "行提交", "好的提交", "好提交", "好",
    "同意", "同意报销", "批准", "通过",
    "交吧", "就这样提交", "就这样吧", "就这么办", "按这个来",
    "按这个提交", "就这个", "就它了", "没问题按这个来",
}

# 2. 取消操作
CANCEL_PHRASES = {
    "取消", "取消报销", "取消申请", "取消操作", "取消掉",
    "撤销", "撤销报销", "撤销申请", "撤回", "撤回报销",
    "不报了", "不报了取消", "算了不报了", "不弄了", "不办了",
    "终止", "终止报销", "停止", "停止报销", "结束",
    "退出", "退出报销", "放弃", "放弃报销", "放弃申请",
    "算了", "不用了", "不搞了", "先不报了", "暂时不报",
    "取消吧"
}

# 3. 恢复操作
RESUME_PHRASES = {
    "恢复", "恢复报销", "恢复申请", "恢复刚才那个", "恢复之前的",
    "恢复一下", "帮我恢复", "把刚才的报销继续", "把之前的报销继续",
    "继续", "继续报销", "继续申请", "继续办理", "继续刚才的",
    "继续之前那个", "接着办", "接着报销", "接着弄", "接着来",
    "办吧", "继续吧", "接着来吧", "把刚才那个办了", "刚才那个继续",
}

# 4. 拒绝恢复（仅在等待恢复确认状态下生效）
REJECT_RESUME_PHRASES = {
    "不恢复", "不恢复了", "不用恢复", "不要恢复", "别恢复",
    "不继续", "不继续了", "不用继续", "不要继续", "别继续",
    "不办了", "不办了，重新报", "不用了", "不了",
    "重新报", "重新报销", "重新提交", "重新申请",
    "不恢复，重新报", "不恢复重新报", "算了重新报",
    "放弃恢复", "放弃刚才的", "不要刚才那个",
}

# 5. 翻页操作
PAGINATION_PHRASES = {"下一页", "下一张", "上一页", "上一张"}
PAGINATION_PATTERN = re.compile(r"^第[0-9一二三四五六七八九十百]+页$")


# ================= 辅助工具函数 =================

def _normalize_message(message: str) -> str:
    """清理标点符号和空格，方便进行精准短语匹配。"""
    return (
        message.strip()
        .replace("。", "").replace("！", "").replace("!", "")
        .replace("，", "").replace(",", "").replace(" ", "")
    )


def _is_explicit_confirm(message: str) -> bool:
    return _normalize_message(message) in CONFIRM_PHRASES


def _is_explicit_cancel(message: str) -> bool:
    return _normalize_message(message) in CANCEL_PHRASES


def _is_explicit_resume(message: str) -> bool:
    return _normalize_message(message) in RESUME_PHRASES


def _is_explicit_reject_resume(message: str) -> bool:
    return _normalize_message(message) in REJECT_RESUME_PHRASES


def _is_explicit_pagination(message: str) -> bool:
    """判断是否为翻页操作（支持固定词汇和‘第X页’正则）。"""
    clean_msg = _normalize_message(message)
    if clean_msg in PAGINATION_PHRASES:
        return True
    return bool(PAGINATION_PATTERN.match(clean_msg))


# 拒绝恢复的否定信号：只要命中，就说明用户不想恢复
REJECT_RESUME_PATTERNS = (
    r"不恢复", r"不用恢复", r"不要恢复", r"别恢复",
    r"不继续", r"不用继续", r"不要继续", r"别继续",
    r"不办了", r"不弄了", r"先不", r"放弃",
    r"不用了", r"不用啦", r"不需要了",
    r"重新报", r"重新申请", r"重新提交", r"重新发起", r"不要刚才",
    # 「算了」只有在句首/标点后/句尾才是拒绝，避免「计算了下个月预算」误判
    r"(?:^|[，,。.！!？?\s])算了", r"算了[，,。.！!？?]?$",
    r"(?:^|[，,。.！!？?\s])不了", r"不了[，,。.！!？?]?$",
)
REJECT_RESUME_REGEX = re.compile("|".join(REJECT_RESUME_PATTERNS))

# 确认恢复的正向信号
RESUME_SIGNALS = ("恢复", "继续", "接着", "办吧", "来吧")


def _classify_pending_resume(message: str) -> Intent | None:
    """在「等待确认恢复」上下文中判断用户是同意还是拒绝恢复。

    这里改用「否定信号优先 + 关键词包含」的规则兜底，不再依赖精确词表：
    「不用了，先不恢复」「算了不继续了」这类口语化表达都能被接住。
    """
    clean_msg = _normalize_message(message)

    if not clean_msg:
        return None

    # 用户在确认恢复时通常只回一句短话；长消息更可能是新的诉求，
    # 交给后续正常意图识别，避免「计算了下个月预算」被误判成拒绝恢复。
    if len(clean_msg) > 25:
        return None

    if REJECT_RESUME_REGEX.search(clean_msg):
        return Intent.REJECT_RESUME

    if clean_msg in RESUME_PHRASES:
        return Intent.CONFIRM_RESUME

    if any(signal in clean_msg for signal in RESUME_SIGNALS):
        return Intent.CONFIRM_RESUME

    return None

# ================= 业务意图确定性识别 =================

# 明确查询已有业务的表达
BUSINESS_QUERY_PATTERN = re.compile(
    r"报销记录|报销历史|报销详情|"
    r"审批进度|审批状态|审批到哪一步|"
    r"申请状态|处理结果|费用统计|报销统计|"
    r"AI预审|人工审批"
)

# 明确查询制度、政策的表达
KNOWLEDGE_QUERY_PATTERN = re.compile(
    r"报销标准|报销政策|报销制度|"
    r"报销流程|报销需要什么|"
    r"需要哪些材料|能不能报销|"
    r"可以报销吗|是否可以报销|"
    r"怎么报销|如何报销"
)

# 明确要求新建独立业务的表达
NEW_BUSINESS_PATTERN = re.compile(
    r"新建一笔|新开一笔|新的一笔|"
    r"另外.*新建|另外.*新开|"
    r"重新发起|重新发一笔|"
    r"单独.*报销"
)

# 费用类别
EXPENSE_CATEGORY_PATTERN = re.compile(
    r"话费|电话费|通信费|手机|电脑|"
    r"办公用品|餐费|交通费|打车费|住宿费|"
    r"差旅费|招待费|停车费|油费"
)

# 费用金额
AMOUNT_PATTERN = re.compile(
    r"\d+(?:\.\d{1,2})?\s*(?:元|块)"
)

# 实际发生费用的动作
EXPENSE_ACTION_PATTERN = re.compile(
    r"买了|购买了|采购了|支付|交了|交纳|缴纳|"
    r"交|花了|消费了|垫付了|支出了|报销一下|帮我报销"
)


def _is_expense_statement(message: str) -> bool:
    """判断用户是否在描述一笔实际发生的费用。"""

    if BUSINESS_QUERY_PATTERN.search(message):
        return False

    if KNOWLEDGE_QUERY_PATTERN.search(message):
        return False

    return (
        bool(EXPENSE_CATEGORY_PATTERN.search(message))
        and bool(AMOUNT_PATTERN.search(message))
        and bool(EXPENSE_ACTION_PATTERN.search(message))
    )

# ================= 核心节点逻辑 =================

async def classify_intent(state: AgentState) -> dict:
    """意图识别节点。"""

    current_message = state.get("current_message", "").strip()
    if not current_message:
        return {"intent": Intent.UNKNOWN}

    # 1. 提取上下文状态
    agent_context = state.get("agent_context") or {}
    pending_action = agent_context.get("pending_action") or {}
    pending_resume_task_uid = pending_action.get("business_task_uid")
    business_query = agent_context.get("business_query") or {}
    query_type = business_query.get("query_type")
    active_task_uid = state.get("active_business_task_uid")

    # ================= 优先级 1：恢复确认状态拦截 =================
    if pending_resume_task_uid:
        # 该状态下用户的回复几乎都是在回答「是否恢复」，优先用规则判定，
        # 避免口语化的拒绝（如「不用了，先不恢复」）被识别成其他意图。
        resume_decision = _classify_pending_resume(current_message)
        if resume_decision is not None:
            return {"intent": resume_decision}

    # ================= 优先级 2：全局快捷指令拦截 =================
    # 不管是恢复状态还是普通状态，下面这些明确的指令都直接生效

    # 明确恢复
    if _is_explicit_resume(current_message) and not pending_resume_task_uid:
        # 如果没有 pending，用户说恢复，那是去查历史取消记录
        return {"intent": Intent.RESUME_ACTION}

    # 明确取消（有活动任务才允许取消）
    if active_task_uid and _is_explicit_cancel(current_message):
        return {"intent": Intent.CANCEL_ACTION}

    # 明确提交（有活动任务才允许提交）
    if active_task_uid and _is_explicit_confirm(current_message):
        # 注意：如果 pending 状态下来了，上面的 prompt 会告诉 LLM 这是 confirm_resume
        # 但如果用户真的有 active_task_uid，且说了确认，这里优先给提交
        return {"intent": Intent.CONFIRM_ACTION}

    # 翻页操作（必须是在查列表，且命中了翻页指令）
    if query_type == BusinessQueryType.EXPENSE_LIST.value and _is_explicit_pagination(current_message):
        return {"intent": Intent.BUSINESS_QUERY}

    # ================= 确定性业务意图识别 =================

    # 1. 明确要求新建独立业务
    if NEW_BUSINESS_PATTERN.search(current_message):
        logger.info("确定性意图识别：明确发起新业务")
        return {
            "intent": Intent.BUSINESS_ACTION,
            "business_action_ready":True
            }

    # 2. 明确查询已有业务
    if BUSINESS_QUERY_PATTERN.search(current_message):
        logger.info("确定性意图识别：查询已有业务")
        return {"intent": Intent.BUSINESS_QUERY}

    # 3. 明确查询业务知识
    if KNOWLEDGE_QUERY_PATTERN.search(current_message):
        logger.info("确定性意图识别：查询业务知识")
        return {"intent": Intent.KNOWLEDGE_QUERY}

    # 4. 明确描述实际发生的费用
    if _is_expense_statement(current_message):

        if active_task_uid:
            logger.info(
                "确定性意图识别：补充当前业务费用，task_uid=%s",
                active_task_uid,
            )
            return {"intent": Intent.PROVIDE_INFORMATION}

        logger.info("确定性意图识别：发起新的报销业务")
        return {"intent": Intent.BUSINESS_ACTION}

    # ================= 降级：走 LLM 识别 =================

    model_name = settings.LLM_INTENT_MODEL
    usage_callback = create_usage_callback()
    history_messages = build_history_messages(
        state.get("history") or [],
        max_messages=4,
    )
    # 纯意图分类模式：只让模型输出一个标签，不抽取参数
    system_prompt = render_prompt(
        "intent/classify_intent_v2.j2",
        has_pending_task=bool(pending_resume_task_uid),
        has_active_task=bool(active_task_uid),
    )

    messages = [
        SystemMessage(content=system_prompt),
        *history_messages,
        HumanMessage(content=current_message),
    ]

    llm = get_llm_model(model_name=model_name, temp=0)
    structured_llm = llm.with_structured_output(IntentResult)


    response: IntentResult = await structured_llm.ainvoke(
        messages,
        config={"callbacks": [usage_callback]},
    )

    usage = get_token_usage(usage_callback)

    final_intent = response.intent

    # ================= 后置校验：纠正 LLM 的幻觉 =================

    # 1. 没有活动任务，却识别成补充信息 -> 绝对错误
    if final_intent == Intent.PROVIDE_INFORMATION and not active_task_uid:
        logger.warning(
            "LLM 意图误判拦截: 无活动任务却识别为 PROVIDE_INFORMATION，降级为 UNKNOWN。msg=%s",
            current_message
        )
        final_intent = Intent.UNKNOWN

    # 2. 没有活动任务，却识别成确认提交或取消 -> 绝对错误
    if final_intent in {Intent.CONFIRM_ACTION, Intent.CANCEL_ACTION} and not active_task_uid:
        logger.warning("LLM 意图误判拦截: 无活动任务却识别为提交/取消，降级为 UNKNOWN。")
        final_intent = Intent.UNKNOWN

    # 3. 没有等待恢复的任务，却识别成确认/拒绝恢复 -> 绝对错误
    if final_intent in {Intent.CONFIRM_RESUME, Intent.REJECT_RESUME} and not pending_resume_task_uid:
        logger.warning("LLM 意图误判拦截: 无 pending 任务却识别为恢复确认，降级为 UNKNOWN。")
        final_intent = Intent.UNKNOWN

    # =============================================================
    result_data = {
        "intent": final_intent,
        "business_action_ready": response.has_expense_information,
        **accumulate_token_usage(state, usage),

    }

    logger.info(
        "意图识别完成 | model=%s | intent=%s | tokens=%s",
        model_name,
        final_intent.value,
        usage,
    )

    return result_data

