ROLE_POOL = [
    "软件实施",
    "售前技术支持",
    "技术支持工程师",
    "产品助理",
    "项目助理",
    "客户成功",
    "解决方案助理",
    "AI 工具应用助理",
    "数据分析助理",
    "测试工程师",
    "运维助理",
    "需求分析助理",
    "运营助理",
    "电商运营助理",
    "新媒体运营",
    "行政助理",
    "人事助理",
    "财务助理",
    "销售助理",
    "商务助理",
    "客服专员",
    "管培生",
    "Java 开发实习",
    "前端开发实习",
    "Python 开发实习",
]


def recommend_roles(answers: dict[str, str]) -> list[dict[str, str | int]]:
    scores = {role: 0 for role in ROLE_POOL}

    direction = answers.get("work_preference", "")
    if direction == "沟通客户、解决问题":
        for role in ["软件实施", "技术支持工程师", "客户成功", "售前技术支持", "客服专员"]:
            scores[role] += 25
    elif direction == "整理需求、做产品文档":
        for role in ["产品助理", "需求分析助理", "项目助理", "解决方案助理"]:
            scores[role] += 25
    elif direction == "写代码、做系统":
        for role in ["Java 开发实习", "前端开发实习", "Python 开发实习", "测试工程师"]:
            scores[role] += 25
    elif direction == "做数据、做表格分析":
        for role in ["数据分析助理", "运营助理", "电商运营助理", "财务助理"]:
            scores[role] += 25
    elif direction == "做内容、活动和账号":
        for role in ["新媒体运营", "运营助理", "电商运营助理", "商务助理"]:
            scores[role] += 25

    coding = answers.get("coding_level", "")
    if coding == "比较弱":
        for role in ["软件实施", "售前技术支持", "产品助理", "客户成功", "项目助理", "运营助理"]:
            scores[role] += 15
        for role in ["Java 开发实习", "前端开发实习", "Python 开发实习"]:
            scores[role] -= 10
    elif coding == "能做课程设计":
        for role in ["软件实施", "测试工程师", "技术支持工程师", "Java 开发实习"]:
            scores[role] += 15
    elif coding == "比较熟练":
        for role in ["Java 开发实习", "前端开发实习", "Python 开发实习", "测试工程师"]:
            scores[role] += 20

    communication = answers.get("communication", "")
    if communication == "愿意经常沟通":
        for role in ["软件实施", "售前技术支持", "客户成功", "销售助理", "商务助理", "客服专员"]:
            scores[role] += 18
    elif communication == "更喜欢少沟通":
        for role in ["测试工程师", "数据分析助理", "运维助理"]:
            scores[role] += 12

    document = answers.get("document", "")
    if document == "能接受大量文档":
        for role in ["产品助理", "项目助理", "需求分析助理", "软件实施", "解决方案助理"]:
            scores[role] += 18

    business_trip = answers.get("business_trip", "")
    if business_trip == "能接受出差":
        for role in ["软件实施", "售前技术支持", "解决方案助理"]:
            scores[role] += 12
    elif business_trip == "不想出差":
        for role in ["运营助理", "新媒体运营", "数据分析助理", "行政助理", "人事助理"]:
            scores[role] += 10

    ai_tools = answers.get("ai_tools", "")
    if ai_tools == "愿意把 AI 当优势":
        for role in ["AI 工具应用助理", "产品助理", "运营助理", "数据分析助理", "解决方案助理"]:
            scores[role] += 20

    major = answers.get("major", "")
    if major in {"软件/计算机/信息管理", "电子信息/自动化"}:
        for role in ["软件实施", "技术支持工程师", "测试工程师", "数据分析助理", "Java 开发实习", "Python 开发实习"]:
            scores[role] += 14
    elif major in {"管理/工商/市场", "文科/语言/传媒"}:
        for role in ["产品助理", "项目助理", "运营助理", "新媒体运营", "人事助理", "行政助理", "商务助理"]:
            scores[role] += 14
    elif major == "财会/金融/经管":
        for role in ["财务助理", "数据分析助理", "运营助理", "商务助理"]:
            scores[role] += 16

    excel = answers.get("excel", "")
    if excel == "比较熟练":
        for role in ["数据分析助理", "运营助理", "财务助理", "客户成功", "项目助理"]:
            scores[role] += 14

    sql = answers.get("sql", "")
    if sql in {"会基础查询", "比较熟练"}:
        for role in ["数据分析助理", "软件实施", "测试工程师", "技术支持工程师"]:
            scores[role] += 16

    pressure = answers.get("pressure", "")
    if pressure == "能接受业绩压力":
        for role in ["销售助理", "商务助理", "客户成功", "售前技术支持"]:
            scores[role] += 12
    elif pressure == "希望压力稳定":
        for role in ["行政助理", "人事助理", "测试工程师", "数据分析助理"]:
            scores[role] += 10

    detail = answers.get("detail", "")
    if detail == "比较细心":
        for role in ["测试工程师", "财务助理", "数据分析助理", "项目助理", "软件实施"]:
            scores[role] += 12

    creativity = answers.get("creativity", "")
    if creativity == "喜欢创意表达":
        for role in ["新媒体运营", "运营助理", "产品助理"]:
            scores[role] += 14

    company_type = answers.get("company_type", "")
    if company_type == "互联网/软件公司":
        for role in ["产品助理", "测试工程师", "软件实施", "数据分析助理", "AI 工具应用助理"]:
            scores[role] += 8
    elif company_type == "传统企业/稳定平台":
        for role in ["行政助理", "人事助理", "财务助理", "项目助理", "管培生"]:
            scores[role] += 8

    internship = answers.get("internship", "")
    if internship == "没有实习":
        for role in ["管培生", "助理类岗位", "运营助理", "项目助理"]:
            if role in scores:
                scores[role] += 8
    elif internship == "有相关实习":
        for role in ["产品助理", "项目助理", "客户成功", "数据分析助理", "测试工程师"]:
            scores[role] += 10

    reasons = {
        "软件实施": "适合软件工程背景、沟通能力尚可、愿意做交付和文档的人。",
        "售前技术支持": "适合懂一点技术、能沟通客户需求、愿意做方案表达的人。",
        "产品助理": "适合喜欢整理需求、写文档、理解业务流程的人。",
        "客户成功": "适合愿意沟通客户、跟进问题、维护客户关系的人。",
        "AI 工具应用助理": "适合会用 AI 工具提升办公、资料整理和业务分析效率的人。",
        "数据分析助理": "适合喜欢 Excel、SQL、数据整理和业务报表的人。",
        "测试工程师": "适合有课程设计基础、愿意细致验证系统功能的人。",
        "项目助理": "适合能做会议纪要、进度跟踪、文档整理和跨部门沟通的人。",
    }

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    return [
        {
            "role": role,
            "score": max(0, score),
            "reason": reasons.get(role, "根据你的问卷选择，该方向具备一定匹配度。"),
        }
        for role, score in ranked[:6]
        if score > 0
    ]
