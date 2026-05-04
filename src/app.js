const state = {
  events: [],
  clusters: [],
  recruitingPolicy: null,
  questions: [],
  dailyCount: 5,
  activeTrack: "全部",
  query: "",
};

const tagLabels = {
  "project-deep-dive": "项目深挖",
  rag: "RAG",
  memory: "记忆/上下文",
  "tool-calling": "工具调用",
  "agent-architecture": "Agent架构",
  "cost-latency": "成本/时延",
  algorithm: "手撕算法",
  backend: "后端基础",
  redis: "Redis",
  mysql: "MySQL",
  linux: "Linux",
  adb: "ADB",
  python: "Python",
  java: "Java",
  concurrency: "并发",
  automation: "自动化",
  "automation-framework": "自动化框架",
  "test-case-design": "测试用例",
  ci: "CI/CD",
  flaky: "稳定性治理",
  observability: "可观测/回放",
  "agent-vs-workflow": "Agent vs Workflow",
  langgraph: "LangGraph",
  "query-rewrite": "Query改写",
  "role-fit": "岗位匹配",
  rl: "强化学习",
  llm: "大模型",
  text2sql: "Text2SQL",
  recommendation: "推荐系统",
  paper: "论文",
  "product-sense": "产品视角",
  network: "网络",
  state: "状态系统",
  fullstack: "AI全栈",
  search: "搜索",
  process: "流程样本",
};

function badgeClass(track) {
  if (track.includes("测试")) return "test";
  if (track.includes("AI应用") || track.includes("大模型")) return "ai";
  if (track.includes("通用")) return "general";
  return "";
}

async function init() {
  const [eventsResponse, questionsResponse] = await Promise.all([
    fetch("./data/interview-events.json"),
    fetch("./data/daily-questions.json"),
  ]);
  const data = await eventsResponse.json();
  const questionData = await questionsResponse.json();
  state.events = data.events;
  state.clusters = data.derivedClusters || [];
  state.recruitingPolicy = data.recruitingPolicy || null;
  state.questions = questionData.questions || [];
  state.dailyCount = questionData.dailyCount || 5;
  document.getElementById("updatedAt").textContent = `更新：${data.updatedAt} / 题库：${questionData.updatedAt}`;

  renderFilters();
  renderMetrics();
  renderDailyQuestions();
  renderThemes();
  renderCards();
  renderQuality();

  document.getElementById("searchInput").addEventListener("input", (event) => {
    state.query = event.target.value.trim().toLowerCase();
    renderMetrics();
    renderDailyQuestions();
    renderThemes();
    renderCards();
  });
}

function getTracks() {
  return [
    "全部",
    ...Array.from(
      new Set([
        ...state.questions.map((question) => question.track),
        ...getDisplayEvents().map((event) => event.roleTrack),
      ]),
    ),
  ];
}

function renderFilters() {
  const root = document.getElementById("trackFilters");
  root.innerHTML = "";
  getTracks().forEach((track) => {
    const button = document.createElement("button");
    button.className = `chip ${state.activeTrack === track ? "active" : ""}`;
    button.textContent = track;
    button.addEventListener("click", () => {
      state.activeTrack = track;
      renderFilters();
      renderMetrics();
      renderDailyQuestions();
      renderThemes();
      renderCards();
    });
    root.appendChild(button);
  });
}

function filteredEvents() {
  return getDisplayEvents().filter((event) => {
    const trackMatch = state.activeTrack === "全部" || event.roleTrack === state.activeTrack;
    if (!trackMatch) return false;
    if (!state.query) return true;
    const haystack = JSON.stringify(event).toLowerCase();
    return haystack.includes(state.query);
  });
}

function filteredQuestions() {
  return state.questions
    .filter((question) => {
      const trackMatch = state.activeTrack === "全部" || question.track === state.activeTrack;
      if (!trackMatch) return false;
      if (!state.query) return true;
      return JSON.stringify(question).toLowerCase().includes(state.query);
    })
    .sort((a, b) => a.priority - b.priority || a.title.localeCompare(b.title, "zh-CN"));
}

