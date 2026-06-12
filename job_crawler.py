import re
import json
import subprocess
from html import unescape
from pathlib import Path
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import requests
from bs4 import BeautifulSoup


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0 Safari/537.36"
    )
}

JOB_WORDS = ["岗位", "职位", "职责", "要求", "任职", "薪资", "招聘", "经验", "学历"]
BLOCKED_WORDS = ["captcha", "验证码", "登录后", "安全验证"]
JOB_DOMAINS = ["zhipin.com", "zhaopin.com", "51job.com", "liepin.com", "lagou.com", "kanzhun.com"]
CITY_PROVINCES = {
    "杭州": "浙江",
    "宁波": "浙江",
    "上海": "上海",
    "北京": "北京",
    "广州": "广东",
    "深圳": "广东",
    "南京": "江苏",
    "苏州": "江苏",
    "成都": "四川",
    "武汉": "湖北",
    "西安": "陕西",
}


def _clean_text(text: str, max_len: int = 1200) -> str:
    text = unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_len]


def _extract_real_url(url: str) -> str:
    parsed = urlparse(url)
    if "bing.com" in parsed.netloc:
        target = parse_qs(parsed.query).get("u")
        if target:
            return unquote(target[0])
    if "duckduckgo.com" in parsed.netloc:
        target = parse_qs(parsed.query).get("uddg")
        if target:
            return unquote(target[0])
    return url


def _search_bing(query: str, limit: int) -> list[dict[str, str]]:
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
                "url": _extract_real_url(link["href"]),
                "snippet": _clean_text(snippet_node.get_text(" ", strip=True), 240) if snippet_node else "",
            }
        )
        if len(results) >= limit:
            break
    return results


def _search_duckduckgo(query: str, limit: int) -> list[dict[str, str]]:
    url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
    response = requests.get(url, headers=HEADERS, timeout=12)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    results = []

    for item in soup.select(".result"):
        link = item.select_one(".result__a")
        if not link or not link.get("href"):
            continue
        snippet_node = item.select_one(".result__snippet")
        results.append(
            {
                "title": _clean_text(link.get_text(" ", strip=True), 120),
                "url": _extract_real_url(link["href"]),
                "snippet": _clean_text(snippet_node.get_text(" ", strip=True), 240) if snippet_node else "",
            }
        )
        if len(results) >= limit:
            break
    return results


def _fetch_detail(url: str) -> str:
    try:
        response = requests.get(url, headers=HEADERS, timeout=12, allow_redirects=True)
        if response.status_code >= 400:
            return ""
    except requests.RequestException:
        return ""

    soup = BeautifulSoup(response.text, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    meta_desc = ""
    meta = soup.select_one("meta[name='description']")
    if meta and meta.get("content"):
        meta_desc = meta["content"]
    text = soup.get_text(" ", strip=True)
    detail = _clean_text(f"{title} {meta_desc} {text}", 1800)

    lowered = detail.lower()
    if any(word.lower() in lowered for word in BLOCKED_WORDS):
        return ""
    return detail


def _score_job(text: str, target_role: str, city: str, resume_text: str) -> int:
    score = 35
    combined = text.lower()
    resume_lower = resume_text.lower()
    for word in [target_role, city, "应届", "助理", "实习", "实施", "售前", "产品", "客户成功", "SQL", "数据库", "文档", "沟通"]:
        if word and word.lower() in combined:
            score += 5
    for word in ["java", "数据库", "sql", "ai", "文档", "沟通"]:
        if word in resume_lower and word in combined:
            score += 4
    return max(0, min(score, 95))


def _platform_from_url(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if "zhipin" in host:
        return "BOSS直聘"
    if "zhaopin" in host:
        return "智联招聘"
    if "51job" in host:
        return "前程无忧"
    if "liepin" in host:
        return "猎聘"
    return host.replace("www.", "") or "网页"


def _is_job_domain(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return any(domain in host for domain in JOB_DOMAINS)


def _matches_city_text(text: str, city: str) -> bool:
    target_city = city.strip()
    if not target_city:
        return True
    text = text or ""
    province = CITY_PROVINCES.get(target_city, "")
    if target_city in text:
        return True
    if province and province in text and "上海" not in text:
        return True
    return False


def _filter_jobs_by_city(jobs: list[dict[str, str | int]], city: str) -> list[dict[str, str | int]]:
    filtered = []
    for job in jobs:
        city_text = " ".join(
            str(job.get(key, ""))
            for key in ("location", "title", "snippet", "detail")
        )
        if _matches_city_text(city_text, city):
            filtered.append(job)
    return filtered


def crawl_jobs(target_role: str, city: str, resume_text: str, max_jobs: int = 6) -> list[dict[str, str | int]]:
    browser_jobs = _crawl_with_browser(target_role, city, max_jobs)
    if browser_jobs:
        browser_jobs = _filter_jobs_by_city(browser_jobs, city)
        for job in browser_jobs:
            detail = str(job.get("detail", ""))
            job["match_score"] = max(
                int(job.get("match_score", 0)),
                _score_job(detail, target_role, city, resume_text),
            )
        return sorted(browser_jobs, key=lambda job: int(job["match_score"]), reverse=True)[:max_jobs]

    search_results = []
    platform_queries = [
        f"site:zhipin.com {city} {target_role} 应届生 招聘",
        f"site:zhaopin.com {city} {target_role} 应届生 招聘",
        f"site:51job.com {city} {target_role} 应届生 招聘",
        f"site:liepin.com {city} {target_role} 应届生 招聘",
        f"site:lagou.com {city} {target_role} 应届生 招聘",
        f"{city} {target_role} 应届生 招聘 JD",
    ]

    for query in platform_queries:
        for searcher in (_search_bing, _search_duckduckgo):
            try:
                found = searcher(query, max(3, max_jobs))
                search_results.extend(found)
                break
            except requests.RequestException:
                continue
        if len(search_results) >= max_jobs * 3:
            break

    jobs = []
    seen = set()
    for item in search_results:
        url = item["url"]
        if not url.startswith("http") or url in seen:
            continue
        if not _is_job_domain(url):
            continue
        seen.add(url)

        detail = _fetch_detail(url)
        source_text = detail or item["snippet"]
        if not source_text:
            continue
        if not _matches_city_text(source_text, city):
            continue
        if not any(word in source_text for word in JOB_WORDS):
            continue

        jobs.append(
            {
                "title": item["title"],
                "platform": _platform_from_url(url),
                "url": url,
                "snippet": item["snippet"],
                "detail": source_text,
                "match_score": _score_job(source_text, target_role, city, resume_text),
            }
        )
        if len(jobs) >= max_jobs:
            break

    return sorted(_filter_jobs_by_city(jobs, city), key=lambda job: int(job["match_score"]), reverse=True)


def _crawl_with_browser(target_role: str, city: str, max_jobs: int) -> list[dict[str, str | int]]:
    script = Path(__file__).with_name("browser_job_crawler.mjs")
    if not script.exists():
        return []

    try:
        result = subprocess.run(
            ["node", str(script), target_role, city, str(max_jobs)],
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []

    if not result.stdout.strip():
        return []

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []

    jobs = data.get("jobs", [])
    if not isinstance(jobs, list):
        return []
    return jobs
