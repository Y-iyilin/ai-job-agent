import base64
import json
import os
import shutil
from datetime import datetime
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from company_risk import assess_company_risk
from fixed_template_engine import (
    FixedTemplateError,
    build_replacement_prompt,
    extract_template_blocks,
    load_template_bytes,
    merge_editable_replacements,
    normalize_replacements,
    render_fixed_template,
    to_editable_replacements,
)
from hot_skills import recommend_hot_skills
from job_crawler import crawl_jobs
from job_links import build_job_links, build_search_keywords
from llm_client import LLMConfigError, call_job_agent
from prompts import build_resume_rewrite_prompt, build_template_resume_prompt, build_user_prompt
try:
    from prompts import build_role_questionnaire_prompt
except ImportError:
    def build_role_questionnaire_prompt(answers: dict[str, str], resume_text: str = "") -> str:
        answers_text = "\n".join(f"- {key}：{value}" for key, value in answers.items() if str(value).strip())
        resume_text = resume_text.strip() or "用户暂未提供简历正文，请主要根据问卷答案判断。"
        return f"""请根据下面的求职方向问卷，为用户推荐适合投递的岗位方向。

【用户简历/背景补充】
{resume_text}

【问卷答案】
{answers_text}

严格要求：
1. 输出 Markdown。
2. 不要编造用户没有提供的经历、证书、项目或技能。
3. 不要输出“如果你愿意”“我可以继续帮你”等后续服务邀约。
4. 必须保留下面 8 个二级标题。

## 一、综合求职画像

## 二、最推荐的 3 个岗位方向

每个岗位包含：岗位方向、推荐指数、为什么适合、需要补强、招聘搜索关键词、投递谨慎点。

## 三、可以尝试的 3 个备选方向

## 四、不建议优先投递的方向

## 五、目标岗位选择建议

## 六、简历补强优先级

## 七、招聘网站搜索词

## 八、7 天行动计划
"""
from resume_exporter import (
    build_docx,
    build_docx_from_template,
    build_pdf,
    build_template_preview_html,
    extract_docx_template_text,
    extract_pdf_template_text,
    extract_resume_document,
    get_template_description,
    get_template_names,
    preview_docx_template,
    preview_pdf_template,
)
from resume_parser import ResumeParseError, parse_resume_file
from role_recommender import ROLE_POOL


st.set_page_config(
    page_title="AI 求职助手 Agent",
    page_icon="💼",
    layout="wide",
)

