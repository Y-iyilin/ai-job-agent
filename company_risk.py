from __future__ import annotations

import re
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0 Safari/537.36"
    )
}

POSITIVE_WORDS = [
    "官网",
    "融资",
    "上市",
    "高新技术企业",
    "专精特新",
    "社保",
    "五险一金",
    "成立多年",
    "年终奖",
    "双休",
    "周末双休",
    "弹性工作",
    "带薪年假",
    "专业培训",
    "员工旅游",
    "绩效奖金",
    "民营50-150人",
    "民营150-500人",
    "上市公司",
    "国企",
    "外资",
]

RISK_WORDS = [
    "诈骗",
    "骗子",
    "跑路",
    "传销",
    "培训贷",
    "收费培训",
    "押金",
    "保证金",
    "拖欠工资",
    "欠薪",
    "仲裁",
    "劳动纠纷",
    "失信",
    "被执行人",
    "经营异常",
    "严重违法",
    "虚假招聘",
    "黑名单",
    "投诉",
    "避雷",
    "加班严重",
    "无社保",
    "不缴社保",
    "单休",
    "大小周",
    "工资低",
    "试用期不给工资",
    "高薪诱导",
    "无底薪",
    "纯提成",
]

OFFICIAL_WORDS = ["国家企业信用信息公示系统", "企查查", "天眼查", "爱企查", "启信宝", "官网", "工商"]
TREATMENT_GOOD_WORDS = ["五险一金", "双休", "周末双休", "年终奖", "带薪年假", "餐饮补贴", "交通补贴", "通讯补贴", "专业培训", "员工旅游", "绩效奖金"]
TREATMENT_BAD_WORDS = ["单休", "大小周", "无社保", "不缴社保", "押金", "保证金", "培训贷", "无底薪", "纯提成", "试用期不给工资"]
JOB_TRUST_WORDS = ["直招", "全职", "经验", "学历", "岗位职责", "任职要求", "薪资", "地址", "公司规模", "招聘"]
JOB_VAGUE_WORDS = ["轻松月入", "日结", "兼职刷单", "无需经验高薪", "名额有限", "先交费", "包过", "保录取"]
ORG_SUFFIX_PATTERN = r"股份有限公司|有限责任公司|有限公司|集团|公司|科技|信息技术|网络技术|数字技术|软件|电子商务|杭州|上海|北京|深圳|广州|南京|苏州|成都|武汉|中国"
GENERIC_COMPANY_TERMS = {"某某", "测试", "企业", "公司", "招聘", "科技", "信息", "技术", "网络", "数字", "杭州", "上海", "北京", "深圳", "广州", "中国"}


def _clean_text(text: str, max_len: int = 1200) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    return text[:max_len]


def _company_core_terms(company_name: str) -> list[str]:
    normalized = re.sub(r"[（(].*?[）)]", "", company_name or "")
    candidates = [normalized.strip()]
    core = re.sub(ORG_SUFFIX_PATTERN, "", normalized)
    if core.strip():
        candidates.append(core.strip())
    words = re.findall(r"[\u4e00-\u9fffA-Za-z0-9]{2,}", normalized)
    candidates.extend(word for word in words if word not in {"有限", "责任", "股份", *GENERIC_COMPANY_TERMS})
    unique = []
    for item in candidates:
        item = item.strip()
        if len(item) >= 2 and item not in GENERIC_COMPANY_TERMS and item not in unique:
            unique.append(item)
    return unique[:5]


def _is_relevant_result(company_name: str, item: dict[str, str]) -> bool:
    text = f"{item.get('title', '')} {item.get('snippet', '')} {item.get('url', '')}".lower()
    terms = _company_core_terms(company_name)
    if not terms:
        return True
    for term in terms:
        if term.lower() in text:
            return True
    return False


