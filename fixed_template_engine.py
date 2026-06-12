from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile


TEMPLATE_PATH = Path(__file__).resolve().parent / "templates" / "default_resume_template.docx"

WORD_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
ET.register_namespace("w", WORD_NS["w"])


@dataclass
class TextBlock:
    index: int
    text: str
    max_chars: int


class FixedTemplateError(RuntimeError):
    pass


def load_template_bytes() -> bytes:
    if not TEMPLATE_PATH.exists():
        raise FixedTemplateError("默认模板不存在，请确认 templates/default_resume_template.docx 已存在。")
    return TEMPLATE_PATH.read_bytes()


def extract_template_blocks(template_bytes: bytes | None = None) -> list[TextBlock]:
    data = template_bytes or load_template_bytes()
    blocks: list[TextBlock] = []
    seen: set[str] = set()
    for text in _iter_docx_paragraph_text(data):
        cleaned = _clean_text(text)
        if not cleaned:
            continue
        if len(cleaned) > 160:
            continue
        if cleaned in seen:
            continue
        seen.add(cleaned)
        blocks.append(TextBlock(len(blocks) + 1, cleaned, max(4, len(cleaned))))
    return blocks


def build_replacement_prompt(
    resume_text: str,
    target_role: str,
    city: str,
    blocks: list[TextBlock],
) -> str:
    block_payload = [
        {"index": block.index, "old_text": block.text, "max_chars": block.max_chars}
        for block in blocks
    ]
    return f"""你是简历旧模板文字替换助手。请根据【原始简历】和【模板原文字块】生成替换文字。

目标岗位：{target_role or "未指定"}
目标城市：{city or "未指定"}

严格要求：
1. 只输出 JSON 数组，不要 Markdown，不要解释。
2. 数组每项必须是 {{"index": 数字, "new_text": "替换文字"}}。
3. 必须保留模板原来的版块数量和顺序，不要新增 index。
4. 每个 new_text 不能超过对应 max_chars；为了保持一页，尽量比原文更短。
5. 不得编造原始简历没有的学校、公司、证书、项目、时间、经历或技能。
6. 如果原简历没有对应信息，保留原字段含义并写“待补充”或用更通用但真实的表达。
7. 姓名、电话、邮箱、现居等基础信息如果原简历有就替换，没有就写“待补充”，不要编造。
8. 标题类文字如“实习经历”“项目经历”“核心能力”“教育背景”保持不变。
9. 输出文字用于替换 Word 模板原文字，不能出现换行、Markdown 符号或项目符号前缀。

模板原文字块：
{json.dumps(block_payload, ensure_ascii=False, indent=2)}

原始简历：
{resume_text}
"""


def normalize_replacements(raw_text: str, blocks: list[TextBlock]) -> list[dict]:
    items = _parse_json_array(raw_text)
    by_index = {
        int(item.get("index")): str(item.get("new_text", "")).strip()
        for item in items
        if isinstance(item, dict) and item.get("index")
    }
    replacements = []
    for block in blocks:
        new_text = by_index.get(block.index, block.text)
        replacements.append(
            {
                "index": block.index,
                "old_text": block.text,
                "new_text": _fit_text(new_text, block.max_chars),
                "max_chars": block.max_chars,
            }
        )
    return replacements


def to_editable_replacements(replacements: list[dict]) -> list[dict]:
    return [
        {
            "index": int(item.get("index", index + 1)),
            "new_text": str(item.get("new_text", "")),
            "max_chars": int(item.get("max_chars", len(str(item.get("new_text", ""))) or 4)),
        }
        for index, item in enumerate(replacements)
    ]


def merge_editable_replacements(editable_items: list[dict], blocks: list[TextBlock]) -> list[dict]:
    by_index = {
        int(item.get("index")): str(item.get("new_text", "")).strip()
        for item in editable_items
        if isinstance(item, dict) and item.get("index")
    }
    merged = []
    for block in blocks:
        new_text = by_index.get(block.index, block.text)
        merged.append(
            {
                "index": block.index,
                "old_text": block.text,
                "new_text": _fit_text(new_text, block.max_chars),
                "max_chars": block.max_chars,
            }
        )
    return merged


def render_fixed_template(replacements: list[dict], template_bytes: bytes | None = None) -> bytes:
    data = template_bytes or load_template_bytes()
    mapping = {
        str(item.get("old_text", "")).strip(): str(item.get("new_text", "")).strip()
        for item in replacements
        if str(item.get("old_text", "")).strip()
    }
    output = BytesIO()
    xml_cache: dict[str, bytes] = {}
    with ZipFile(BytesIO(data), "r") as zin:
        names = [
            name
            for name in zin.namelist()
            if name.startswith("word/") and name.endswith(".xml")
        ]
        for name in names:
            raw = zin.read(name)
            try:
                root = ET.fromstring(raw)
            except ET.ParseError:
                continue
            changed = False
            for paragraph in root.findall(".//w:p", WORD_NS):
                nodes = paragraph.findall(".//w:t", WORD_NS)
                if not nodes:
                    continue
                original = _clean_text("".join(node.text or "" for node in nodes))
                replacement = mapping.get(original)
                if replacement is None:
                    continue
                nodes[0].text = replacement
                for node in nodes[1:]:
                    node.text = ""
                changed = True
            if changed:
                xml_cache[name] = ET.tostring(root, encoding="utf-8", xml_declaration=True)

        with ZipFile(output, "w", ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                zout.writestr(item, xml_cache.get(item.filename, zin.read(item.filename)))
    return output.getvalue()


def _iter_docx_paragraph_text(data: bytes):
    with ZipFile(BytesIO(data), "r") as zin:
        for name in zin.namelist():
            if not (name.startswith("word/") and name.endswith(".xml")):
                continue
            try:
                root = ET.fromstring(zin.read(name))
            except ET.ParseError:
                continue
            for paragraph in root.findall(".//w:p", WORD_NS):
                nodes = paragraph.findall(".//w:t", WORD_NS)
                text = "".join(node.text or "" for node in nodes)
                if text.strip():
                    yield text


def _parse_json_array(text: str) -> list:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\[.*\]", cleaned, flags=re.S)
        if not match:
            raise FixedTemplateError("AI 没有返回 JSON 数组。")
        data = json.loads(match.group(0))
    if not isinstance(data, list):
        raise FixedTemplateError("AI 返回的不是 JSON 数组。")
    return data


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _fit_text(text: str, max_chars: int) -> str:
    cleaned = _clean_text(text)
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max(1, max_chars - 1)].rstrip() + "…"
