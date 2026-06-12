BASE_HOT_SKILLS = [
    {
        "skill": "AI 工具应用",
        "reason": "能用大模型做资料整理、需求梳理、文档初稿和问题分析，适合实施、售前、产品助理岗位。",
        "keywords": ["AI", "ChatGPT", "Codex", "提示词", "大模型"],
    },
    {
        "skill": "Excel / 表格分析",
        "reason": "实施、客户成功和产品助理经常要整理客户问题、需求清单、测试记录和项目进度。",
        "keywords": ["Excel", "表格", "数据整理", "透视表"],
    },
    {
        "skill": "SQL / 数据库基础",
        "reason": "软件实施和技术支持岗位常见数据查询、数据核对、问题定位场景。",
        "keywords": ["SQL", "MySQL", "数据库", "查询"],
    },
    {
        "skill": "需求分析",
        "reason": "能把客户表达转成需求点、功能点和待办事项，是实施、售前、产品助理的共同能力。",
        "keywords": ["需求", "需求分析", "用户故事", "功能"],
    },
    {
        "skill": "项目文档写作",
        "reason": "培训手册、会议纪要、实施记录、需求文档和验收材料都是入门岗位高频任务。",
        "keywords": ["文档", "会议纪要", "培训手册", "需求文档", "验收"],
    },
    {
        "skill": "客户沟通与问题跟进",
        "reason": "偏交付和支持类岗位很看重沟通、记录、反馈和闭环能力。",
        "keywords": ["沟通", "客户", "跟进", "反馈", "协作"],
    },
]


ROLE_SKILLS = {
    "软件实施": ["SQL / 数据库基础", "项目文档写作", "客户沟通与问题跟进", "需求分析", "AI 工具应用"],
    "售前技术支持": ["需求分析", "项目文档写作", "客户沟通与问题跟进", "AI 工具应用", "Excel / 表格分析"],
    "产品助理": ["需求分析", "Excel / 表格分析", "项目文档写作", "AI 工具应用", "客户沟通与问题跟进"],
    "客户成功": ["客户沟通与问题跟进", "Excel / 表格分析", "项目文档写作", "AI 工具应用", "需求分析"],
    "解决方案助理": ["需求分析", "项目文档写作", "客户沟通与问题跟进", "AI 工具应用", "SQL / 数据库基础"],
    "AI 工具应用助理": ["AI 工具应用", "Excel / 表格分析", "需求分析", "项目文档写作", "客户沟通与问题跟进"],
}


def recommend_hot_skills(target_role: str, resume_text: str) -> list[dict[str, str]]:
    wanted = ROLE_SKILLS.get(target_role, [item["skill"] for item in BASE_HOT_SKILLS])
    skill_map = {item["skill"]: item for item in BASE_HOT_SKILLS}
    resume_lower = resume_text.lower()
    results = []

    for skill in wanted:
        item = skill_map[skill]
        matched = any(keyword.lower() in resume_lower for keyword in item["keywords"])
        results.append(
            {
                "skill": item["skill"],
                "reason": item["reason"],
                "status": "简历已体现" if matched else "建议补充",
            }
        )
    return results