def _search_web(query: str, limit: int = 6) -> list[dict[str, str]]:
    url = f"https://www.bing.com/search?q={quote_plus(query)}"
    response = requests.get(url, headers=HEADERS, timeout=12)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    results = []
    for item in soup.select("li.b_algo"):
        link = item.select_one("h2 a")
        if not link or not link.get("href"):
            continue
        snippet_node = item.select_one(".b_caption p")
        results.append(
            {
                "title": _clean_text(link.get_text(" ", strip=True), 120),
                "url": link["href"],
                "snippet": _clean_text(snippet_node.get_text(" ", strip=True), 260) if snippet_node else "",
            }
        )
        if len(results) >= limit:
            break
    return results


def _risk_level(score: int) -> str:
    if score >= 80:
        return "低风险"
    if score >= 60:
        return "中等风险"
    return "高风险"


def _source_weight(url: str, title: str) -> int:
    text = f"{url} {title}".lower()
    source_scores = {
        "gsxt.gov.cn": 14,
        "qcc.com": 10,
        "tianyancha.com": 10,
        "aiqicha.baidu.com": 9,
        "qixin.com": 8,
        "zhipin.com": 5,
        "51job.com": 5,
        "liepin.com": 5,
        "lagou.com": 4,
        "linkedin.com": 4,
        "kanzhun.com": 4,
        "maimai.cn": 4,
        "1688.com": 6,
        "alibaba.com": 6,
        "hikvision.com": 6,
        "zhihu.com": 3,
        "blacklist": -8,
    }
    for key, value in source_scores.items():
        if key in text:
            return value
    if any(word in text for word in ["投诉", "避雷", "诈骗", "欠薪", "失信", "被执行人"]):
        return -6
    return 1


def _company_name_signal(company_name: str) -> tuple[int, list[str], list[str]]:
    risks = []
    positives = []
    score = 0
    if re.search(r"有限公司|股份有限公司|集团|有限责任公司|合伙企业", company_name):
        score += 4
        positives.append("企业名称包含较完整的组织形式")
    else:
        score -= 4
        risks.append("企业名称不够完整，建议用营业执照全称复查")
    if len(company_name) <= 4:
        score -= 5
        risks.append("企业名称过短，搜索结果容易混杂")
    return score, risks, positives


