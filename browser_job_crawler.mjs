import { chromium } from "playwright";

const [, , roleArg = "软件实施", cityArg = "杭州", maxArg = "6"] = process.argv;
const role = roleArg.trim();
const city = cityArg.trim();
const maxJobs = Math.max(1, Number.parseInt(maxArg, 10) || 6);

const salaryPattern = /(\d+(\.\d+)?-\d+(\.\d+)?(千|万|万\/年)|\d+(\.\d+)?(千|万|万\/年)|面议)/;
const stopWords = new Set(["去聊聊", "投递"]);
const titlePattern = /(工程师|助理|顾问|专员|经理|运维|产品|实施|技术支持|客户成功)/;
const noisyTitlePattern = /(文档|五险|补贴|奖金|培训|保险|公积金|测试用例|回归测试|接口测试|性能测试)/;

function scoreJob(block) {
  let score = 40;
  const text = block.join(" ").toLowerCase();
  const title = block[0] || "";
  if (title.includes(role)) score += 25;
  if (title.includes("实施")) score += 18;
  if (title.includes("技术支持") || title.includes("客户成功") || title.includes("产品")) score += 10;
  if (title.includes("测试") || title.includes("开发")) score -= 12;
  for (const word of [role, city, "应届", "助理", "实习", "sql", "数据库", "文档", "用户培训", "项目管理", "需求"]) {
    if (word && text.includes(word.toLowerCase())) score += 6;
  }
  return Math.max(0, Math.min(95, score));
}

function parseJobs(text, searchUrl) {
  const lines = text
    .split(/\n+/)
    .map((line) => line.trim())
    .filter(Boolean);

  const jobs = [];
  for (let i = 0; i < lines.length; i += 1) {
    const title = lines[i];
    const near = lines.slice(i, i + 28);
    const hasRole = title.includes(role) || titlePattern.test(title);
    const looksLikeTitle = title.length <= 36 && titlePattern.test(title) && !noisyTitlePattern.test(title);
    const salaryIndex = near.findIndex((line, index) => index > 0 && salaryPattern.test(line));
    const cityIndex = near.findIndex((line, index) => index > 0 && line.includes(city));
    const endIndex = near.findIndex((line) => stopWords.has(line));

    if (!hasRole || !looksLikeTitle || salaryIndex < 0 || salaryIndex > 3 || cityIndex < 0 || cityIndex > 6 || endIndex < 0) {
      continue;
    }

    const block = near.slice(0, Math.max(endIndex, salaryIndex + 1));
    const salary = block.find((line) => salaryPattern.test(line)) || "";
    const location = block.find((line) => line.includes(city)) || "";
    const company =
      [...block]
        .reverse()
        .find((line) => /公司|集团|科技|信息|软件|有限|股份/.test(line) && !/民营|国企|外资|合资|上市|人$|计算机软件/.test(line)) || "";
    const tags = block
      .filter((line) => ![title, salary, location, company].includes(line))
      .filter((line) => !/回复|在线|刚刚|活跃/.test(line))
      .slice(0, 12);

    const key = `${title}-${company}-${salary}`;
    if (jobs.some((job) => job.key === key)) {
      continue;
    }

    jobs.push({
      key,
      title,
      platform: "前程无忧",
      url: searchUrl,
      salary,
      location,
      company,
      snippet: tags.join("、"),
      detail: block.join("\n"),
      match_score: scoreJob(block),
    });

    if (jobs.length >= maxJobs * 3) break;
  }

  return jobs
    .sort((a, b) => b.match_score - a.match_score)
    .slice(0, maxJobs)
    .map(({ key, ...job }) => job);
}

async function main() {
  const keyword = encodeURIComponent(`${city} ${role}`);
  const searchUrl = `https://we.51job.com/pc/search?keyword=${keyword}&searchType=2&sortType=0`;
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1366, height: 900 } });
  try {
    await page.goto(searchUrl, { waitUntil: "domcontentloaded", timeout: 60000 });
    await page.waitForTimeout(8000);
    let jobs = await page.evaluate(({ maxJobs, role, city }) => {
      function score(detail, title) {
        let value = 40;
        const text = detail.toLowerCase();
        if (title.includes(role)) value += 25;
        if (title.includes("实施")) value += 18;
        if (title.includes("技术支持") || title.includes("客户成功") || title.includes("产品")) value += 10;
        if (title.includes("测试") || title.includes("开发")) value -= 12;
        for (const word of [role, city, "应届", "助理", "实习", "sql", "数据库", "文档", "用户培训", "项目管理", "需求"]) {
          if (word && text.includes(word.toLowerCase())) value += 6;
        }
        return Math.max(0, Math.min(95, value));
      }

      const cards = Array.from(document.querySelectorAll(".joblist-item-job[sensorsdata]"));
      const jobs = [];
      const seen = new Set();
      for (const card of cards) {
        const sensorsRaw = card.getAttribute("sensorsdata") || "{}";
        let sensors = {};
        try {
          sensors = JSON.parse(sensorsRaw);
        } catch {
          sensors = {};
        }
        const title = card.querySelector(".jname")?.textContent?.trim() || sensors.jobTitle || "";
        const salary = card.querySelector(".sal")?.textContent?.trim() || sensors.jobSalary || "";
        const location = card.querySelector(".area")?.textContent?.trim() || sensors.jobArea || "";
        const companyBlock = card.querySelector(".joblist-item-cname, .cname, a[href*='co']")?.textContent?.trim() || "";
        const company = companyBlock.split("\n")[0]?.trim() || "";
        const tags = Array.from(card.querySelectorAll(".tag"))
          .map((tag) => tag.textContent.trim())
          .filter(Boolean)
          .slice(0, 14);
        const detail = card.innerText.trim();
        const jobId = sensors.jobId || "";
        const url = jobId ? `https://jobs.51job.com/all/${jobId}.html` : "";
        if (!title || !url) continue;
        if (city && location && !location.includes(city)) continue;
        if (city && !location && !detail.includes(city)) continue;
        const hasTarget = title.includes(role) || detail.includes(role) || title.includes("实施") || detail.includes("软件实施");
        if (!hasTarget) continue;
        const key = `${title}-${company}-${salary}`;
        if (seen.has(key)) continue;
        seen.add(key);
        jobs.push({
          title,
          platform: "前程无忧",
          url,
          salary,
          location,
          company,
          snippet: tags.join("、"),
          detail,
          match_score: score(detail, title),
        });
      }
      return jobs.sort((a, b) => b.match_score - a.match_score).slice(0, maxJobs);
    }, { maxJobs, role, city });
    if (!jobs.length) {
      const text = await page.locator("body").innerText({ timeout: 15000 });
      jobs = parseJobs(text, searchUrl);
    }
    process.stdout.write(JSON.stringify({ ok: true, source: "51job-playwright", jobs }, null, 2));
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  process.stdout.write(JSON.stringify({ ok: false, error: error.message, jobs: [] }, null, 2));
  process.exitCode = 1;
});
