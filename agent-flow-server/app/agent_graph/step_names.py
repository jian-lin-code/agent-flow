"""LangGraph 节点展示名称。"""

STEP_DISPLAY_NAMES = {
    # 1. 感知与路由
    "classify_intent": "意图路由分发(Intent Routing)",
    "resolve_business_task": "目标任务解析(Task Resolution)",

    # 2. 上下文与状态
    "load_business_task_context": "会话上下文加载(Context Loading)",

    # 3. 核心执行单元 (Action & Query)
    "handle_business_action": "业务指令执行(Business Execution)",
    "handle_business_query": "业务数据检索(Data Retrieval)",
    # 业务查询分发后的具体查询节点
    "handle_expense_list": "报销记录查询(Expense List)",
    "handle_expense_detail": "报销单详情查询(Expense Detail)",
    "handle_expense_progress": "报销审批进度查询(Expense Progress)",
    "handle_expense_approval_history": "人工审批历史查询(Approval History)",
    "handle_expense_pre_review": "AI 报销初审结果查询(AI Pre-Review)",
    "handle_expense_statistics": "报销统计分析(Expense Statistics)",

    "handle_knowledge_query": "知识图谱检索(Knowledge RAG)",
    "handle_knowledge_answer": "知识增强生成(Knowledge Grounded Answer)",
    "handle_knowledge_no_result": "知识未命中兜底(Knowledge Miss Fallback)",

    # 4. 交互与槽位填补 (Slot Filling)
    "handle_provide_information": "槽位信息抽取(Slot Extraction)",
    "handle_confirm_action": "高危操作确权(Action Confirmation)",
    "handle_cancel_action": "操作中断回滚(Action Rollback)",

    # 5. 状态恢复 (Resume)
    "handle_resume_action": "断点状态恢复(State Resume)",
    "handle_confirm_resume": "恢复意愿确权(Resume Confirmation)",
    "handle_reject_resume": "恢复意愿拒绝(Resume Rejection)",

    # 6. 兜底与响应
    "handle_unknown": "意图澄清兜底(Clarification Fallback)",
    "generate_response": "自然语言合成(NLG Synthesis)"
}


def get_step_display_name(step_name: str) -> str:
    return STEP_DISPLAY_NAMES.get(step_name, step_name)