def _score_company(company_name: str, results: list[dict[str, str]], job_detail: str = "") -> tuple[int, list[str], list[str], list[str], dict[str, int]]:
    score = 58
    risks = []
    positives = []
    dimensions = []
    breakdown = {
        "工商可信度": 12,
        "负面舆情": 20,
        "待遇信号": 12,
        "公开信息": 8,
        "岗位可信度": 8,
    }
    joined_text = " ".join(
        f"{item.get('title', '')} {item.get('snippet', '')}"
        for item in results
    )
    full_text = f"{joined_text} {job_detail}"

    if not company_name.strip():
        return 0, ["未填写企业名称"], [], ["企业名称缺失"], {key: 0 for key in breakdown}

    relevant_items = [item for item in results if _is_relevant_result(company_name, item)]
    relevant_count = len(relevant_items)
    relevance_text = " ".join(
        f"{item.get('title', '')} {item.get('snippet', '')}"
        for item in relevant_items
    )
    name_score, name_risks, name_positives = _company_name_signal(company_name)
    score += name_score
    risks.extend(name_risks)
    positives.extend(name_positives)

    official_base_text = relevance_text or joined_text
    official_hits = [word for word in OFFICIAL_WORDS if word in official_base_text]
    source_score = sum(_source_weight(str(item.get("url", "")), str(item.get("title", ""))) for item in relevant_items)
    if official_hits or source_score >= 8:
        gain = min(18, len(set(official_hits)) * 4 + max(0, min(source_score, 12)))
        score += gain
        breakdown["工商可信度"] = min(30, breakdown["工商可信度"] + gain)
        positives.append("检索到工商/企业信息平台或官网相关结果")
        dimensions.append(f"工商信息：有公开入口，+{gain} 分")
    else:
        score -= 12
        breakdown["工商可信度"] = max(0, breakdown["工商可信度"] - 12)
        risks.append("未检索到明显工商/官网信息入口，建议手动核验营业执照")
        dimensions.append("工商信息：公开入口不足，-12 分")

    negative_hits = []
    for word in RISK_WORDS:
        if word in full_text:
            negative_hits.append(word)
    if negative_hits:
        penalty = min(48, 8 * len(set(negative_hits)))
        score -= penalty
        breakdown["负面舆情"] = max(0, breakdown["负面舆情"] - penalty)
        for word in list(dict.fromkeys(negative_hits))[:8]:
            risks.append(f"公开信息或岗位描述出现风险词：{word}")
        dimensions.append(f"负面舆情：发现 {len(set(negative_hits))} 个风险词，-{penalty} 分")
    else:
        score += 8
        breakdown["负面舆情"] = min(30, breakdown["负面舆情"] + 8)
        positives.append("公开摘要中暂未发现明显诈骗/欠薪/失信等高风险词")
        dimensions.append("负面舆情：暂未发现明显风险词，+8 分")

    treatment_good = [word for word in TREATMENT_GOOD_WORDS if word in full_text]
    treatment_bad = [word for word in TREATMENT_BAD_WORDS if word in full_text]
    if treatment_good:
        gain = min(12, len(set(treatment_good)) * 2)
        score += gain
        breakdown["待遇信号"] = min(20, breakdown["待遇信号"] + gain)
        positives.append("岗位或公开摘要出现较明确福利待遇信息")
        dimensions.append(f"待遇信息：正向福利 {len(set(treatment_good))} 项，+{gain} 分")
    if treatment_bad:
        score -= min(25, len(set(treatment_bad)) * 6)
        breakdown["待遇信号"] = max(0, breakdown["待遇信号"] - min(25, len(set(treatment_bad)) * 6))
        for word in list(dict.fromkeys(treatment_bad))[:5]:
            risks.append(f"待遇/岗位描述存在谨慎信号：{word}")
        dimensions.append(f"待遇信息：发现 {len(set(treatment_bad))} 项谨慎信号")

    positive_hits = []
    for word in POSITIVE_WORDS:
        if word in full_text:
            positive_hits.append(word)
    if positive_hits:
        score += min(14, len(set(positive_hits)) * 2)
        for word in list(dict.fromkeys(positive_hits))[:6]:
            positives.append(f"公开信息或岗位描述出现正向信号：{word}")

    if not results:
        score -= 28
        breakdown["公开信息"] = max(0, breakdown["公开信息"] - 8)
        risks.append("未检索到足够公开信息，建议手动核验企业资质")
        dimensions.append("信息丰富度：检索结果为空，-28 分")
    elif relevant_count == 0:
        score -= 24
        breakdown["公开信息"] = max(0, breakdown["公开信息"] - 8)
        risks.append("搜索结果与企业名称相关性低，可能需要使用完整公司名重新核验")
        dimensions.append("信息相关性：结果疑似跑偏，-24 分")
    elif len(results) <= 2:
        score -= 12
        breakdown["公开信息"] = max(0, breakdown["公开信息"] - 5)
        risks.append("公开信息较少，企业真实性、规模和口碑需要进一步确认")
        dimensions.append("信息丰富度：较少，-12 分")
    elif len(results) >= 6:
        gain = 7 if relevant_count >= 3 else 2
        score += gain
        breakdown["公开信息"] = min(18, breakdown["公开信息"] + gain)
        positives.append("公开检索结果较多，便于交叉核验")
        dimensions.append(f"信息丰富度：较高，+{gain} 分")

    if re.search(r"\d+-\d+人|50-150人|150-500人|500-1000人|1000-5000人|5000-10000人", full_text):
        score += 4
        breakdown["岗位可信度"] = min(16, breakdown["岗位可信度"] + 4)
        positives.append("岗位信息中出现人员规模，企业信息相对更可核验")
        dimensions.append("规模信息：有人员规模描述")
    else:
        dimensions.append("规模信息：不明确")

    job_trust_hits = [word for word in JOB_TRUST_WORDS if word in job_detail]
    job_vague_hits = [word for word in JOB_VAGUE_WORDS if word in job_detail]
    if job_trust_hits:
        gain = min(8, len(set(job_trust_hits)))
        score += gain
        breakdown["岗位可信度"] = min(20, breakdown["岗位可信度"] + gain)
        dimensions.append(f"岗位可信度：JD 结构较完整，+{gain} 分")
    if job_vague_hits:
        penalty = min(24, len(set(job_vague_hits)) * 8)
        score -= penalty
        breakdown["岗位可信度"] = max(0, breakdown["岗位可信度"] - penalty)
        for word in list(dict.fromkeys(job_vague_hits))[:4]:
            risks.append(f"岗位描述存在高风险营销话术：{word}")
        dimensions.append(f"岗位可信度：发现夸张/收费话术，-{penalty} 分")

    if source_score < 0:
        penalty = min(12, abs(source_score))
        score -= penalty
        risks.append("搜索来源中出现投诉或风险导向页面，建议谨慎投递")
        dimensions.append(f"来源质量：负面来源偏多，-{penalty} 分")

    unique_risks = list(dict.fromkeys(risks))[:8]
    unique_positives = list(dict.fromkeys(positives))[:6]
    normalized_breakdown = {key: max(0, min(value, 100)) for key, value in breakdown.items()}
    score_cap = 96
    if relevant_count == 0:
        score_cap = 58
    elif "企业名称不够完整，建议用营业执照全称复查" in unique_risks:
        score_cap = 74
    return max(0, min(score, score_cap)), unique_risks, unique_positives, dimensions[:8], normalized_breakdown


