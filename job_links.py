from urllib.parse import quote_plus, urlencode


BOSS_CITY_CODES = {
    "北京": "101010100",
    "上海": "101020100",
    "广州": "101280100",
    "深圳": "101280600",
    "杭州": "101210100",
    "南京": "101190100",
    "苏州": "101190400",
    "成都": "101270100",
    "武汉": "101200100",
    "西安": "101110100",
    "重庆": "101040100",
    "天津": "101030100",
}


def build_search_keywords(target_role: str, city: str) -> list[str]:
    role = target_role.strip()
    area = city.strip()
    base = [
        f"{area} {role} 应届生",
        f"{area} {role} 助理",
        f"{area} {role} 实习",
        f"{area} {role} 校招",
    ]

    related = {
        "软件实施": ["实施工程师", "软件实施顾问", "项目实施助理"],
        "售前技术支持": ["售前工程师助理", "技术支持工程师", "解决方案助理"],
        "产品助理": ["产品经理助理", "需求分析助理", "项目助理"],
        "客户成功": ["客户成功专员", "客户运营", "软件客户服务"],
        "解决方案助理": ["解决方案顾问助理", "售前助理", "方案助理"],
        "AI 工具应用助理": ["AI应用助理", "AI工具运营", "办公自动化助理"],
    }

    for item in related.get(role, []):
        base.append(f"{area} {item}")

    seen = set()
    keywords = []
    for keyword in base:
        cleaned = " ".join(keyword.split())
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            keywords.append(cleaned)
    return keywords[:8]


def build_job_links(target_role: str, city: str) -> list[dict[str, str]]:
    keyword = f"{city.strip()} {target_role.strip()} 应届生".strip()
    encoded_keyword = quote_plus(keyword)
    encoded_city = quote_plus(city.strip())
    boss_city = BOSS_CITY_CODES.get(city.strip(), "100010000")

    return [
        {
            "platform": "BOSS直聘",
            "title": f"{city} {target_role} 岗位搜索",
            "url": f"https://www.zhipin.com/web/geek/job?query={encoded_keyword}&city={boss_city}",
            "reason": "适合看实施、售前、产品助理、客户成功等偏沟通和交付的岗位。",
        },
        {
            "platform": "智联招聘",
            "title": f"{city} {target_role} 招聘搜索",
            "url": f"https://sou.zhaopin.com/?{urlencode({'jl': city.strip(), 'kw': target_role.strip()})}",
            "reason": "适合筛选应届生、助理、实习和校招类岗位。",
        },
        {
            "platform": "前程无忧",
            "title": f"{city} {target_role} 职位搜索",
            "url": f"https://we.51job.com/pc/search?keyword={encoded_keyword}&searchType=2&sortType=0",
            "reason": "适合补充查看传统企业、外包、实施交付类岗位。",
        },
        {
            "platform": "猎聘",
            "title": f"{city} {target_role} 职位搜索",
            "url": f"https://www.liepin.com/zhaopin/?key={encoded_keyword}&dq={encoded_city}",
            "reason": "适合查看岗位要求写得更完整的招聘信息，便于提取 JD。",
        },
        {
            "platform": "Bing 综合搜索",
            "title": f"全网搜索 {city} {target_role} 招聘",
            "url": f"https://www.bing.com/search?q={quote_plus(keyword + ' 招聘')}",
            "reason": "用于补充查找平台外的公司官网、校招页和招聘聚合页。",
        },
    ]
