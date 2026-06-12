SYSTEM_PROMPT = """你是一个务实、谨慎的 AI 求职助手 Agent。

你的任务是根据用户提供的简历、岗位 JD 和目标岗位方向，分析岗位匹配度，并给出可执行的求职建议。

重要原则：
1. 不要编造用户没有写过的技术、项目、实习或工作经历。
2. 如果简历信息不足，要明确说“简历中暂未体现”。
3. 建议要适合软件工程应届生，重点面向软件实施、售前技术支持、产品助理、客户成功、AI 工具应用助理等岗位。
4. 输出必须使用 Markdown，并且必须原样保留用户要求的 12 个二级标题。
5. 语气要真实、清楚、可复制到简历或求职材料中。
6. 评分要保守，不要为了鼓励而虚高。

你需要体现 Agent 思路：先理解任务，再提取岗位要求，再分析个人匹配度，最后生成行动建议。
"""


OUTPUT_TEMPLATE = """请严格按下面结构输出，不要删除、改名、合并任何标题：

## 一、岗位关键词

## 二、岗位核心要求

## 三、简历匹配优势

## 四、主要短板

## 五、匹配度评分

请给出 0-100 分，并解释原因。
评分参考：
- 80-100：高度匹配，建议优先投递
- 60-79：基本匹配，可以投递，但需要优化简历
- 40-59：匹配一般，除非岗位很感兴趣，否则不优先
- 0-39：不建议投递

## 六、是否建议投递

## 七、简历优化建议

## 八、HR 打招呼话术

## 九、面试准备问题

## 十、简历项目经历优化建议

## 十一、招聘搜索关键词

请给出 5-8 个适合去招聘网站搜索的关键词组合。

## 十二、针对该岗位的简历改写示例

请基于用户已经提供的信息，改写一段更适合该岗位的项目经历或个人优势。不要编造不存在的经历。
"""


def build_user_prompt(resume_text: str, jd_text: str, target_role: str) -> str:
    return f"""请分析下面这次求职匹配任务。

【目标岗位方向】
{target_role}

【我的简历内容】
{resume_text}

【岗位 JD】
{jd_text}

请按以下步骤分析：
1. 理解我想投递的岗位方向。
2. 从 JD 中提取硬技能、软能力、经验要求和工作场景。
3. 对照简历，找出真实匹配点和明显短板。
4. 给出匹配度评分和是否建议投递。
5. 生成简历优化建议、HR 打招呼话术、面试准备问题、项目经历优化建议、招聘搜索关键词和简历改写示例。

{OUTPUT_TEMPLATE}
"""


def build_resume_rewrite_prompt(
    resume_text: str,
    target_role: str,
    city: str,
    crawled_jobs: list[dict[str, str | int]],
    hot_skills: list[dict[str, str]],
) -> str:
    jobs_text = "\n\n".join(
        f"岗位：{job.get('title', '')}\n薪资：{job.get('salary', '')}\n地点：{job.get('location', '')}\n公司：{job.get('company', '')}\nJD摘要：{job.get('detail', '')}"
        for job in crawled_jobs[:5]
    ) or "暂未抓取到真实岗位，请根据目标岗位方向进行优化。"
    skills_text = "\n".join(
        f"- {item['skill']}（{item['status']}）：{item['reason']}"
        for item in hot_skills
    )

    return f"""请根据我的原始简历、目标岗位方向、目标城市、真实招聘岗位信息和热门能力标签，生成一版更适合投递的简历优化稿。

【目标岗位方向】
{target_role}

【目标城市】
{city}

【我的原始简历】
{resume_text}

【真实招聘岗位信息】
{jobs_text}

【热门能力标签】
{skills_text}

请严格遵守：
1. 不要编造不存在的学校、实习、公司、证书、比赛、项目或技术能力。
2. 可以优化表达，但必须基于原始简历已有事实。
3. 如果某些能力简历中没有体现，请写成“建议补充”，不要直接写进成品经历。
4. 输出 Markdown，方便复制到 Word。

请按下面结构输出：

## 一、简历定位

## 二、建议保留和强化的内容

## 三、建议弱化或删除的内容

## 四、优化后的个人优势

## 五、优化后的技能描述

## 六、优化后的项目经历写法

## 七、针对真实岗位的关键词补强

## 八、不能夸大的内容提醒

## 九、可直接复制的简历版本
"""


def build_template_resume_prompt(
    resume_text: str,
    target_role: str,
    city: str,
    output_format: str,
    template_name: str,
    template_description: str,
    template_text: str,
    crawled_jobs: list[dict[str, str | int]],
    hot_skills: list[dict[str, str]],
) -> str:
    jobs_text = "\n\n".join(
        f"岗位：{job.get('title', '')}\n薪资：{job.get('salary', '')}\n地点：{job.get('location', '')}\n公司：{job.get('company', '')}\nJD摘要：{job.get('detail', '')}"
        for job in crawled_jobs[:5]
    ) or "暂未抓取到真实岗位，请根据目标岗位方向进行优化。"
    skills_text = "\n".join(
        f"- {item['skill']}（{item['status']}）：{item['reason']}"
        for item in hot_skills
    ) or "暂无热门能力标签。"
    template_text = template_text.strip() or "未上传外部模板，请参考内置模板说明生成。"

    return f"""请把我的原始简历改写成一份适合导出为 {output_format} 的正式简历正文。

你必须同时参考【模板信息】和【模板可识别文字】，尽量沿用模板里的栏目顺序、信息密度、标题层级和表达长度。
如果模板像一页简历，就输出一页简历风格；如果模板更偏表格/分区，就按相似分区组织内容。
模板可识别文字通常会按模板中的文字块顺序给出，你要尽量让输出的分段数量、长短和顺序接近模板，方便程序把文字替换回模板中的原位置。

【目标岗位方向】
{target_role}

【目标城市】
{city}

【输出格式】
{output_format}

【模板名称】
{template_name}

【模板说明】
{template_description}

【模板可识别文字】
{template_text}

【我的原始简历】
{resume_text}

【真实招聘岗位信息】
{jobs_text}

【热门能力标签】
{skills_text}

严格要求：
1. 不要编造不存在的学校、公司、实习、证书、比赛、项目、技术能力或时间。
2. 必须基于原始简历已有事实进行改写，可以优化措辞、调整栏目顺序、合并重复内容。
3. 如果模板里有姓名、电话、邮箱、学校等字段，但原简历没有对应信息，请保留为“待补充”，不要编造。
4. 不要输出解释、分析过程、注意事项或代码块。
5. 只输出最终简历正文，用 Markdown 表达标题、项目符号和分区，方便页面预览和生成 {output_format} 文件。
6. 内容要尽量贴合模板结构，不要把一大段文本直接堆在模板后面。
7. 如果模板字段较短，输出也要短；如果模板是分栏或表格风格，输出要更像短字段和短项目符号，而不是长段落。
"""
