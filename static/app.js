const I18N = {
  en: {
    eyebrow: "One site with patterns, many sites with Firecrawl",
    title: "Hong Kong property indices · Dominic Yu",
    insight: "Comparison insight",
    latest: "Latest readings",
    evidence: "Collection evidence",
    download: "Download dataset",
    asOf: "As of",
    points: "points",
    readings: "readings stored",
    emptyInsight: "The comparison insight appears after the pipeline calls Ollama Cloud.",
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
      official_page: "Official page",
    },
    status: { ok: "Succeeded", fallback: "Fallback", fail: "Failed" },
    updateNote: "Data is fetched, processed, and updated by AI automatically every week.",
  },
  "zh-Hant": {
    eyebrow: "單一網站靠規律，多個網站靠 Firecrawl",
    title: "香港樓價指數 · Dominic Yu",
    insight: "比較解讀",
    latest: "最新讀數",
    evidence: "採集紀錄",
    download: "下載數據",
    asOf: "截至",
    points: "點",
    readings: "筆已入庫",
    emptyInsight: "比較解讀會在資料管道呼叫 Ollama Cloud 之後顯示。",
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
      official_page: "官方頁面",
    },
    status: { ok: "成功", fallback: "改用後備", fail: "失敗" },
    updateNote: "數據由 AI 每週自動擷取、處理並更新。",
  },
};

const storedLang = localStorage.getItem("hk-index-lang");
const state = {
  lang: storedLang || ((navigator.language || "").toLowerCase().startsWith("zh") ? "zh-Hant" : "en"),
  data: null,
  charts: {},
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

  try {
    renderCharts();
  } catch (err) {
    console.error(err);
  }

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

const SPARSE_LIMIT = 24;

function seriesName(series) {
  return state.lang === "zh-Hant" ? series.name_zh : series.name_en;
}

function historyTitle(name) {
  return state.lang === "zh-Hant" ? `${name}歷史走勢` : `${name} history`;
}

function emptyHistory(name) {
  return state.lang === "zh-Hant" ? `尚未有${name}歷史數據。` : `No ${name} history yet.`;
}

function chartPoints(series) {
  const history = Array.isArray(series.history) ? series.history : [];
  return history.filter((point) => {
    if (!point || point.value == null || point.value === "" || !point.date) return false;
    return Number.isFinite(Number(point.value));
  });
}

function isMonthly(series) {
  return series.frequency === "monthly";
}

function tooltipDate(point, monthly) {
  if (monthly) {
    const label = point.label || "";
    if (/^\d{4}-\d{2}$/.test(label)) return label;
    return String(point.date).slice(0, 7);
  }
  return point.date;
}

function axisDate(point, monthly, compact) {
  const date = String(point.date || "");
  if (monthly) return tooltipDate(point, true);
  if (compact && date.length >= 10) return date.slice(5);
  return date;
}

function destroyCharts() {
  for (const chart of Object.values(state.charts)) {
    chart.destroy();
  }
  state.charts = {};
}

function yScale(values, sparse) {
  const scale = {
    ticks: { color: "#6b645b" },
    grid: { color: "#eadfd0" },
  };
  if (!sparse || !values.length) return scale;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min;
  const pad = span === 0 ? Math.max(Math.abs(min) * 0.05, 1) : span * 0.25;
  scale.min = min - pad;
  scale.max = max + pad;
  return scale;
}

function textWidth(chart, text, bold) {
  const ctx = chart && chart.ctx;
  if (!ctx) return text.length * 8;
  const font = (typeof Chart !== "undefined" && Chart.defaults.font) || {};
  ctx.save();
  ctx.font = `${bold ? "bold " : ""}${font.size || 12}px ${font.family || "sans-serif"}`;
  const width = ctx.measureText(text).width;
  ctx.restore();
  return width;
}

function tooltipMaxWidth(chart) {
  const canvasWidth = chart && chart.canvas ? chart.canvas.clientWidth : 280;
  return Math.max(140, canvasWidth - 28);
}

function wrapText(chart, text, maxWidth) {
  const words = String(text).split(" ");
  const tokens = words.flatMap((word) => {
    if (textWidth(chart, word, true) <= maxWidth) return [word];
    const parts = [];
    let current = "";
    for (const char of word) {
      const next = current + char;
      if (current && textWidth(chart, next, true) > maxWidth) {
        parts.push(current);
        current = char;
      } else {
        current = next;
      }
    }
    if (current) parts.push(current);
    return parts;
  });
  const lines = [];
  let current = "";
  for (const token of tokens) {
    const next = current ? `${current} ${token}` : token;
    if (current && textWidth(chart, next, true) > maxWidth) {
      lines.push(current);
      current = token;
    } else {
      current = next;
    }
  }
  if (current) lines.push(current);
  return lines.length ? lines : [text];
}

function tooltipTitle(chart, name, date) {
  const single = `${name} · ${date}`;
  const maxWidth = tooltipMaxWidth(chart);
  if (textWidth(chart, single, true) <= maxWidth) return single;
  return [...wrapText(chart, name, maxWidth), date];
}

function chartConfig(name, points, monthly, sparse, compact) {
  const values = points.map((point) => Number(point.value));
  const tooltipDates = points.map((point) => tooltipDate(point, monthly));
  const showEveryTick = points.length > 0 && points.length <= 8;
  const dataset = {
    label: name,
    data: values,
    borderColor: "#9d2c2c",
    borderWidth: 1.6,
    pointRadius: sparse ? 3 : 0,
    tension: 0.12,
    fill: true,
    backgroundColor: "rgba(157, 44, 44, 0.08)",
  };
  if (sparse) {
    dataset.pointHoverRadius = 5;
    dataset.pointBackgroundColor = "#9d2c2c";
    dataset.pointBorderColor = "#fffdf8";
    dataset.pointBorderWidth = 1.5;
    dataset.pointHitRadius = 10;
  }
  return {
    type: "line",
    data: {
      labels: points.map((point) => axisDate(point, monthly, compact)),
      datasets: [dataset],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            title(items) {
              return tooltipTitle(this.chart, name, tooltipDates[items[0].dataIndex]);
            },
            label(item) {
              const value = item.formattedValue;
              const single = `${name}: ${value}`;
              if (textWidth(this.chart, single, false) <= tooltipMaxWidth(this.chart)) return single;
              return value;
            },
          },
        },
      },
      scales: {
        x: {
          ticks: {
            color: "#6b645b",
            maxTicksLimit: showEveryTick ? points.length : 8,
            autoSkip: !showEveryTick,
            maxRotation: showEveryTick && (compact || monthly) ? 0 : 50,
            minRotation: 0,
          },
          grid: { display: false },
        },
        y: yScale(values, sparse),
      },
    },
  };
}