st.markdown(
    """
    <style>
    [data-testid="stAppViewContainer"] {
        background: #F6F7F9;
    }
    [data-testid="stSidebar"] {
        background: #FFFFFF;
        border-right: 1px solid #E5E7EB;
    }
    [data-testid="stSidebar"] > div:first-child {
        padding-top: 0;
    }
    [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3 {
        font-size: 12px;
        color: #374151;
        text-transform: uppercase;
        letter-spacing: .06em;
    }
    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] li,
    [data-testid="stSidebar"] span {
        font-size: 12px;
    }
    .block-container {
        padding-top: 1.75rem;
        padding-bottom: 3rem;
        max-width: 1100px;
    }
    .figma-notice {
        display: flex;
        align-items: center;
        gap: 10px;
        background: #FEF2F2;
        border: 1px solid #FECACA;
        color: #DC2626;
        border-radius: 8px;
        padding: 10px 14px;
        margin-bottom: 18px;
        font-size: 12px;
    }
    .figma-notice strong {
        font-weight: 700;
    }
    .sidebar-logo {
        display: flex;
        align-items: center;
        gap: 10px;
        padding: 18px 2px 16px 2px;
        border-bottom: 1px solid #E5E7EB;
        margin-bottom: 14px;
    }
    .sidebar-logo-mark {
        width: 32px;
        height: 32px;
        border-radius: 8px;
        background: #DC2626;
        color: #FFFFFF;
        display: flex;
        align-items: center;
        justify-content: center;
        font-weight: 800;
        font-size: 15px;
    }
    .sidebar-logo-title {
        color: #1A1A2E;
        font-weight: 700;
        font-size: 13px;
        line-height: 1.25;
    }
    .sidebar-logo-subtitle {
        color: #6B7280;
        font-size: 11px;
        line-height: 1.25;
        margin-top: 2px;
    }
    .app-hero {
        background: transparent;
        padding: 0;
        margin-bottom: 18px;
    }
    .app-hero h1 {
        margin: 0 0 6px 0;
        font-size: 22px;
        line-height: 1.25;
        color: #1A1A2E;
        font-weight: 800;
        letter-spacing: 0;
    }
    .app-hero p {
        margin: 0;
        color: #6B7280;
        font-size: 13px;
        line-height: 1.75;
        max-width: 680px;
    }
    .hero-badges {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        margin-top: 14px;
    }
    .hero-badge {
        border: 1px solid #E5E7EB;
        border-radius: 6px;
        padding: 4px 10px;
        color: #374151;
        background: #FFFFFF;
        font-size: 11px;
        white-space: nowrap;
    }
    .workflow-strip {
        display: flex;
        align-items: stretch;
        gap: 0;
        overflow-x: auto;
    }
    .workflow-card {
        position: fixed;
        top: 12px;
        left: calc(21rem + max(1rem, (100vw - 21rem - 1100px) / 2));
        width: min(1100px, calc(100vw - 21rem - 2rem));
        z-index: 999;
        border: 1px solid #E5E7EB;
        border-radius: 8px;
        background: #FFFFFF;
        padding: 15px 16px 14px 16px;
        margin: 0 0 18px 0;
        box-shadow: 0 10px 24px rgba(15, 23, 42, .08);
        backdrop-filter: blur(10px);
    }
    .workflow-title {
        font-size: 11px;
        font-weight: 800;
        color: #9CA3AF;
        text-transform: uppercase;
        letter-spacing: .08em;
        margin-bottom: 12px;
    }
    .workflow-spacer {
        height: 126px;
    }
    .workflow-progress {
        position: relative;
        height: 6px;
        border-radius: 999px;
        background: #F3F4F6;
        overflow: hidden;
        margin: 2px 0 14px 0;
    }
    .workflow-progress-fill {
        height: 100%;
        border-radius: 999px;
        background: #DC2626;
        transition: width .35s ease;
    }
    .workflow-item {
        flex: 1 1 0;
        min-width: 120px;
        display: flex;
        flex-direction: column;
        align-items: stretch;
        gap: 7px;
    }
    .workflow-dot {
        width: 24px;
        height: 24px;
        border-radius: 999px;
        background: #F1F2F4;
        color: #9CA3AF;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 10px;
        font-weight: 800;
        flex: 0 0 auto;
    }
    .workflow-dot.active {
        background: #DC2626;
        color: #FFFFFF;
    }
    .workflow-dot.done {
        background: #22C55E;
        color: #FFFFFF;
    }
    .workflow-label {
        padding-right: 10px;
        font-size: 11px;
        line-height: 1.35;
        color: #9CA3AF;
        text-align: left;
    }
    .workflow-item.active .workflow-label {
        color: #DC2626;
        font-weight: 700;
    }
    .workflow-item.done .workflow-label {
        color: #16A34A;
    }
    .input-shell {
        background: #FFFFFF;
        border: 1px solid #E5E7EB;
        border-radius: 8px;
        padding: 18px 20px;
        margin: 16px 0 16px 0;
    }
    .input-shell-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 12px;
    }
    .input-shell-header h2 {
        margin: 0;
        font-size: 14px;
        font-weight: 800;
        color: #1A1A2E;
    }
    .input-shell-header span {
        display: block;
        font-size: 11px;
        color: #9CA3AF;
        background: #F6F7F9;
        border-radius: 6px;
        padding: 4px 8px;
    }
    .section-title {
        border-left: 4px solid #DC2626;
        padding-left: 10px;
        margin: 20px 0 10px 0;
    }
    .section-title h2 {
        margin: 0;
        font-size: 20px;
        color: #111827;
        letter-spacing: 0;
    }
    .section-title p {
        margin: 3px 0 0 0;
        color: #6B7280;
        font-size: 13px;
        line-height: 1.6;
    }
    .metric-card {
        border: 1px solid #E5E7EB;
        border-radius: 8px;
        padding: 14px 16px;
        background: #FFFFFF;
        min-height: 78px;
    }
    .metric-card .label {
        color: #6B7280;
        font-size: 12px;
        margin-bottom: 6px;
    }
    .metric-card .value {
        color: #1A1A2E;
        font-size: 15px;
        font-weight: 700;
        line-height: 1.25;
    }
    .metric-card .hint {
        color: #6B7280;
        font-size: 12px;
        margin-top: 4px;
        line-height: 1.5;
    }
    .status-dot {
        display: inline-block;
        width: 8px;
        height: 8px;
        border-radius: 999px;
        margin-right: 6px;
    }
    .status-ok { background: #16A34A; }
    .status-warn { background: #F59E0B; }
    .risk-card {
        border: 1px solid #E5E7EB;
        border-radius: 8px;
        background: #FFFFFF;
        padding: 14px 16px;
        margin: 10px 0;
    }
    .risk-score {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        min-width: 58px;
        height: 34px;
        border-radius: 8px;
        font-weight: 700;
        color: #111827;
        background: #F3F4F6;
        border: 1px solid #E5E7EB;
    }
    .risk-low { background: #ECFDF5; border-color: #BBF7D0; color: #047857; }
    .risk-mid { background: #FFFBEB; border-color: #FDE68A; color: #B45309; }
    .risk-high { background: #FEF2F2; border-color: #FECACA; color: #B91C1C; }
    .result-panel {
        background: #FFFFFF;
        border: 1px solid #E5E7EB;
        border-radius: 8px;
        padding: 18px 20px;
        margin: 14px 0;
    }
    .skill-card {
        border: 1px solid #DBEAFE;
        background: #EFF6FF;
        border-radius: 8px;
        padding: 12px 14px;
        min-height: 92px;
    }
    .skill-card strong {
        color: #1A1A2E;
        font-size: 13px;
    }
    .job-card-shell {
        background: #FFFFFF;
        border: 1px solid #E5E7EB;
        border-radius: 8px;
        padding: 16px;
        margin: 10px 0;
    }
    .job-card-shell:hover {
        border-color: rgba(220, 38, 38, .35);
        box-shadow: 0 2px 8px rgba(15, 23, 42, .04);
    }
    .agent-loader {
        display: flex;
        align-items: center;
        gap: 10px;
        padding: 10px 12px;
        border: 1px solid #E5E7EB;
        border-radius: 8px;
        background: #F9FAFB;
        color: #374151;
        font-size: 14px;
        margin: 8px 0 12px 0;
    }
    .agent-spinner {
        width: 18px;
        height: 18px;
        border: 3px solid #E5E7EB;
        border-top-color: #EF4444;
        border-radius: 50%;
        animation: agent-spin 0.9s linear infinite;
    }
    @keyframes agent-spin {
        to { transform: rotate(360deg); }
    }
    @media (max-width: 900px) {
        .workflow-card {
            left: 1rem;
            width: calc(100vw - 2rem);
            top: 8px;
        }
        .workflow-spacer {
            height: 150px;
        }
        .workflow-strip {
            grid-template-columns: repeat(2, minmax(0, 1fr));
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


DEFAULT_RESUME = """示例：
软件工程应届生，了解 Java、数据库、课程设计项目。
做过学生管理系统/图书管理系统等课程设计，能使用 AI 工具辅助资料整理和文档生成。
目标岗位：软件实施、售前技术支持、产品助理、客户成功等。"""

DEFAULT_JD = """示例：
岗位：软件实施助理
职责：协助客户完成系统上线、需求沟通、问题记录、用户培训和项目文档整理。
要求：沟通能力好，熟悉办公软件，了解数据库基础，有软件项目经验优先。"""

TARGET_ROLE_OPTIONS = ROLE_POOL + ["其他"]
HISTORY_PATH = Path("output/history.json")
HISTORY_FILES_DIR = Path("output/history_files")
ALLOWED_HISTORY_TYPES = {"简历优化稿", "手动编辑稿", "Word生成", "PDF生成"}


def load_usage_history() -> list[dict[str, str]]:
    if not HISTORY_PATH.exists():
        return []
    try:
        data = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [
                item
                for item in data
                if isinstance(item, dict) and item.get("type") in ALLOWED_HISTORY_TYPES
            ]
    except Exception:
        return []
    return []


def save_usage_history(history: list[dict[str, str]]) -> None:
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_PATH.write_text(
        json.dumps(history[:80], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def append_usage_history(
    event_type: str,
    target_role: str,
    city: str,
    summary: str,
    content: str = "",
    file_path: str = "",
) -> None:
    record = {
        "id": datetime.now().strftime("%Y%m%d%H%M%S%f"),
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "type": event_type,
        "target_role": target_role,
        "city": city,
        "summary": summary[:160],
        "content": content,
        "file_path": file_path,
    }
    history = [record] + load_usage_history()
    save_usage_history(history)
    st.session_state.usage_history = history


def save_history_file(file_name: str, data: bytes) -> str:
    HISTORY_FILES_DIR.mkdir(parents=True, exist_ok=True)
    path = HISTORY_FILES_DIR / file_name
    path.write_bytes(data)
    return str(path)


def save_output_file(file_name: str, data: bytes) -> str:
    output_dir = Path("output")
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / file_name
    path.write_bytes(data)
    return str(path)


def render_pdf_preview(pdf_bytes: bytes) -> None:
    encoded = base64.b64encode(pdf_bytes).decode("ascii")
    st.markdown(
        f"""
        <iframe
            src="data:application/pdf;base64,{encoded}"
            width="100%"
            height="720"
            style="border:1px solid #e5e7eb;border-radius:8px;background:#fff;"
        ></iframe>
        """,
        unsafe_allow_html=True,
    )


def render_section(title: str, description: str = "") -> None:
    st.markdown(
        f"""
        <div class="section-title">
          <h2>{title}</h2>
          <p>{description}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_metric_card(label: str, value: str, hint: str) -> None:
    st.markdown(
        f"""
        <div class="metric-card">
          <div class="label">{label}</div>
          <div class="value">{value}</div>
          <div class="hint">{hint}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def build_workflow_html(current_step: int) -> str:
    steps = [
        "读取简历和目标",
        "生成关键词标签",
        "爬取真实岗位",
        "分析 JD 匹配",
        "生成改写内容",
        "导出下载文件",
    ]
    current_step = max(1, min(int(current_step or 1), len(steps)))
    progress_width = int(((current_step - 1) / (len(steps) - 1)) * 100)
    items = []
    for index, label in enumerate(steps, start=1):
        if index < current_step:
            state = "done"
            dot = "✓"
        elif index == current_step:
            state = "active"
            dot = f"{index:02d}"
        else:
            state = ""
            dot = f"{index:02d}"
        items.append(
            f'<div class="workflow-item {state}">'
            f'<div class="workflow-dot {state}">{dot}</div>'
            f'<div class="workflow-label">{label}</div>'
            f'</div>'
        )
    return (
        '<div class="workflow-card">'
        '<div class="workflow-title">Agent 工作流</div>'
        f'<div class="workflow-progress"><div class="workflow-progress-fill" style="width:{progress_width}%;"></div></div>'
        f'<div class="workflow-strip">{"".join(items)}</div>'
        '</div>'
    )


def render_workflow(current_step: int) -> None:
    st.markdown(build_workflow_html(current_step), unsafe_allow_html=True)
    st.markdown('<div class="workflow-spacer"></div>', unsafe_allow_html=True)


def get_agent_step() -> int:
    manual_step = int(st.session_state.get("agent_workflow_step", 1) or 1)
    inferred_step = 1
    if st.session_state.resume_docx_data or st.session_state.resume_pdf_data:
        inferred_step = 6
    elif st.session_state.resume_rewrite_result or st.session_state.word_resume_text or st.session_state.pdf_resume_text:
        inferred_step = 5
    elif st.session_state.analysis_result:
        inferred_step = 4
    elif st.session_state.crawled_jobs:
        inferred_step = 3
    elif st.session_state.search_keywords or st.session_state.hot_skills:
        inferred_step = 2
    return max(manual_step, inferred_step)


def render_env_status() -> None:
    load_dotenv()
    session_ready = bool(st.session_state.get("user_ai_api_key", "").strip())
    items = [
        ("用户 API Key", session_ready),
        ("Node.js", bool(shutil.which("node"))),
    ]
    for label, ok in items:
        cls = "status-ok" if ok else "status-warn"
        text = "已配置" if ok else "未检测到"
        st.markdown(
            f'<span class="status-dot {cls}"></span>{label}：{text}',
            unsafe_allow_html=True,
        )


def build_user_ai_config() -> dict[str, str] | None:
    api_key = st.session_state.get("user_ai_api_key", "").strip()
    base_url = st.session_state.get("user_ai_base_url", "").strip().rstrip("/")
    model = st.session_state.get("user_ai_model", "").strip()
    if not api_key or not base_url or not model:
        return None
    return {
        "api_key": api_key,
        "base_url": base_url,
        "model": model,
        "fallback_models": st.session_state.get("user_ai_fallback_models", "").strip(),
        "timeout": "120",
        "max_retries": "2",
    }


def call_agent(user_prompt: str) -> str:
    user_config = build_user_ai_config()
    if not user_config:
        raise LLMConfigError("请先在左侧“AI 接口登录”填写自己的 Base URL、API Key 和模型名。")
    return call_job_agent(user_prompt, config_override=user_config)


def render_company_risk_result(result: dict[str, object]) -> None:
    score = int(result.get("score", 0))
    level = str(result.get("level", "未知"))
    cls = "risk-low" if score >= 80 else "risk-mid" if score >= 60 else "risk-high"
    st.markdown(
        f"""
        <div class="risk-card">
          <div style="display:flex;align-items:center;justify-content:space-between;gap:12px;">
            <div>
              <div style="font-size:14px;color:#6B7280;margin-bottom:4px;">企业风险评分</div>
              <div style="font-size:18px;font-weight:700;color:#111827;">{result.get("company", "")}</div>
            </div>
            <div class="risk-score {cls}">{score}分 · {level}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    risks = result.get("risks", [])
    positives = result.get("positives", [])
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**风险提示**")
        if risks:
            for item in risks:
                st.write(f"- {item}")
        else:
            st.write("- 暂未从公开摘要中发现明显风险词。")
    with c2:
        st.markdown("**正向信息**")
        if positives:
            for item in positives:
                st.write(f"- {item}")
        else:
            st.write("- 暂未检索到足够明确的正向资质信号。")
    dimensions = result.get("dimensions", [])
    breakdown = result.get("breakdown", {})
    if isinstance(breakdown, dict) and breakdown:
        st.markdown("**分项评分**")
        score_cols = st.columns(min(5, len(breakdown)))
        for index, (name, value) in enumerate(breakdown.items()):
            with score_cols[index % len(score_cols)]:
                st.metric(str(name), f"{int(value)}")
    if dimensions:
        st.markdown("**评分维度**")
        dim_cols = st.columns(2)
        for index, item in enumerate(dimensions):
            with dim_cols[index % 2]:
                st.caption(f"- {item}")

    with st.expander("查看公开信息摘要和核验入口", expanded=False):
        st.caption("评分基于公开搜索摘要和岗位描述关键词，只用于求职风险提醒，不等同于法律或工商结论。")
        for item in result.get("results", []):
            st.markdown(f"- [{item.get('title', '网页')}]({item.get('url', '#')})")
            if item.get("snippet"):
                st.caption(str(item["snippet"]))
        st.markdown("**建议手动核验**")
        for item in result.get("links", []):
            st.link_button(str(item["name"]), str(item["url"]), use_container_width=True)
            st.caption(str(item["reason"]))


def get_template_context(template_name: str, template_bytes: bytes, template_file_name: str) -> tuple[str, str]:
    description = get_template_description(template_name)
    if template_bytes and template_file_name.lower().endswith(".docx"):
        return description, extract_docx_template_text(template_bytes)
    if template_bytes and template_file_name.lower().endswith(".pdf"):
        return description, extract_pdf_template_text(template_bytes)
    return description, f"{template_name}\n{description}"


def init_state() -> None:
    if "analysis_result" not in st.session_state:
        st.session_state.analysis_result = ""
    if "job_links" not in st.session_state:
        st.session_state.job_links = []
    if "search_keywords" not in st.session_state:
        st.session_state.search_keywords = []
    if "crawled_jobs" not in st.session_state:
        st.session_state.crawled_jobs = []
    if "hot_skills" not in st.session_state:
        st.session_state.hot_skills = []
    if "parsed_resume_text" not in st.session_state:
        st.session_state.parsed_resume_text = ""
    if "resume_rewrite_result" not in st.session_state:
        st.session_state.resume_rewrite_result = ""
    if "uploaded_resume_bytes" not in st.session_state:
        st.session_state.uploaded_resume_bytes = b""
    if "uploaded_resume_name" not in st.session_state:
        st.session_state.uploaded_resume_name = ""
    if "role_recommendations" not in st.session_state:
        st.session_state.role_recommendations = []
    if "role_questionnaire_result" not in st.session_state:
        st.session_state.role_questionnaire_result = ""
    if "custom_target_role" not in st.session_state:
        st.session_state.custom_target_role = ""
    if "imported_template_bytes" not in st.session_state:
        st.session_state.imported_template_bytes = b""
    if "imported_template_name" not in st.session_state:
        st.session_state.imported_template_name = ""
    if "resume_docx_data" not in st.session_state:
        st.session_state.resume_docx_data = b""
    if "resume_pdf_data" not in st.session_state:
        st.session_state.resume_pdf_data = b""
    if "template_docx_data" not in st.session_state:
        st.session_state.template_docx_data = b""
    if "template_pdf_data" not in st.session_state:
        st.session_state.template_pdf_data = b""
    if "editable_resume_text" not in st.session_state:
        st.session_state.editable_resume_text = ""
    if "word_resume_text" not in st.session_state:
        st.session_state.word_resume_text = ""
    if "pdf_resume_text" not in st.session_state:
        st.session_state.pdf_resume_text = ""
    if "usage_history" not in st.session_state:
        st.session_state.usage_history = load_usage_history()
    if "company_risk_results" not in st.session_state:
        st.session_state.company_risk_results = {}
    if "agent_workflow_step" not in st.session_state:
        st.session_state.agent_workflow_step = 1
    if "fixed_resume_text" not in st.session_state:
        st.session_state.fixed_resume_text = ""
    if "fixed_template_bytes" not in st.session_state:
        st.session_state.fixed_template_bytes = b""
    if "fixed_template_name" not in st.session_state:
        st.session_state.fixed_template_name = ""
    if "fixed_template_signature" not in st.session_state:
        st.session_state.fixed_template_signature = ""
    if "fixed_replacements_text" not in st.session_state:
        st.session_state.fixed_replacements_text = ""
    if "fixed_result_docx" not in st.session_state:
        st.session_state.fixed_result_docx = b""
    if "user_ai_provider" not in st.session_state:
        st.session_state.user_ai_provider = "中转站"
    if "user_ai_base_url" not in st.session_state:
        st.session_state.user_ai_base_url = ""
    if "user_ai_api_key" not in st.session_state:
        st.session_state.user_ai_api_key = ""
    if "user_ai_model" not in st.session_state:
        st.session_state.user_ai_model = ""
    if "user_ai_fallback_models" not in st.session_state:
        st.session_state.user_ai_fallback_models = ""


def clear_resume_exports() -> None:
    st.session_state.resume_docx_data = b""
    st.session_state.resume_pdf_data = b""
    st.session_state.template_docx_data = b""
    st.session_state.template_pdf_data = b""


def set_agent_step(step: int) -> None:
    st.session_state.agent_workflow_step = max(1, min(int(step), 6))


def file_signature(file_obj) -> str:
    if file_obj is None:
        return ""
    return f"{getattr(file_obj, 'name', '')}:{getattr(file_obj, 'size', 0)}"


def build_markdown_file(
    result: str,
    target_role: str,
    city: str,
    search_keywords: list[str],
    job_links: list[dict[str, str]],
    crawled_jobs: list[dict[str, str | int]],
    hot_skills: list[dict[str, str]],
    resume_rewrite_result: str,
) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    keywords_md = "\n".join(f"- {item}" for item in search_keywords) or "- 暂无"
    links_md = "\n".join(
        f"- [{item['platform']}：{item['title']}]({item['url']})  \n  推荐理由：{item['reason']}"
        for item in job_links
    ) or "- 暂无"
    crawled_jobs_md = "\n".join(
        f"- [{item['title']}]({item['url']})｜{item['platform']}｜匹配度：{item['match_score']}  \n  {item['snippet'] or str(item['detail'])[:160]}"
        for item in crawled_jobs
    ) or "- 暂无"
    hot_skills_md = "\n".join(
        f"- {item['skill']}（{item['status']}）：{item['reason']}"
        for item in hot_skills
    ) or "- 暂无"
    return f"""# AI 求职助手 Agent 分析结果

- 生成时间：{now}
- 目标岗位方向：{target_role or "未填写"}
- 目标城市：{city or "未填写"}

## 招聘搜索关键词

{keywords_md}

## 推荐招聘链接

{links_md}

## 真实岗位侦察结果

{crawled_jobs_md}

## 热门能力标签

{hot_skills_md}

## 简历优化稿

{resume_rewrite_result or "暂无"}

---

{result}
"""


def main() -> None:
    init_state()

    workflow_placeholder = st.empty()
    workflow_placeholder.markdown(build_workflow_html(get_agent_step()), unsafe_allow_html=True)
    st.markdown('<div class="workflow-spacer"></div>', unsafe_allow_html=True)
    st.markdown(
        """
        <div class="figma-notice">
          <strong>演示模式</strong>
          <span>线上使用时建议在左侧填写自己的 API Key、Base URL 和模型；岗位爬取和企业风险评分会读取公开网页摘要。</span>
        </div>
        <div class="app-hero">
          <h1>AI 求职助手 Agent</h1>
          <p>上传简历、输入目标岗位和城市后，Agent 会解析材料、侦察真实招聘信息、分析 JD 匹配度，并生成可编辑的 Word / PDF 简历版本。</p>
          <div class="hero-badges">
            <span class="hero-badge">简历解析</span>
            <span class="hero-badge">真实岗位侦察</span>
            <span class="hero-badge">JD 匹配评分</span>
            <span class="hero-badge">模板化简历生成</span>
            <span class="hero-badge">历史记录</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.sidebar:
        st.markdown(
            """
            <div class="sidebar-logo">
              <div class="sidebar-logo-mark">AI</div>
              <div>
                <div class="sidebar-logo-title">AI 求职助手</div>
                <div class="sidebar-logo-subtitle">Agent · v1.0.0</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.subheader("使用说明")
        st.write("1. 线上使用时在左侧填写自己的 API Key。")
        st.write("2. 粘贴真实简历和岗位 JD。")
        st.write("3. 也可以上传 `.txt`、`.docx`、`.pdf` 简历文件。")
        st.write("4. 点击开始分析，结果可下载为 Markdown。")
        st.write("5. 可以爬取公开网页里的真实岗位信息，并抽取岗位摘要。")
        st.warning("请不要把身份证号、手机号、真实住址等敏感信息粘贴进测试内容。")
        st.divider()
        st.subheader("环境状态")
        render_env_status()
        st.divider()
        st.subheader("AI 接口登录")
        provider = st.radio(
            "接口类型",
            ["中转站", "OpenAI 官方"],
            horizontal=True,
            key="user_ai_provider",
        )
        if provider == "OpenAI 官方":
            default_base_url = "https://api.openai.com/v1"
            model_options = ["gpt-4.1-mini", "gpt-4.1", "gpt-4o-mini", "gpt-4o"]
        else:
            default_base_url = "https://你的中转站地址/v1"
            model_options = ["gpt-5.4-mini", "gpt-4.1-mini", "gpt-4o-mini", "自定义"]
        st.text_input(
            "Base URL",
            value=st.session_state.user_ai_base_url or default_base_url,
            key="user_ai_base_url",
            help="必须兼容 OpenAI /chat/completions 格式。",
        )
        st.text_input(
            "API Key",
            key="user_ai_api_key",
            type="password",
            help="只保存在当前浏览器会话，不写入历史记录。",
        )
        selected_model = st.selectbox("模型", model_options)
        if selected_model == "自定义":
            st.text_input("自定义模型名", key="user_ai_model")
        else:
            st.session_state.user_ai_model = selected_model
            st.caption(f"当前模型：{selected_model}")
        st.text_input(
            "备用模型（可选，逗号分隔）",
            key="user_ai_fallback_models",
            placeholder="例如：gpt-4o-mini,gpt-4.1-mini",
        )
        if build_user_ai_config():
            st.success("已使用当前会话 API 配置。")
        else:
            st.info("必须填写自己的 API 配置后才能调用 AI。服务器不会提供默认 Key。")
        st.divider()
        st.subheader("使用记录")
        if st.button("刷新历史", use_container_width=True):
            st.session_state.usage_history = load_usage_history()
        if st.session_state.usage_history:
            for item in st.session_state.usage_history[:10]:
                label = f"{item.get('time', '')}｜{item.get('type', '')}"
                with st.expander(label, expanded=False):
                    st.caption(f"{item.get('target_role', '')}｜{item.get('city', '')}")
                    st.write(item.get("summary", ""))
                    if item.get("file_path"):
                        st.code(item["file_path"])
                    if item.get("content") and st.button("载入这条内容", key=f"load_history_{item.get('id')}", use_container_width=True):
                        if item.get("type") == "岗位分析":
                            st.session_state.analysis_result = item["content"]
                        else:
                            st.session_state.resume_rewrite_result = item["content"]
                            st.session_state.editable_resume_text = extract_resume_document(item["content"])
                            if item.get("type") == "Word生成":
                                st.session_state.word_resume_text = item["content"]
                            if item.get("type") == "PDF生成":
                                st.session_state.pdf_resume_text = item["content"]
                            clear_resume_exports()
                        st.rerun()
        else:
            st.info("暂无历史记录。")

    st.markdown(
        """
        <div class="input-shell-header" style="margin-top:16px;margin-bottom:12px;">
          <h2>输入信息</h2>
          <span>支持历史记录载入和文件解析</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    uploaded_resume = st.file_uploader(
        "上传简历文件",
        type=["txt", "docx", "pdf"],
        help="支持可复制文字的 TXT、DOCX、PDF。扫描图片版 PDF 暂不支持 OCR。",
    )
    if uploaded_resume is not None:
        try:
            uploaded_bytes = uploaded_resume.getvalue()
            parsed_text = parse_resume_file(uploaded_resume.name, uploaded_bytes)
            st.session_state.uploaded_resume_bytes = uploaded_bytes
            st.session_state.uploaded_resume_name = uploaded_resume.name
            st.session_state.parsed_resume_text = parsed_text
            st.success(f"已识别简历文件：{uploaded_resume.name}")
            with st.expander("查看识别出的简历文本", expanded=False):
                st.text_area("识别结果", value=parsed_text, height=220, disabled=True)
        except ResumeParseError as exc:
            st.error(str(exc))

    with st.expander("不知道投什么岗位？先做一个方向问卷", expanded=False):
        with st.form("role_questionnaire"):
            st.caption("这个问卷用于给不确定求职方向的人做初步推荐，问题越细，推荐越接近实际情况。")
            col_q1, col_q2, col_q3 = st.columns(3)
            with col_q1:
                major = st.selectbox("你的专业/背景更接近？", ["软件/计算机/信息管理", "电子信息/自动化", "管理/工商/市场", "财会/金融/经管", "文科/语言/传媒", "其他"])
                education = st.selectbox("你的学历阶段？", ["专科", "本科", "硕士及以上"])
                internship = st.selectbox("你有没有相关实习？", ["没有实习", "有不相关实习", "有相关实习"])
                work_preference = st.selectbox(
                    "你更愿意做哪类工作？",
                    ["沟通客户、解决问题", "整理需求、做产品文档", "写代码、做系统", "做数据、做表格分析", "做内容、活动和账号"],
                )
                coding_level = st.selectbox("你的代码能力大概是？", ["比较弱", "能做课程设计", "比较熟练"])
                sql = st.selectbox("你的 SQL / 数据库能力？", ["不会", "会基础查询", "比较熟练"])
                excel = st.selectbox("你的 Excel / 表格能力？", ["一般", "会基础整理", "比较熟练"])
                english = st.selectbox("英语或文档阅读能力？", ["较弱", "一般", "还可以"])
                ai_tools = st.selectbox("你想把 AI 工具使用当成求职优势吗？", ["愿意把 AI 当优势", "一般", "暂时不想"])
            with col_q2:
                communication = st.selectbox("你对沟通的接受度？", ["愿意经常沟通", "可以适度沟通", "更喜欢少沟通"])
                document = st.selectbox("你能接受写文档、整理材料吗？", ["能接受大量文档", "一般", "不太喜欢"])
                business_trip = st.selectbox("你能接受出差或现场支持吗？", ["能接受出差", "偶尔可以", "不想出差"])
                pressure = st.selectbox("你对工作压力的偏好？", ["能接受业绩压力", "可以接受项目压力", "希望压力稳定"])
                detail = st.selectbox("你自评细心程度？", ["比较细心", "一般", "不算细心"])
                creativity = st.selectbox("你喜欢创意表达吗？", ["喜欢创意表达", "一般", "不喜欢"])
                customer = st.selectbox("你愿意面对客户或用户吗？", ["愿意", "可以适度", "不太愿意"])
                team_style = st.selectbox("你更喜欢的协作方式？", ["跨部门协作", "小团队协作", "独立完成任务"])
                learning_speed = st.selectbox("你学习新工具的速度？", ["比较快", "一般", "比较慢"])
            with col_q3:
                company_type = st.selectbox("你偏好的公司类型？", ["互联网/软件公司", "传统企业/稳定平台", "乙方/项目型公司", "都可以"])
                industry = st.selectbox("你感兴趣的行业？", ["软件/SaaS", "电商/零售", "教育/培训", "医疗/政企", "制造/工业", "金融/财务", "都可以"])
                salary_priority = st.selectbox("你更看重什么？", ["成长空间", "稳定性", "薪资", "离家近/少加班"])
                city_preference = st.selectbox("城市选择？", ["只看本地", "省内可以", "全国都可以"])
                sales_acceptance = st.selectbox("你能接受销售性质工作吗？", ["能接受", "只接受轻销售", "不能接受"])
                operations_interest = st.selectbox("你对运营类工作兴趣？", ["有兴趣", "一般", "没兴趣"])
                dev_interest = st.selectbox("你对开发岗兴趣？", ["有兴趣", "一般", "没兴趣"])
                long_term_goal = st.selectbox("长期更想往哪个方向发展？", ["技术/系统", "产品/项目", "运营/增长", "客户/商务", "管理/综合"])
                certificates = st.text_input("你已有证书或优势关键词", placeholder="例如：四六级、计算机二级、普通话、获奖、学生干部")
            submitted = st.form_submit_button("生成岗位方向推荐", use_container_width=True)

        if submitted:
            questionnaire_answers = {
                "专业/背景": major,
                "学历阶段": education,
                "实习情况": internship,
                "更愿意做的工作": work_preference,
                "代码能力": coding_level,
                "SQL / 数据库能力": sql,
                "Excel / 表格能力": excel,
                "英语或文档阅读能力": english,
                "AI 工具使用意愿": ai_tools,
                "沟通接受度": communication,
                "文档整理接受度": document,
                "出差/现场支持接受度": business_trip,
                "压力偏好": pressure,
                "细心程度": detail,
                "创意表达偏好": creativity,
                "面对客户/用户意愿": customer,
                "协作方式": team_style,
                "学习新工具速度": learning_speed,
                "偏好公司类型": company_type,
                "感兴趣行业": industry,
                "最看重因素": salary_priority,
                "城市选择": city_preference,
                "销售性质接受度": sales_acceptance,
                "运营兴趣": operations_interest,
                "开发岗兴趣": dev_interest,
                "长期发展方向": long_term_goal,
                "证书或优势关键词": certificates,
            }
            try:
                with st.spinner("正在把问卷答案交给 AI 生成岗位方向建议..."):
                    prompt = build_role_questionnaire_prompt(
                        questionnaire_answers,
                        st.session_state.parsed_resume_text,
                    )
                    st.session_state.role_questionnaire_result = call_agent(prompt)
                    st.session_state.role_recommendations = []
                st.success("岗位方向建议已生成。")
            except LLMConfigError as exc:
                st.error(str(exc))
                st.info("问卷推荐需要使用你在左侧填写的 API 配置。")
            except Exception as exc:
                st.error("生成岗位方向建议失败，请检查 API 地址、模型名称、Key、额度或网络状态。")
                st.code(str(exc))

        if st.session_state.role_questionnaire_result:
            st.markdown("**AI 岗位方向建议**")
            st.markdown(st.session_state.role_questionnaire_result)

    col_left, col_right = st.columns(2)

    with col_left:
        resume_text = st.text_area(
            "简历内容",
            value=st.session_state.parsed_resume_text or DEFAULT_RESUME,
            height=320,
            help="粘贴你的简历、项目经历、技能和求职方向。",
        )

    with col_right:
        jd_text = st.text_area(
            "岗位 JD",
            value=DEFAULT_JD,
            height=320,
            help="粘贴招聘网站上的岗位职责和任职要求。",
        )

    col_role, col_city = st.columns([2, 1])

    with col_role:
        selected_target_role = st.selectbox(
            "目标岗位方向",
            TARGET_ROLE_OPTIONS,
        )
        if selected_target_role == "其他":
            custom_target_role = st.text_input(
                "输入你的求职方向",
                placeholder="例如：项目助理、短视频运营、AI 产品助理",
                key="custom_target_role",
            )
            target_role = custom_target_role.strip()
        else:
            target_role = selected_target_role

    with col_city:
        city = st.text_input("目标城市", value="杭州", help="用于生成招聘搜索关键词和推荐链接。")

    summary_cols = st.columns(4)
    with summary_cols[0]:
        render_metric_card("当前岗位方向", target_role or "未填写", "来自当前目标岗位选择")
    with summary_cols[1]:
        render_metric_card("岗位侦察", str(len(st.session_state.crawled_jobs)), "抓取真实岗位详情页")
    with summary_cols[2]:
        render_metric_card("历史记录", str(len(st.session_state.usage_history)), "可载入旧结果继续编辑")
    with summary_cols[3]:
        export_state = "已生成" if (st.session_state.resume_docx_data or st.session_state.resume_pdf_data) else "Word / PDF"
        render_metric_card("导出能力", export_state, "支持模板参考与在线编辑")

    st.caption("岗位侦察会抓取公开网页和搜索结果，不绕过登录、验证码或付费限制；岗位是否仍在招聘以原网页为准。")

    crawl_enabled = st.checkbox("开始分析时同时爬取真实招聘信息", value=True)
    resume_template = st.selectbox(
        "简历导出模板",
        get_template_names(),
        help="用于普通 Word/PDF 导出；真正保留原模板位置替换，建议上传带 {{AI_RESUME}} 或 {{简历正文}} 占位符的 DOCX 模板。",
    )
    st.caption(f"模板预览：{get_template_description(resume_template)}")
    st.markdown(build_template_preview_html(resume_template), unsafe_allow_html=True)

    with st.expander("导入自己的 Word 简历或模板", expanded=False):
        imported_template = st.file_uploader(
            "上传 .docx 或 .pdf 作为导出模板",
            type=["docx", "pdf"],
            key="template_uploader",
            help="可以上传已有简历，也可以上传空白简历模板。DOCX 支持占位符插入；普通 PDF 只能作为参考/封面合并，不能稳定替换原版式内容。",
        )
        st.caption("DOCX 模板会把可识别文字交给 AI 参考，导出时优先替换模板文字并保留样式、图片和版面结构。PDF 模板会把可识别文字交给 AI 参考，生成新的 PDF 简历。")
        if imported_template is not None:
            template_bytes = imported_template.getvalue()
            st.session_state.imported_template_bytes = template_bytes
            st.session_state.imported_template_name = imported_template.name
            try:
                if imported_template.name.lower().endswith(".pdf"):
                    preview = preview_pdf_template(template_bytes)
                    st.success(f"已导入 PDF 模板：{imported_template.name}")
                    c1, c2 = st.columns(2)
                    c1.metric("页数", preview["page_count"])
                    c2.metric("可识别文字行", len(preview.get("sample_text", [])))
                else:
                    preview = preview_docx_template(template_bytes)
                    st.success(f"已导入 Word 模板：{imported_template.name}")
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("段落", preview["paragraph_count"])
                    c2.metric("表格", preview["table_count"])
                    c3.metric("图片", preview["image_count"])
                    c4.metric("节", preview["section_count"])
                sample_text = preview.get("sample_text", [])
                if sample_text:
                    st.markdown("**模板内容预览**")
                    preview_text = "<br>".join(str(line) for line in sample_text)
                    st.markdown(
                        f"""
                        <div style="border:1px solid #e5e7eb;border-radius:8px;padding:12px 14px;background:#ffffff;color:#111827;line-height:1.7;">
                        {preview_text}
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                else:
                    st.info("模板内没有识别到文字，可能是纯图片模板或空白模板。")
            except Exception as exc:
                st.error("模板预览失败，请确认上传的是正常的 .docx 文件。")
                st.code(str(exc))
        elif st.session_state.imported_template_name:
            st.info(f"当前已导入模板：{st.session_state.imported_template_name}")

    max_jobs = st.slider("最多爬取岗位数量", min_value=3, max_value=10, value=6)

    start = st.button("开始分析", type="primary", use_container_width=True)

    if start:
        if not resume_text.strip():
            st.error("请先填写简历内容。")
        elif not jd_text.strip():
            st.error("请先填写岗位 JD。")
        elif not target_role.strip():
            st.error("请先填写目标岗位方向。")
        elif not city.strip():
            st.error("请先填写目标城市。")
        else:
            progress = st.progress(0)
            loader = st.empty()
            loader.markdown(
                '<div class="agent-loader"><div class="agent-spinner"></div><span>Agent 正在读取材料并执行求职分析工作流...</span></div>',
                unsafe_allow_html=True,
            )
            st.session_state.resume_rewrite_result = ""
            st.session_state.editable_resume_text = ""
            st.session_state.word_resume_text = ""
            st.session_state.pdf_resume_text = ""
            set_agent_step(1)
            clear_resume_exports()
            with st.status("Agent 正在执行求职分析流程...", expanded=True) as status:
                st.write("步骤 1/6：读取简历内容")
                progress.progress(10)
                try:
                    st.write("步骤 2/6：生成搜索关键词和热门能力标签")
                    set_agent_step(2)
                    st.session_state.search_keywords = build_search_keywords(target_role, city)
                    st.session_state.job_links = build_job_links(target_role, city)
                    st.session_state.hot_skills = recommend_hot_skills(target_role, resume_text)
                    progress.progress(25)

                    st.write("步骤 3/6：爬取公开招聘信息并抽取岗位卡片")
                    set_agent_step(3)
                    if crawl_enabled:
                        st.session_state.crawled_jobs = crawl_jobs(
                            target_role=target_role,
                            city=city,
                            resume_text=resume_text,
                            max_jobs=max_jobs,
                        )
                        st.write(f"已获取 {len(st.session_state.crawled_jobs)} 条岗位信息")
                    else:
                        st.session_state.crawled_jobs = []
                        st.write("已跳过岗位爬取")
                    progress.progress(45)

                    st.write("步骤 4/6：调用大模型分析 JD、岗位要求和简历匹配度")
                    set_agent_step(4)
                    prompt = build_user_prompt(
                        resume_text=resume_text,
                        jd_text=jd_text,
                        target_role=target_role,
                    )
                    st.session_state.analysis_result = call_agent(prompt)
                    progress.progress(70)

                    st.write("步骤 5/6：记录岗位画像，等待用户手动生成简历优化稿")
                    set_agent_step(5)
                    st.write("为节省 API token，本次不自动改写简历。需要时请在下方点击“生成简历优化稿”。")
                    progress.progress(90)

                    st.write("步骤 6/6：准备分析结果和岗位链接")
                    progress.progress(100)
                    loader.empty()
                    status.update(label="Agent 工作流执行完成", state="complete", expanded=False)
                    st.success("分析完成。")
                except LLMConfigError as exc:
                    loader.empty()
                    status.update(label="Agent 工作流中断：API 配置缺失", state="error", expanded=True)
                    st.error(str(exc))
                    st.info("请检查左侧 API 登录信息。线上版本要求用户使用自己的 API Key。")
                except Exception as exc:
                    loader.empty()
                    status.update(label="Agent 工作流中断：执行失败", state="error", expanded=True)
                    st.error("调用 AI 接口失败，请检查中转 API 地址、模型名称、Key、网络状态或稍后重试。")
                    st.code(str(exc))

    st.divider()

    render_section("热门能力标签", "根据目标岗位和简历内容，提示哪些能力已经体现、哪些需要补强。")
    skills_to_show = st.session_state.hot_skills or recommend_hot_skills(target_role, resume_text)
    skill_cols = st.columns(2)
    for index, item in enumerate(skills_to_show):
        with skill_cols[index % 2]:
            st.markdown(
                f"""
                <div class="skill-card">
                  <strong>{item['skill']}</strong>
                  <div style="font-size:11px;color:#2563EB;margin:5px 0 4px 0;">{item['status']}</div>
                  <div style="font-size:12px;color:#6B7280;line-height:1.6;">{item['reason']}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    render_section("招聘搜索关键词", "用于在招聘网站继续复查岗位，避免只依赖单个平台结果。")
    if st.session_state.search_keywords:
        st.write("、".join(st.session_state.search_keywords))
    else:
        preview_keywords = build_search_keywords(target_role, city)
        st.write("、".join(preview_keywords))

    render_section("推荐招聘链接", "保留主流招聘平台入口，岗位是否仍在招聘以原网页为准。")
    links_to_show = st.session_state.job_links or build_job_links(target_role, city)
    link_cols = st.columns(2)
    for index, item in enumerate(links_to_show):
        with link_cols[index % 2]:
            st.markdown(f"**{item['platform']}**")
            st.link_button(item["title"], item["url"], use_container_width=True)
            st.caption(item["reason"])

    render_section("真实岗位侦察", "展示爬取到的真实岗位卡片、匹配分、公司、薪资、地点和详情链接。")
    if st.session_state.crawled_jobs:
        for item in st.session_state.crawled_jobs:
            with st.container():
                st.markdown('<div class="job-card-shell">', unsafe_allow_html=True)
                col_job, col_score = st.columns([4, 1])
                with col_job:
                    st.markdown(f"**{item['title']}**")
                    st.caption(f"{item['platform']}")
                with col_score:
                    st.metric("匹配分", item["match_score"])

                job_meta = []
                if item.get("company"):
                    job_meta.append(f"公司：{item['company']}")
                if item.get("salary"):
                    job_meta.append(f"薪资：{item['salary']}")
                if item.get("location"):
                    job_meta.append(f"地点：{item['location']}")
                if job_meta:
                    st.write("｜".join(job_meta))

                st.markdown("**抓取到的岗位信息**")
                detail_text = str(item.get("detail") or item.get("snippet") or "暂无详细摘要")
                st.write(detail_text)

                action_col1, action_col2 = st.columns(2)
                with action_col1:
                    st.link_button("打开岗位原网页", item["url"], use_container_width=True)
                with action_col2:
                    company_name = str(item.get("company", "")).split("  ")[0].strip()
                    risk_key = f"{company_name}-{item.get('url', '')}"
                    if st.button(
                        "评估企业风险",
                        key=f"risk_{index}_{risk_key}",
                        use_container_width=True,
                        disabled=not bool(company_name),
                    ):
                        with st.spinner("正在检索企业资质、投诉和风险信息..."):
                            st.session_state.company_risk_results[risk_key] = assess_company_risk(
                                company_name,
                                detail_text,
                            )
                    if risk_key in st.session_state.company_risk_results:
                        render_company_risk_result(st.session_state.company_risk_results[risk_key])
                st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.info("点击“开始分析”后会尝试爬取公开网页中的真实岗位信息。若招聘平台要求登录或验证码，可能只能抓到搜索摘要。")

    with st.expander("手动查询企业资质与风险评分", expanded=False):
        st.caption("用于复查公司是否存在诈骗、培训贷、押金、欠薪、经营异常、失信等风险信号。")
        manual_company = st.text_input("企业名称", placeholder="例如：杭州某某信息技术有限公司")
        if st.button("查询企业风险", use_container_width=True, disabled=not bool(manual_company.strip())):
            with st.spinner("正在检索公开企业信息和风险摘要..."):
                st.session_state.company_risk_results[f"manual-{manual_company.strip()}"] = assess_company_risk(
                    manual_company.strip()
                )
        manual_key = f"manual-{manual_company.strip()}"
        if manual_key in st.session_state.company_risk_results:
            render_company_risk_result(st.session_state.company_risk_results[manual_key])

    st.divider()

    render_section("旧模板简历替换工具", "读取 DOCX 底层文字节点，只替换文字，不改模板格式、文本框、线条、颜色、图片和位置。")
    try:
        fixed_template_bytes = st.session_state.fixed_template_bytes or load_template_bytes()
        fixed_blocks = extract_template_blocks(fixed_template_bytes)
    except FixedTemplateError as exc:
        fixed_template_bytes = b""
        fixed_blocks = []
        st.error(str(exc))

    fixed_left, fixed_right = st.columns([1.05, 0.95], gap="large")
    with fixed_left:
        st.markdown("**使用上方简历内容**")
        fixed_resume_source = resume_text.strip()
        if fixed_resume_source:
            st.success("已读取上方“简历内容”，无需在此重复上传。")
        else:
            st.warning("上方“简历内容”为空，请先上传或粘贴简历。")
        st.text_area(
            "当前用于旧模板替换的简历内容",
            value=fixed_resume_source,
            height=320,
            disabled=True,
        )

    with fixed_right:
        st.markdown("**模板导入与状态**")
        fixed_template_upload = st.file_uploader(
            "上传自己的 DOCX 模板",
            type=["docx"],
            key="fixed_template_uploader",
            help="只支持 DOCX。页面不会显示模板原文。",
        )
        if fixed_template_upload is not None:
            current_signature = file_signature(fixed_template_upload)
            if current_signature != st.session_state.fixed_template_signature:
                st.session_state.fixed_template_bytes = fixed_template_upload.getvalue()
                st.session_state.fixed_template_name = fixed_template_upload.name
                st.session_state.fixed_template_signature = current_signature
                st.session_state.fixed_replacements_text = ""
                st.session_state.fixed_result_docx = b""
                set_agent_step(1)
                st.success("自定义模板已加载")
            fixed_template_bytes = st.session_state.fixed_template_bytes or load_template_bytes()
            fixed_blocks = extract_template_blocks(fixed_template_bytes)
        st.markdown(
            """
            <div class="risk-card">
              <strong>模板已加载</strong><br>
              <span style="color:#6B7280;font-size:12px;line-height:1.7;">
              页面不会显示模板中的任何原始文字。生成时只在后台读取文字节点，用于等长替换和保持版式。
              </span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.session_state.fixed_template_name:
            st.caption("当前使用自定义 DOCX 模板")
        else:
            st.caption("当前使用项目默认模板")
        st.metric("可替换文字块", len(fixed_blocks))
        st.caption("每段新文字会按原文字长度截断，尽量保持一页。")
        action_left, action_right = st.columns(2)
        with action_left:
            if st.button("恢复默认模板", use_container_width=True):
                st.session_state.fixed_template_bytes = b""
                st.session_state.fixed_template_name = ""
                st.session_state.fixed_template_signature = ""
                st.session_state.fixed_replacements_text = ""
                st.session_state.fixed_result_docx = b""
                set_agent_step(1)
                st.rerun()
        with action_right:
            if st.button("清空结果", use_container_width=True):
                st.session_state.fixed_replacements_text = ""
                st.session_state.fixed_result_docx = b""
                set_agent_step(1)
                st.rerun()

    fixed_role_col, fixed_city_col = st.columns(2)
    with fixed_role_col:
        fixed_target_role = st.text_input("旧模板目标岗位", value=target_role or "未指定")
    with fixed_city_col:
        fixed_city = st.text_input("旧模板目标城市", value=city or "未指定")

    if st.button("生成替换文字", type="primary", use_container_width=True):
        set_agent_step(5)
        if not fixed_resume_source.strip():
            st.error("请先在页面上方上传或粘贴原始简历。")
        elif not fixed_template_bytes or not fixed_blocks:
            st.error("模板不可用或没有识别到可替换文字块。")
        else:
            try:
                with st.status("正在生成等长替换文字...", expanded=True) as status:
                    st.write("读取模板文字块")
                    st.write("调用 AI 生成替换 JSON")
                    prompt = build_replacement_prompt(
                        fixed_resume_source,
                        fixed_target_role,
                        fixed_city,
                        fixed_blocks,
                    )
                    raw_replacements = call_agent(prompt)
                    replacements = normalize_replacements(raw_replacements, fixed_blocks)
                    st.session_state.fixed_replacements_text = json.dumps(
                        to_editable_replacements(replacements),
                        ensure_ascii=False,
                        indent=2,
                    )
                    st.session_state.fixed_result_docx = b""
                    set_agent_step(5)
                    status.update(label="替换文字已生成", state="complete", expanded=False)
            except (LLMConfigError, FixedTemplateError) as exc:
                st.error(str(exc))
            except Exception as exc:
                st.error("生成失败，请检查 API Key、模型或网络。")
                st.code(str(exc))

    if st.session_state.fixed_replacements_text:
        st.markdown("**检查和编辑替换 JSON**")
        st.caption("页面只显示 `index/new_text/max_chars`，不会显示模板原文字。可以手动修改 `new_text`，建议不要超过 `max_chars`。")
        st.text_area("替换 JSON", key="fixed_replacements_text", height=360)
        render_col, download_col = st.columns(2)
        with render_col:
            if st.button("生成 Word", use_container_width=True):
                try:
                    editable_replacements = json.loads(st.session_state.fixed_replacements_text)
                    replacements = merge_editable_replacements(editable_replacements, fixed_blocks)
                    result = render_fixed_template(replacements, fixed_template_bytes)
                    st.session_state.fixed_result_docx = result
                    set_agent_step(6)
                    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    path = save_output_file(f"{stamp}_fixed_template_resume.docx", result)
                    st.success(f"Word 已生成：{path}")
                except json.JSONDecodeError as exc:
                    st.error(f"替换 JSON 格式错误：{exc}")
                except Exception as exc:
                    st.error("生成 Word 失败。")
                    st.code(str(exc))
        with download_col:
            if st.session_state.fixed_result_docx:
                st.success("Word 文件已准备好，可以下载。")
            else:
                st.info("生成 Word 后下载按钮会变为可用。")
            st.download_button(
                "下载 Word",
                data=st.session_state.fixed_result_docx,
                file_name="旧模板替换生成简历.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                disabled=not bool(st.session_state.fixed_result_docx),
                use_container_width=True,
            )
    else:
        st.info("上传或粘贴简历后，点击“生成替换文字”。")

    st.divider()

    render_section("简历优化稿", "先手动调用 AI 生成简历正文，再预览、编辑并按需导出 Word / PDF。")
    st.caption("为节省 API token，开始分析不会自动生成简历优化稿。这里需要手动点击一次，后续 Word/PDF 导出只做本地文件生成。")
    generate_resume = st.button(
        "生成简历优化稿（调用 AI）",
        type="secondary",
        use_container_width=True,
        disabled=not bool(resume_text.strip() and target_role.strip() and city.strip()),
    )
    if generate_resume:
        try:
            loader = st.empty()
            loader.markdown(
                '<div class="agent-loader"><div class="agent-spinner"></div><span>Agent 正在结合真实岗位信息改写简历...</span></div>',
                unsafe_allow_html=True,
            )
            rewrite_prompt = build_resume_rewrite_prompt(
                resume_text=resume_text,
                target_role=target_role,
                city=city,
                crawled_jobs=st.session_state.crawled_jobs,
                hot_skills=st.session_state.hot_skills or recommend_hot_skills(target_role, resume_text),
            )
            set_agent_step(5)
            st.session_state.resume_rewrite_result = call_agent(rewrite_prompt)
            st.session_state.editable_resume_text = extract_resume_document(st.session_state.resume_rewrite_result)
            clear_resume_exports()
            loader.empty()
            append_usage_history(
                "简历优化稿",
                target_role,
                city,
                st.session_state.editable_resume_text.replace("\n", " ")[:160],
                st.session_state.resume_rewrite_result,
            )
            st.success("简历优化稿已生成。")
        except LLMConfigError as exc:
            st.error(str(exc))
            st.info("请检查左侧 API 登录信息。线上版本要求用户使用自己的 API Key。")
        except Exception as exc:
            st.error("生成简历优化稿失败，请检查 API 地址、模型名称、Key、网络状态或稍后重试。")
            st.code(str(exc))

    if st.session_state.resume_rewrite_result:
        if not st.session_state.editable_resume_text:
            st.session_state.editable_resume_text = extract_resume_document(st.session_state.resume_rewrite_result)

        tab_ai, tab_edit, tab_preview = st.tabs(["AI 完整结果", "编辑简历正文", "下载前预览"])
        with tab_ai:
            st.markdown(st.session_state.resume_rewrite_result)
        with tab_edit:
            st.text_area(
                "这里的内容会用于生成 Word / PDF，修改后再点击生成文件即可。",
                key="editable_resume_text",
                height=420,
            )
            if st.button("保存当前编辑到历史", use_container_width=True):
                clear_resume_exports()
                append_usage_history(
                    "手动编辑稿",
                    target_role,
                    city,
                    st.session_state.editable_resume_text.replace("\n", " ")[:160],
                    st.session_state.editable_resume_text,
                )
                st.success("当前编辑稿已保存到历史。")
        with tab_preview:
            st.markdown(st.session_state.editable_resume_text or "暂无可预览内容。")

        resume_document_text = st.session_state.editable_resume_text.strip() or extract_resume_document(st.session_state.resume_rewrite_result)
        template_source = st.session_state.imported_template_bytes
        template_source_name = st.session_state.imported_template_name
        if not template_source and st.session_state.uploaded_resume_name.lower().endswith(".docx"):
            template_source = st.session_state.uploaded_resume_bytes
            template_source_name = st.session_state.uploaded_resume_name

        template_description, template_text = get_template_context(
            resume_template,
            template_source,
            template_source_name,
        )
        if template_source_name.lower().endswith(".pdf"):
            st.info("PDF 模板的可识别文字会交给 AI 参考，生成新的 PDF 简历正文；不会再把生成内容追加到 PDF 模板后面。")
        elif template_source_name.lower().endswith(".docx"):
            st.info("Word 模板的可识别文字会交给 AI 参考；导出时会优先替换模板中的文字并保留样式、图片和版面结构。")

        col_md, col_docx, col_pdf = st.columns(3)
        with col_md:
            st.download_button(
                "下载 Markdown",
                data=resume_document_text.encode("utf-8"),
                file_name="optimized_resume.md",
                mime="text/markdown",
                use_container_width=True,
            )
        with col_docx:
            if st.button(
                "生成 Word 版本（调用 AI）",
                use_container_width=True,
            ):
                try:
                    with st.spinner("正在把模板和简历交给 API，生成 Word 版本正文..."):
                        prompt = build_template_resume_prompt(
                            resume_text=resume_document_text,
                            target_role=target_role,
                            city=city,
                            output_format="Word",
                            template_name=template_source_name or resume_template,
                            template_description=template_description,
                            template_text=template_text,
                            crawled_jobs=st.session_state.crawled_jobs,
                            hot_skills=st.session_state.hot_skills or recommend_hot_skills(target_role, resume_text),
                        )
                        word_result = call_agent(prompt)
                        st.session_state.word_resume_text = extract_resume_document(word_result)
                        st.session_state.resume_docx_data = build_docx(
                            st.session_state.word_resume_text,
                            title=f"{target_role}AI优化稿",
                            template_name=resume_template,
                        )
                        st.session_state.template_docx_data = b""
                        if template_source and template_source_name.lower().endswith(".docx"):
                            st.session_state.template_docx_data = build_docx_from_template(
                                template_source,
                                st.session_state.word_resume_text,
                                title=f"{target_role}AI优化稿",
                                template_name=resume_template,
                            )
                        st.session_state.resume_pdf_data = b""
                        st.session_state.template_pdf_data = b""
                        set_agent_step(6)
                    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    main_docx = st.session_state.template_docx_data or st.session_state.resume_docx_data
                    file_path = save_history_file(f"{stamp}_word_resume.docx", main_docx)
                    append_usage_history(
                        "Word生成",
                        target_role,
                        city,
                        "已调用 API 按模板生成 Word 版本简历。",
                        st.session_state.word_resume_text,
                        file_path,
                    )
                except Exception as exc:
                    st.error("Word 版本生成失败：API 当前不可用或额度已用尽。")
                    st.info("这次没有生成新的历史记录。请更换可用模型、补充额度，或稍后重试。")
                    st.code(str(exc))
        with col_pdf:
            if st.button(
                "生成 PDF 版本（调用 AI）",
                use_container_width=True,
            ):
                try:
                    with st.spinner("正在把模板和简历交给 API，生成 PDF 版本正文..."):
                        prompt = build_template_resume_prompt(
                            resume_text=resume_document_text,
                            target_role=target_role,
                            city=city,
                            output_format="PDF",
                            template_name=template_source_name or resume_template,
                            template_description=template_description,
                            template_text=template_text,
                            crawled_jobs=st.session_state.crawled_jobs,
                            hot_skills=st.session_state.hot_skills or recommend_hot_skills(target_role, resume_text),
                        )
                        pdf_result = call_agent(prompt)
                        st.session_state.pdf_resume_text = extract_resume_document(pdf_result)
                        st.session_state.resume_pdf_data = build_pdf(
                            st.session_state.pdf_resume_text,
                            title=f"{target_role}优化版简历",
                            template_name=resume_template,
                        )
                        st.session_state.resume_docx_data = b""
                        st.session_state.template_docx_data = b""
                        st.session_state.template_pdf_data = b""
                        set_agent_step(6)
                    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    file_path = save_history_file(f"{stamp}_pdf_resume.pdf", st.session_state.resume_pdf_data)
                    append_usage_history(
                        "PDF生成",
                        target_role,
                        city,
                        "已调用 API 按模板生成 PDF 版本简历。",
                        st.session_state.pdf_resume_text,
                        file_path,
                    )
                except Exception as exc:
                    st.error("PDF 版本生成失败：API 当前不可用或额度已用尽。")
                    st.info("这次没有生成新的历史记录。请更换可用模型、补充额度，或稍后重试。")
                    st.code(str(exc))

        if st.session_state.word_resume_text:
            st.markdown("**Word 下载前预览**")
            st.text_area(
                "编辑 Word 版本正文，修改后点击下方按钮刷新 Word 文件。",
                key="word_resume_text",
                height=360,
            )
            st.markdown(st.session_state.word_resume_text or "暂无可预览内容。")
            refresh_word, download_word = st.columns(2)
            with refresh_word:
                if st.button("应用编辑并刷新 Word 文件", use_container_width=True):
                    st.session_state.resume_docx_data = build_docx(
                        st.session_state.word_resume_text,
                        title=f"{target_role}优化版简历",
                        template_name=resume_template,
                    )
                    st.session_state.template_docx_data = b""
                    if template_source and template_source_name.lower().endswith(".docx"):
                        st.session_state.template_docx_data = build_docx_from_template(
                            template_source,
                            st.session_state.word_resume_text,
                            title=f"{target_role}AI优化稿",
                            template_name=resume_template,
                        )
                    set_agent_step(6)
                    st.success("Word 文件已按当前编辑内容刷新。")
            with download_word:
                word_data = st.session_state.template_docx_data or st.session_state.resume_docx_data
                st.download_button(
                    "下载 Word 版本",
                    data=word_data,
                    file_name="optimized_resume.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    use_container_width=True,
                    disabled=not bool(word_data),
                )

        if st.session_state.pdf_resume_text:
            st.markdown("**PDF 下载前预览**")
            st.text_area(
                "编辑 PDF 版本正文，修改后点击下方按钮刷新 PDF 文件。",
                key="pdf_resume_text",
                height=360,
            )
            refresh_pdf, download_pdf = st.columns(2)
            with refresh_pdf:
                if st.button("应用编辑并刷新 PDF 文件", use_container_width=True):
                    st.session_state.resume_pdf_data = build_pdf(
                        st.session_state.pdf_resume_text,
                        title=f"{target_role}优化版简历",
                        template_name=resume_template,
                    )
                    set_agent_step(6)
                    st.success("PDF 文件已按当前编辑内容刷新。")
            if st.session_state.resume_pdf_data:
                render_pdf_preview(st.session_state.resume_pdf_data)
            with download_pdf:
                st.download_button(
                    "下载 PDF 版本",
                    data=st.session_state.resume_pdf_data,
                    file_name="optimized_resume.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                    disabled=not bool(st.session_state.resume_pdf_data),
                )
    else:
        st.info("先点击上面的“生成简历优化稿（调用 AI）”，生成后再按需导出 Word 或 PDF。")

    render_section("分析结果", "展示 JD 匹配、投递建议、面试准备和简历优化方向。")

    if st.session_state.analysis_result:
        st.markdown(st.session_state.analysis_result)
        markdown_file = build_markdown_file(
            st.session_state.analysis_result,
            target_role,
            city,
            st.session_state.search_keywords,
            st.session_state.job_links,
            st.session_state.crawled_jobs,
            st.session_state.hot_skills,
            st.session_state.resume_rewrite_result,
        )
    else:
        st.info("填写简历和岗位 JD 后，点击“开始分析”查看结果。")
        markdown_file = build_markdown_file(
            "",
            target_role,
            city,
            build_search_keywords(target_role, city),
            build_job_links(target_role, city),
            [],
            recommend_hot_skills(target_role, resume_text),
            "",
        )

    st.download_button(
        "下载 Markdown 结果",
        data=markdown_file.encode("utf-8"),
        file_name="ai_job_agent_result.md",
        mime="text/markdown",
        use_container_width=True,
        disabled=not bool(st.session_state.analysis_result),
    )
    workflow_placeholder.markdown(build_workflow_html(get_agent_step()), unsafe_allow_html=True)


if __name__ == "__main__":
    main()
