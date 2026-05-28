const DATA_URL = "./data/dashboard-data.json";
const state = {
  data: null,
  filter: "all",
  query: "",
  sort: "pnl",
  loading: false,
};

const palette = ["#1e7b5b", "#365f91", "#a87526", "#2b7a78", "#7a5b9a"];

const fmtMoney = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});

const fmtMoney2 = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 2,
});

function num(value, fallback = 0) {
  const n = maybeNum(value);
  return n == null ? fallback : n;
}

function maybeNum(value) {
  if (value === null || value === undefined || value === "") return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function money(value, precise = false) {
  const n = maybeNum(value);
  if (n == null) return "N/A";
  return (precise ? fmtMoney2 : fmtMoney).format(n);
}

function pct(value) {
  const n = maybeNum(value);
  if (n == null) return "N/A";
  const percent = n * 100;
  const digits = Math.abs(percent) < 0.1 && percent !== 0 ? 2 : 1;
  return `${percent >= 0 ? "+" : ""}${percent.toFixed(digits)}%`;
}

function signedMoney(value, precise = false) {
  const n = maybeNum(value);
  if (n == null) return "N/A";
  return `${n >= 0 ? "+" : ""}${money(n, precise)}`;
}

function clsFor(value) {
  const n = maybeNum(value);
  if (n == null || n === 0) return "neutral";
  return n > 0 ? "positive" : "negative";
}

function esc(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function fmtPrice(value) {
  const n = maybeNum(value);
  return n == null ? "" : n.toFixed(3);
}

function fmtBidAsk(row) {
  const prefix = row.quote_kind && row.quote_kind !== "bid / ask" ? `${esc(row.quote_kind)}: ` : "";
  const bid = maybeNum(row.bid);
  const ask = maybeNum(row.ask);
  if (bid == null && ask == null) return row.mark_warning ? esc(row.mark_warning) : "";
  if (bid == null) return `${prefix}N/A / ${ask.toFixed(3)}`;
  if (ask == null) return `${prefix}${bid.toFixed(3)} / N/A`;
  return `${prefix}${bid.toFixed(3)} / ${ask.toFixed(3)}`;
}

function isPastEnd(row) {
  if (!row.end_date || row.status !== "open") return false;
  const end = new Date(row.end_date).getTime();
  const generated = state.data?.generated_at ? new Date(state.data.generated_at).getTime() : Date.now();
  return Number.isFinite(end) && end < generated;
}

function positionNeedsAttention(row) {
  return num(row.bid_pnl) < 0 || Boolean(row.mark_warning) || isPastEnd(row);
}

function allStrategies() {
  if (!state.data) return [];
  return state.data.groups.flatMap((group) => group.strategies.map((strategy) => ({ ...strategy, group })));
}

function filteredStrategies() {
  const query = state.query.trim().toLowerCase();
  let rows = strategiesForFilter(state.filter);
  if (query) {
    rows = rows.filter((row) =>
      [row.name, row.platform, row.bot_type, row.description].join(" ").toLowerCase().includes(query),
    );
  }
  const sorters = {
    pnl: (a, b) => num(b.total_bid_pnl) - num(a.total_bid_pnl),
    return: (a, b) => num(b.return_bid) - num(a.return_bid),
    open: (a, b) => num(b.open_positions) - num(a.open_positions),
  };
  return rows.sort(sorters[state.sort] || sorters.pnl);
}

function strategiesForFilter(filter) {
  let rows = allStrategies();
  if (filter === "active") {
    rows = rows.filter((row) => row.status === "active");
  } else if (filter === "risk") {
    rows = rows.filter(
      (row) => num(row.total_bid_pnl) < 0 || row.status === "waiting" || (row.positions || []).some(positionNeedsAttention),
    );
  } else if (filter !== "all") {
    rows = rows.filter((row) => row.platform === filter);
  }
  return rows;
}

function summarizeRows(rows) {
  const initial = rows.reduce((sum, row) => sum + num(row.initial_capital), 0);
  const equity = rows.reduce((sum, row) => sum + num(row.equity_bid), 0);
  const pnl = equity - initial;
  const open = rows.reduce((sum, row) => sum + num(row.open_positions), 0);
  const closed = rows.reduce((sum, row) => sum + num(row.closed_positions), 0);
  const active = rows.filter((row) => row.status === "active").length;
  return {
    initial,
    equity,
    pnl,
    returnValue: initial ? pnl / initial : 0,
    open,
    closed,
    active,
    count: rows.length,
  };
}

function filterLabel() {
  const labels = {
    all: "All Systems",
    active: "Active Strategies",
    risk: "Needs Attention",
  };
  return labels[state.filter] || state.filter;
}

function updateSummary() {
  const summary = summarizeRows(filteredStrategies());
  document.getElementById("totalEquity").textContent = money(summary.equity);
  document.getElementById("totalPnl").textContent = signedMoney(summary.pnl);
  document.getElementById("totalPnl").className = clsFor(summary.pnl);
  document.getElementById("totalReturn").textContent = pct(summary.returnValue);
  document.getElementById("totalReturn").className = `metric-delta ${clsFor(summary.returnValue)}`;
  document.getElementById("openPositions").textContent = summary.open;
  document.getElementById("closedPositions").textContent = `${summary.closed} closed`;
  document.getElementById("strategyCount").textContent = summary.count;
  document.getElementById("activeStrategies").textContent = `${summary.active} active`;
  const queryNote = state.query.trim() ? `, search: "${state.query.trim()}"` : "";
  document.getElementById("markType").textContent = `${filterLabel()}${queryNote} - bid marks where available`;
  const sourceTimes = (state.data.groups || [])
    .map((group) => group.updated_at || group.last_scan)
    .filter(Boolean)
    .map((value) => new Date(value))
    .filter((value) => Number.isFinite(value.getTime()));
  const oldestSource = sourceTimes.length ? new Date(Math.min(...sourceTimes.map((value) => value.getTime()))) : null;
  document.getElementById("generatedAt").textContent = oldestSource
    ? `Generated ${new Date(state.data.generated_at).toLocaleString()}\nOldest source ${oldestSource.toLocaleString()}`
    : `Generated ${new Date(state.data.generated_at).toLocaleString()}`;
  document.getElementById("visibilityBadge").textContent = `${state.data.visibility} snapshot`;
  document.getElementById("securityNote").textContent = state.data.security_note;
}

function platformRows() {
  const grouped = new Map();
  filteredStrategies().forEach((strategy) => {
    if (!grouped.has(strategy.platform)) {
      grouped.set(strategy.platform, {
        name: strategy.platform,
        mode: strategy.mode || "mixed",
        equity: 0,
        pnl: 0,
        open: 0,
      });
    }
    const row = grouped.get(strategy.platform);
    row.equity += num(strategy.equity_bid);
    row.pnl += num(strategy.total_bid_pnl);
    row.open += num(strategy.open_positions);
  });
  return Array.from(grouped.values()).map((row, index) => {
    return {
      ...row,
      color: palette[index % palette.length],
    };
  });
}

function renderAllocationChart() {
  const svg = document.getElementById("allocationChart");
  const rows = platformRows();
  const total = rows.reduce((sum, row) => sum + Math.max(0, row.equity), 0);
  const scaleTotal = total || 1;
  const radius = 82;
  const circumference = 2 * Math.PI * radius;
  let offset = 0;
  svg.innerHTML = "";
  const base = document.createElementNS("http://www.w3.org/2000/svg", "circle");
  base.setAttribute("cx", "120");
  base.setAttribute("cy", "120");
  base.setAttribute("r", radius);
  base.setAttribute("class", "donut-ring");
  base.setAttribute("stroke", "#e5eae4");
  svg.appendChild(base);

  rows.forEach((row) => {
    const segment = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    const length = (Math.max(0, row.equity) / scaleTotal) * circumference;
    segment.setAttribute("cx", "120");
    segment.setAttribute("cy", "120");
    segment.setAttribute("r", radius);
    segment.setAttribute("class", "donut-ring");
    segment.setAttribute("stroke", row.color);
    segment.setAttribute("stroke-dasharray", `${length} ${circumference - length}`);
    segment.setAttribute("stroke-dashoffset", -offset);
    segment.setAttribute("transform", "rotate(-90 120 120)");
    svg.appendChild(segment);
    offset += length;
  });

  const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
  label.setAttribute("x", "120");
  label.setAttribute("y", "114");
  label.setAttribute("text-anchor", "middle");
  label.setAttribute("class", "donut-label");
  label.textContent = money(total);
  svg.appendChild(label);

  const sub = document.createElementNS("http://www.w3.org/2000/svg", "text");
  sub.setAttribute("x", "120");
  sub.setAttribute("y", "137");
  sub.setAttribute("text-anchor", "middle");
  sub.setAttribute("class", "donut-sub");
  sub.textContent = "bid equity";
  svg.appendChild(sub);

  const breakdown = document.getElementById("platformBreakdown");
  if (!rows.length) {
    breakdown.innerHTML = `<div class="empty-state">No platform allocation for this filter.</div>`;
    return;
  }
  breakdown.innerHTML = rows
    .map(
      (row) => `
        <div class="breakdown-row">
          <span class="color-dot" style="background:${esc(row.color)}"></span>
          <div>
            <div class="breakdown-name">${esc(row.name)}</div>
            <div class="breakdown-meta">${esc(row.mode)} - ${row.open} open positions</div>
          </div>
          <strong>${money(row.equity)}</strong>
          <span class="${clsFor(row.pnl)}">${signedMoney(row.pnl)}</span>
        </div>
      `,
    )
    .join("");
}

function renderStrategies() {
  const rows = filteredStrategies();
  const grid = document.getElementById("strategyGrid");
  if (!rows.length) {
    grid.innerHTML = `<div class="empty-state">No strategies match the current filter.</div>`;
    return;
  }
  grid.innerHTML = rows
    .map((row) => {
      const ret = num(row.return_bid);
      const progress = Math.max(1, Math.min(100, Math.abs(ret) * 350));
      const negativePositions = (row.positions || []).filter(positionNeedsAttention).length;
      const statusClass = row.status === "waiting" ? "waiting" : "";
      return `
        <article class="strategy-card">
          <div class="strategy-topline">
            <div>
              <div class="strategy-title">${esc(row.name)}</div>
              <div class="strategy-type">${esc(row.platform)} - ${esc(row.bot_type)}</div>
            </div>
            <span class="status-pill ${statusClass}">${esc(row.status)}</span>
          </div>
          <div class="mini-metrics">
            <div class="mini-metric">
              <span>PnL</span>
              <strong class="${clsFor(row.total_bid_pnl)}">${signedMoney(row.total_bid_pnl)}</strong>
            </div>
            <div class="mini-metric">
              <span>Return</span>
              <strong class="${clsFor(row.return_bid)}">${pct(row.return_bid)}</strong>
            </div>
            <div class="mini-metric">
              <span>Open</span>
              <strong>${row.open_positions}</strong>
            </div>
          </div>
          <div class="spark" aria-hidden="true">
            <div class="spark-fill" style="width:${progress}%; background:${ret >= 0 ? "#1e7b5b" : "#b94a48"}"></div>
          </div>
          <p class="description">${esc(row.description || "No description available.")}</p>
          ${row.execution_model ? `<p class="description">Execution: ${esc(row.execution_model)}.</p>` : ""}
          ${negativePositions ? `<p class="description">${negativePositions} open row(s) need attention.</p>` : ""}
          ${
            row.backtest && Object.keys(row.backtest).length
              ? `<p class="description">Backtest: CAGR ${esc(row.backtest.cagr)}, max DD ${esc(row.backtest.max_dd)}, Sharpe ${esc(row.backtest.sharpe)}.</p>`
              : ""
          }
        </article>
      `;
    })
    .join("");
}

function renderPositions() {
  const strategies = filteredStrategies();
  const rows = strategies.flatMap((strategy) =>
    (strategy.positions || []).map((position) => ({
      ...position,
      strategy: strategy.name,
      platform: strategy.platform,
    })),
  );
  rows.sort((a, b) => num(a.bid_pnl, -Infinity) - num(b.bid_pnl, -Infinity));
  const target = document.getElementById("positionsTable");
  if (!rows.length) {
    target.innerHTML = `<div class="empty-state">No exported open positions for this filter.</div>`;
    return;
  }
  target.innerHTML = `
    <table>
      <thead>
        <tr>
          <th>Strategy</th>
          <th>Market / Asset</th>
          <th>Side</th>
          <th>Cost</th>
          <th>Bid PnL</th>
          <th>Entry</th>
          <th>Bid / Ask</th>
          <th>End</th>
        </tr>
      </thead>
      <tbody>
        ${rows
          .map(
            (row) => `
              <tr>
                <td>${esc(row.strategy)}<br><span class="breakdown-meta">${esc(row.platform)}</span></td>
                <td class="question-cell">${esc(row.question || "")}${row.mark_warning ? `<br><span class="warning-text">${esc(row.mark_warning)}</span>` : ""}${isPastEnd(row) ? `<br><span class="warning-text">Past listed end date; awaiting resolved close.</span>` : ""}</td>
                <td>${esc(row.side || "")}</td>
                <td>${money(row.cost, true)}</td>
                <td class="${clsFor(row.bid_pnl)}">${row.bid_pnl == null ? "N/A" : signedMoney(row.bid_pnl, true)}</td>
                <td>${fmtPrice(row.entry_price)}</td>
                <td>${fmtBidAsk(row)}</td>
                <td>${row.end_date ? new Date(row.end_date).toLocaleDateString() : ""}</td>
              </tr>
            `,
          )
          .join("")}
      </tbody>
    </table>
  `;
}

function render() {
  if (!state.data) return;
  updateSummary();
  renderAllocationChart();
  renderStrategies();
  renderPositions();
}

async function loadData() {
  if (state.loading) return;
  state.loading = true;
  const button = document.getElementById("refreshButton");
  if (button) button.disabled = true;
  try {
    const response = await fetch(`${DATA_URL}?t=${Date.now()}`);
    if (!response.ok) throw new Error(`Data load failed: ${response.status}`);
    state.data = await response.json();
    render();
  } finally {
    state.loading = false;
    if (button) button.disabled = false;
  }
}

document.querySelectorAll(".nav-button").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".nav-button").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    state.filter = button.dataset.filter;
    render();
  });
});

document.querySelectorAll(".segment").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".segment").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    state.sort = button.dataset.sort;
    render();
  });
});

document.getElementById("searchInput").addEventListener("input", (event) => {
  state.query = event.target.value;
  render();
});

document.getElementById("refreshButton").addEventListener("click", () => {
  loadData().catch((error) => {
    document.getElementById("strategyGrid").innerHTML = `<div class="empty-state">${esc(error.message)}</div>`;
  });
});

loadData().catch((error) => {
  document.getElementById("strategyGrid").innerHTML = `<div class="empty-state">${esc(error.message)}</div>`;
});
