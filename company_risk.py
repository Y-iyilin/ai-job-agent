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
]


def _clean_text(text: str, max_len: int = 1200) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    return text[:max_len]


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


def _score_company(company_name: str, results: list[dict[str, str]]) -> tuple[int, list[str], list[str]]:
    score = 72
    risks = []
    positives = []
    joined_text = " ".join(
        f"{item.get('title', '')} {item.get('snippet', '')}"
        for item in results
    )

    if not company_name.strip():
        return 0, ["未填写企业名称"], []

    for word in RISK_WORDS:
        if word in joined_text:
            score -= 8
            risks.append(f"公开搜索摘要出现风险词：{word}")

    for word in POSITIVE_WORDS:
        if word in joined_text:
            score += 4
            positives.append(f"公开搜索摘要出现正向信息：{word}")

    if not results:
        score -= 18
        risks.append("未检索到足够公开信息，建议手动核验企业资质")

    if len(results) <= 2:
        score -= 6
        risks.append("公开信息较少，企业真实性和规模需要进一步确认")

    unique_risks = list(dict.fromkeys(risks))[:8]
    unique_positives = list(dict.fromkeys(positives))[:6]
    return max(0, min(score, 96)), unique_risks, unique_positives


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
    queries = [
        f"{company_name} 企业资质 工商 信息",
        f"{company_name} 诈骗 投诉 欠薪 劳动纠纷",
        f"{company_name} 招聘 评价 经营异常",
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
        if len(results) >= 8:
            break

    score, risks, positives = _score_company(company_name, results)
    if job_detail:
        low_detail = job_detail.lower()
        for word in ["押金", "保证金", "培训贷", "先交钱", "收费"]:
            if word in low_detail:
                score = max(0, score - 12)
                risks.append(f"岗位描述中出现高风险表达：{word}")

    return {
        "company": company_name,
        "score": max(0, min(score, 96)),
        "level": _risk_level(score),
        "risks": list(dict.fromkeys(risks))[:8],
        "positives": list(dict.fromkeys(positives))[:6],
        "results": results[:8],
        "links": build_company_links(company_name),
    }
