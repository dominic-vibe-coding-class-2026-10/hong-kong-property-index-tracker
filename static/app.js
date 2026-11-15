const I18N = {
  en: {
    eyebrow: "One site with patterns, many sites with Firecrawl",
    title: "Hong Kong property indices",
    insight: "Comparison insight",
    latest: "Latest readings",
    chart: "Centa-City Leading Index history",
    evidence: "Collection evidence",
    download: "Download dataset",
    asOf: "As of",
    points: "points",
    readings: "readings stored",
    emptyInsight: "The comparison insight appears after the pipeline calls Ollama Cloud.",
    emptyChart: "No Centa-City Leading Index history yet.",
    emptyEvidence: "No collection runs yet.",
    generated: "Generated",
    provisional: "provisional",
    source: "Source",
    up: "up",
    down: "down",
    paths: {
      history_api: "History API",
      playwright_weekly: "Weekly page update",
      tavily_firecrawl: "Tavily + Firecrawl",
      playwright_fallback: "Playwright fallback",
      official_csv: "Official file",
    },
    status: { ok: "Succeeded", fallback: "Fallback", fail: "Failed" },
    updateNote: "Data is fetched, processed, and updated by AI automatically every week.",
  },
  "zh-Hant": {
    eyebrow: "單一網站靠規律，多個網站靠 Firecrawl",
    title: "香港樓價指數",
    insight: "比較解讀",
    latest: "最新讀數",
    chart: "中原城市領先指數歷史走勢",
    evidence: "採集紀錄",
    download: "下載數據",
    asOf: "截至",
    points: "點",
    readings: "筆已入庫",
    emptyInsight: "比較解讀會在資料管道呼叫 Ollama Cloud 之後顯示。",
    emptyChart: "尚未有中原城市領先指數歷史數據。",
    emptyEvidence: "尚未有採集紀錄。",
    generated: "生成時間",
    provisional: "暫定",
    source: "來源",
    up: "上升",
    down: "下跌",
    paths: {
      history_api: "歷史接口",
      playwright_weekly: "每週頁面更新",
      tavily_firecrawl: "Tavily + Firecrawl",
      playwright_fallback: "Playwright 後備",
      official_csv: "官方檔案",
    },
    status: { ok: "成功", fallback: "改用後備", fail: "失敗" },
    updateNote: "數據由 AI 每週自動擷取、處理並更新。",
  },
};

const storedLang = localStorage.getItem("hk-index-lang");
const state = {
  lang: storedLang || ((navigator.language || "").toLowerCase().startsWith("zh") ? "zh-Hant" : "en"),
  data: null,
  chart: null,
};

if (state.lang !== "en" && state.lang !== "zh-Hant") state.lang = "en";

const $ = (id) => document.getElementById(id);

function t() {
  return I18N[state.lang];
}