function getDisplayEvents() {
  return state.events.filter(isIncludedRecruitingType);
}

function isIncludedRecruitingType(event) {
  if (event.recruitingType === "social" || event.recruitingType === "unspecified") {
    return true;
  }
  if (event.recruitingType === "excluded") {
    return false;
  }
  const markerText = `${event.title || ""} ${event.seniority || ""}`;
  return !/(实习|暑期|校招|秋招|春招|26秋招|2026届|27届)/.test(markerText);
}

function renderMetrics() {
  const root = document.getElementById("metrics");
  const events = filteredEvents();
  const questionCount = filteredQuestions().length;
  const hiddenCount = state.events.length - getDisplayEvents().length;
  const roundCount = events.reduce((sum, event) => sum + event.rounds.length, 0);
  const durations = events
    .flatMap((event) => event.rounds.map((round) => round.durationMin))
    .filter((duration) => typeof duration === "number");
  const average = durations.length
    ? Math.round(durations.reduce((sum, duration) => sum + duration, 0) / durations.length)
    : "待补";
  const twoRoundEvents = events.filter((event) => event.rounds.length >= 2).length;
  const highEvidence = events.filter((event) => event.evidenceLevel === "high").length;

  const cards = [
    ["匹配问题", questionCount, "每日推送问题池，按优先级排序"],
    ["保留流程样本", events.length, "仅社招或未说明招聘类型"],
    ["有标注时长均值", average === "待补" ? average : `${average}min`, "公开帖常漏写时长"],
    ["已隐藏流程样本", hiddenCount, `实习/暑期/校招/秋招已排除，当前轮次 ${roundCount}`],
  ];

  root.innerHTML = cards
    .map(
      ([label, value, hint]) => `
        <article class="metric">
          <span>${label}</span>
          <strong>${value}</strong>
          <p>${hint}</p>
        </article>
      `,
    )
    .join("");
}

function renderThemes() {
  const events = filteredEvents();
  const questions = filteredQuestions();
  const counts = new Map();
  events.forEach((event) => {
    event.tags.forEach((tag) => counts.set(tag, (counts.get(tag) || 0) + 1));
  });
  questions.forEach((question) => {
    question.tags.forEach((tag) => counts.set(tag, (counts.get(tag) || 0) + 1));
  });
  const top = Array.from(counts.entries()).sort((a, b) => b[1] - a[1]).slice(0, 9);
  const max = top[0]?.[1] || 1;

  document.getElementById("themeGrid").innerHTML = top
    .map(([tag, count]) => {
      const width = Math.max(18, Math.round((count / max) * 100));
      return `
        <article class="theme-card">
          <strong><span>${tagLabels[tag] || tag}</span><span>${count}</span></strong>
          <div class="bar" aria-hidden="true"><i style="--w: ${width}%"></i></div>
        </article>
      `;
    })
    .join("");
}