def build_company_links(company_name: str) -> list[dict[str, str]]:
    keyword = quote_plus(company_name.strip())
    return [
        {
            "name": "国家企业信用信息公示系统",
            "url": f"https://www.gsxt.gov.cn/corp-query-search-1.html?searchword={keyword}",
            "reason": "核验营业执照、经营状态、行政处罚和经营异常信息。",
        },
        {
            "name": "企查查",
            "url": f"https://www.qcc.com/web/search?key={keyword}",
            "reason": "查看工商信息、司法风险、被执行人和股权结构。",
        },
        {
            "name": "天眼查",
            "url": f"https://www.tianyancha.com/search?key={keyword}",
            "reason": "复查企业风险、人员规模、融资和关联公司。",
        },
        {
            "name": "Bing 投诉/风险搜索",
            "url": f"https://www.bing.com/search?q={quote_plus(company_name + ' 诈骗 投诉 欠薪 劳动纠纷')}",
            "reason": "检索候选公司的负面新闻、投诉和求职风险反馈。",
        },
    ]


def assess_company_risk(company_name: str, job_detail: str = "") -> dict[str, object]:
    company_name = company_name.strip()
    core_terms = _company_core_terms(company_name)
    core_query = core_terms[1] if len(core_terms) > 1 else company_name
    queries = [
        f'"{company_name}" 企业资质 工商 信息',
        f'"{company_name}" 企查查 天眼查 爱企查',
        f'"{core_query}" 官网 工商 招聘',
        f'"{core_query}" 诈骗 投诉 欠薪 劳动纠纷',
        f'"{core_query}" 招聘 评价 经营异常',
    ]
    results: list[dict[str, str]] = []
    seen = set()
    for query in queries:
        try:
            found = _search_web(query, 4)
        except requests.RequestException:
            continue
        for item in found:
            url = item.get("url", "")
            if url and url not in seen:
                seen.add(url)
                results.append(item)
        relevant = [item for item in results if _is_relevant_result(company_name, item)]
        if len(relevant) >= 8:
            break

    relevant_results = [item for item in results if _is_relevant_result(company_name, item)]
    if len(relevant_results) >= 2:
        results = relevant_results + [item for item in results if item not in relevant_results]

    score, risks, positives, dimensions, breakdown = _score_company(company_name, results, job_detail)

    return {
        "company": company_name,
        "score": max(0, min(score, 96)),
        "level": _risk_level(score),
        "risks": list(dict.fromkeys(risks))[:8],
        "positives": list(dict.fromkeys(positives))[:6],
        "dimensions": dimensions,
        "breakdown": breakdown,
        "results": results[:8],
        "links": build_company_links(company_name),
    }