function renderCharts() {
  destroyCharts();
  const root = $("charts");
  if (!root) return;
  root.replaceChildren();
  for (const series of state.data.series || []) {
    const name = seriesName(series);
    const base = state.lang === "zh-Hant" ? series.base_zh : series.base_en;
    const points = chartPoints(series);
    const section = document.createElement("section");
    section.className = "chart-panel";
    section.dataset.series = series.id;

    const head = document.createElement("div");
    head.className = "section-head";
    const heading = document.createElement("h2");
    heading.textContent = historyTitle(name);
    const baseEl = document.createElement("p");
    baseEl.className = "muted";
    baseEl.textContent = base || "";
    head.append(heading, baseEl);
    section.append(head);

    if (!points.length) {
      const empty = document.createElement("p");
      empty.className = "empty-chart";
      empty.textContent = emptyHistory(name);
      section.append(empty);
      root.append(section);
      continue;
    }
    if (typeof Chart === "undefined") {
      root.append(section);
      continue;
    }

    const monthly = isMonthly(series);
    const sparse = points.length <= SPARSE_LIMIT;
    const years = new Set(points.map((point) => String(point.date).slice(0, 4)));
    const compact = sparse && !monthly && years.size === 1;
    const wrap = document.createElement("div");
    wrap.className = "canvas-wrap";
    const canvas = document.createElement("canvas");
    canvas.id = `chart-${series.id}`;
    canvas.setAttribute("role", "img");
    canvas.setAttribute("aria-label", heading.textContent);
    wrap.append(canvas);
    section.append(wrap);
    root.append(section);
    try {
      state.charts[series.id] = new Chart(canvas, chartConfig(name, points, monthly, sparse, compact));
    } catch (err) {
      console.error(err);
      delete state.charts[series.id];
      wrap.remove();
      const empty = document.createElement("p");
      empty.className = "empty-chart";
      empty.textContent = emptyHistory(name);
      section.append(empty);
    }
  }
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