function renderDailyQuestions() {
  const questions = filteredQuestions().slice(0, state.dailyCount);
  const root = document.getElementById("dailyQuestions");
  document.getElementById("dailyCount").textContent = `${questions.length} / ${filteredQuestions().length} 条`;

  if (!questions.length) {
    root.innerHTML = `<div class="empty">没有匹配的今日问题。试试切回“全部”，或搜索 大模型、RAG、产品。</div>`;
    return;
  }

  root.innerHTML = questions
    .map((item, index) => {
      const answerLabel = item.sourceHasAnswer ? "原帖有答案" : "Agent 补答";
      const modeClass = item.sourceHasAnswer ? "source" : "agent";
      const codeBlock = item.code
        ? `<pre class="code-block"><code>${escapeHtml(item.code)}</code></pre>`
        : "";

      return `
        <article class="question-card">
          <div class="question-rank">${String(index + 1).padStart(2, "0")}</div>
          <div class="question-body">
            <div class="question-top">
              <div>
                <div class="question-title-row">
                  <h3>${item.title}</h3>
                  <span class="badge ${priorityClass(item.track)}">${item.track}</span>
                  <span class="answer-pill ${modeClass}">${answerLabel}</span>
                </div>
                <p class="question-text">${item.question}</p>
              </div>
              <a class="source-button" href="${item.sourceUrl}" target="_blank" rel="noreferrer">${item.sourcePlatform} 原帖</a>
            </div>
            ${
              item.sourceAnswerExcerpt
                ? `<div class="source-excerpt"><strong>原帖短摘</strong><span>${item.sourceAnswerExcerpt}</span></div>`
                : ""
            }
            <div class="answer-box">
              <strong>答案</strong>
              <p>${item.answer}</p>
              ${codeBlock}
            </div>
            <div class="question-footer">
              <span>${item.whyItMatters}</span>
              <div class="focus">${item.tags.map((tag) => `<span class="tag">${tag}</span>`).join("")}</div>
            </div>
          </div>
        </article>
      `;
    })
    .join("");
}

function priorityClass(track) {
  if (track === "AI测开") return "test";
  if (track === "AI产品经理") return "ai";
  if (track === "普通测试") return "general";
  return "";
}

function escapeHtml(value) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function renderCards() {
  const events = filteredEvents();
  document.getElementById("resultCount").textContent = `${events.length} 条`;
  const root = document.getElementById("eventCards");
  if (!events.length) {
    root.innerHTML = `<div class="empty">没有匹配的面经。换个关键词，比如 RAG、二面、pytest、Linux。</div>`;
    return;
  }

  root.innerHTML = events
    .map((event) => {
      const rounds = event.rounds
        .map(
          (round) => `
            <div class="round">
              <div class="round-head">
                <strong>${round.name}</strong>
                <span class="duration">${round.durationLabel}</span>
              </div>
              <div class="focus">
                ${round.focus.map((item) => `<span class="tag">${item}</span>`).join("")}
              </div>
              <ol class="questions">
                ${round.questions.map((question) => `<li>${question}</li>`).join("")}
              </ol>
            </div>
          `,
        )
        .join("");

      const takeaways = event.takeaways
        .map((item) => `<div class="takeaway">${item}</div>`)
        .join("");

      return `
        <article class="event-card">
          <div class="event-top">
            <div>
              <div class="event-title-row">
                <h3>${event.title}</h3>
                <span class="badge ${badgeClass(event.roleTrack)}">${event.roleTrack}</span>
              </div>
              <div class="meta">
                ${event.company} · ${event.seniority} · ${event.sourcePlatform} · ${event.sourceDate}
              </div>
            </div>
            <a class="source-button" href="${event.sourceUrl}" target="_blank" rel="noreferrer">来源</a>
          </div>
          <div class="rounds">${rounds}</div>
          <div class="takeaways">${takeaways}</div>
        </article>
      `;
    })
    .join("");
}

function renderQuality() {
  const root = document.getElementById("agentQuality");
  const cluster = state.clusters[0];
  if (!cluster) {
    root.innerHTML = "";
    return;
  }
  root.innerHTML = `
    <div>
      <h3>${cluster.name}</h3>
      <p>${cluster.summary}</p>
      <h3>面试信号</h3>
      <ul class="quality-list">
        ${cluster.signals.map((item) => `<li>${item}</li>`).join("")}
      </ul>
    </div>
    <div>
      <h3>准备清单</h3>
      <ul class="quality-list">
        ${cluster.prepare.map((item) => `<li>${item}</li>`).join("")}
      </ul>
    </div>
  `;
}

init().catch((error) => {
  document.body.innerHTML = `<pre>${error.stack || error.message}</pre>`;
});