function formatValue(value) {
  if (value == null) return "—";
  return Number(value).toLocaleString(state.lang === "zh-Hant" ? "zh-HK" : "en-HK", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function formatChange(change) {
  if (change == null) return "";
  const direction = change > 0 ? t().up : change < 0 ? t().down : "";
  const sign = change > 0 ? "+" : "";
  return `${sign}${change.toFixed(2)}% ${direction}`.trim();
}

function applyChrome() {
  const text = t();
  document.documentElement.lang = state.lang === "zh-Hant" ? "zh-Hant" : "en";
  document.title = text.title;
  $("eyebrow").textContent = text.eyebrow;
  $("title").textContent = text.title;
  $("insight-heading").textContent = text.insight;
  $("latest-heading").textContent = text.latest;
  $("chart-heading").textContent = text.chart;
  $("evidence-heading").textContent = text.evidence;
  $("update-note").textContent = text.updateNote;
  $("lang-en").setAttribute("aria-pressed", state.lang === "en" ? "true" : "false");
  $("lang-zh").setAttribute("aria-pressed", state.lang === "zh-Hant" ? "true" : "false");
}

function render() {
  applyChrome();
  const data = state.data;
  const text = t();
  if (!data) return;

  const insight = data.insights?.[state.lang] || data.insights?.en || "";
  $("insight-text").textContent = insight || text.emptyInsight;
  $("insight-at").textContent = data.insight_at ? `${text.generated} ${data.insight_at}` : "";

  const cards = $("cards");
  cards.replaceChildren();
  for (const series of data.series) {
    const name = state.lang === "zh-Hant" ? series.name_zh : series.name_en;
    const base = state.lang === "zh-Hant" ? series.base_zh : series.base_en;
    const article = document.createElement("article");
    article.className = "card";
    const changeClass = series.change_pct > 0 ? "up" : series.change_pct < 0 ? "down" : "";
    const provisional = series.note === "provisional" ? `<span class="badge">${text.provisional}</span>` : "";
    const pathLabel = text.paths[series.source_path] || series.source_path || "";
    article.innerHTML = `
      <h3>${name}</h3>
      <p class="value">${formatValue(series.latest_value)}</p>
      <p class="change ${changeClass}">${formatChange(series.change_pct)}${provisional}</p>
      <p class="meta">${text.asOf} ${series.period_label || "—"} · ${base}</p>
      <p class="meta">${series.count} ${text.readings}${pathLabel ? ` · ${pathLabel}` : ""}</p>
      <a class="source" href="${series.source_url}" target="_blank" rel="noreferrer">${text.source}</a>
      <a class="download" href="${series.download}">${text.download}</a>
    `;
    cards.append(article);
  }

  const ccl = data.series.find((series) => series.id === "ccl");
  $("chart-base").textContent = ccl ? (state.lang === "zh-Hant" ? ccl.base_zh : ccl.base_en) : "";
  drawChart(ccl);

  const list = $("evidence");
  list.replaceChildren();
  if (!data.evidence?.length) {
    const item = document.createElement("li");
    item.textContent = text.emptyEvidence;
    list.append(item);
    return;
  }
  for (const row of data.evidence) {
    const item = document.createElement("li");
    item.className = row.status;
    const status = document.createElement("span");
    status.className = "status";
    status.textContent = text.status[row.status] || row.status;
    item.append(status, ` ${row.created_at} · ${row.step}`);
    if (row.detail) {
      const detail = document.createElement("div");
      detail.textContent = row.detail;
      item.append(detail);
    }
    list.append(item);
  }
}

function drawChart(ccl) {
  const history = state.data.ccl_history || [];
  const canvas = $("chart");
  if (!history.length || typeof Chart === "undefined") {
    if (state.chart) {
      state.chart.destroy();
      state.chart = null;
    }
    return;
  }
  const name = state.lang === "zh-Hant" ? ccl.name_zh : ccl.name_en;
  const config = {
    type: "line",
    data: {
      labels: history.map((point) => point.date),
      datasets: [
        {
          label: name,
          data: history.map((point) => point.value),
          borderColor: "#9d2c2c",
          borderWidth: 1.6,
          pointRadius: 0,
          tension: 0.12,
          fill: true,
          backgroundColor: "rgba(157, 44, 44, 0.08)",
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { title: (items) => `${name} · ${items[0].label}` } },
      },
      scales: {
        x: {
          ticks: { maxTicksLimit: 8, color: "#6b645b" },
          grid: { display: false },
        },
        y: {
          ticks: { color: "#6b645b" },
          grid: { color: "#eadfd0" },
        },
      },
    },
  };
  if (state.chart) state.chart.destroy();
  state.chart = new Chart(canvas, config);
}

document.querySelectorAll(".lang button").forEach((button) => {
  button.addEventListener("click", () => {
    state.lang = button.dataset.lang;
    localStorage.setItem("hk-index-lang", state.lang);
    render();
  });
});

applyChrome();

fetch("/api/dashboard")
  .then((response) => response.json())
  .then((data) => {
    state.data = data;
    render();
  })
  .catch(() => {
    $("insight-text").textContent = "The dashboard could not load the local database.";
  });
