const DATA_URL = "./data/dashboard-data.json";
const state = {
  data: null,
  filter: "all",
  query: "",
  sort: "pnl",
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

function money(value, precise = false) {
  const n = Number(value || 0);
  return (precise ? fmtMoney2 : fmtMoney).format(n);
}

function pct(value) {
  const n = Number(value || 0) * 100;
  return `${n >= 0 ? "+" : ""}${n.toFixed(1)}%`;
}

function signedMoney(value, precise = false) {
  const n = Number(value || 0);
  return `${n >= 0 ? "+" : ""}${money(n, precise)}`;
}

function clsFor(value) {
  return Number(value || 0) >= 0 ? "positive" : "negative";
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
    pnl: (a, b) => Number(b.total_bid_pnl || 0) - Number(a.total_bid_pnl || 0),
    return: (a, b) => Number(b.return_bid || 0) - Number(a.return_bid || 0),
    open: (a, b) => Number(b.open_positions || 0) - Number(a.open_positions || 0),
  };
  return rows.sort(sorters[state.sort] || sorters.pnl);
}

function strategiesForFilter(filter) {
  let rows = allStrategies();
  if (filter === "active") {
    rows = rows.filter((row) => row.status === "active");
  } else if (filter === "risk") {
    rows = rows.filter((row) => Number(row.total_bid_pnl || 0) < 0 || row.status === "waiting");
  } else if (filter !== "all") {
    rows = rows.filter((row) => row.platform === filter);
  }
  return rows;
}

function summarizeRows(rows) {
  const initial = rows.reduce((sum, row) => sum + Number(row.initial_capital || 0), 0);
  const equity = rows.reduce((sum, row) => sum + Number(row.equity_bid || 0), 0);
  const pnl = equity - initial;
  const open = rows.reduce((sum, row) => sum + Number(row.open_positions || 0), 0);
  const closed = rows.reduce((sum, row) => sum + Number(row.closed_positions || 0), 0);
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
  const summary = summarizeRows(strategiesForFilter(state.filter));
  document.getElementById("totalEquity").textContent = money(summary.equity);
  document.getElementById("totalPnl").textContent = signedMoney(summary.pnl);
  document.getElementById("totalPnl").className = clsFor(summary.pnl);
  document.getElementById("totalReturn").textContent = pct(summary.returnValue);
  document.getElementById("totalReturn").className = `metric-delta ${clsFor(summary.returnValue)}`;
  document.getElementById("openPositions").textContent = summary.open;
  document.getElementById("closedPositions").textContent = `${summary.closed} closed`;
  document.getElementById("strategyCount").textContent = summary.count;
  document.getElementById("activeStrategies").textContent = `${summary.active} active`;
  document.getElementById("markType").textContent = `${filterLabel()} - conservative bid marks`;
  document.getElementById("generatedAt").textContent = new Date(state.data.generated_at).toLocaleString();
  document.getElementById("visibilityBadge").textContent = `${state.data.visibility} snapshot`;
  document.getElementById("securityNote").textContent = state.data.security_note;
}

function platformRows() {
  const grouped = new Map();
  strategiesForFilter(state.filter).forEach((strategy) => {
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
    row.equity += Number(strategy.equity_bid || 0);
    row.pnl += Number(strategy.total_bid_pnl || 0);
    row.open += Number(strategy.open_positions || 0);
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
  const total = rows.reduce((sum, row) => sum + row.equity, 0) || 1;
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
    const length = (row.equity / total) * circumference;
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
          <span class="color-dot" style="background:${row.color}"></span>
          <div>
            <div class="breakdown-name">${row.name}</div>
            <div class="breakdown-meta">${row.mode} - ${row.open} open positions</div>
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
      const ret = Number(row.return_bid || 0);
      const progress = Math.max(1, Math.min(100, Math.abs(ret) * 350));
      return `
        <article class="strategy-card">
          <div class="strategy-topline">
            <div>
              <div class="strategy-title">${row.name}</div>
              <div class="strategy-type">${row.platform} - ${row.bot_type}</div>
            </div>
            <span class="status-pill ${row.status === "waiting" ? "waiting" : ""}">${row.status}</span>
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
          <p class="description">${row.description || "No description available."}</p>
          ${
            row.backtest && Object.keys(row.backtest).length
              ? `<p class="description">Backtest: CAGR ${row.backtest.cagr}, max DD ${row.backtest.max_dd}, Sharpe ${row.backtest.sharpe}.</p>`
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
                <td>${row.strategy}<br><span class="breakdown-meta">${row.platform}</span></td>
                <td class="question-cell">${row.question || ""}</td>
                <td>${row.side || ""}</td>
                <td>${money(row.cost, true)}</td>
                <td class="${clsFor(row.bid_pnl)}">${row.bid_pnl == null ? "N/A" : signedMoney(row.bid_pnl, true)}</td>
                <td>${row.entry_price ? row.entry_price.toFixed(3) : ""}</td>
                <td>${row.bid == null ? "" : `${row.bid.toFixed(3)} / ${row.ask.toFixed(3)}`}</td>
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
  const response = await fetch(`${DATA_URL}?t=${Date.now()}`);
  if (!response.ok) throw new Error(`Data load failed: ${response.status}`);
  state.data = await response.json();
  render();
}

document.querySelectorAll(".nav-button").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".nav-button").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    state.filter = button.dataset.filter;
    updateSummary();
    renderAllocationChart();
    renderStrategies();
    renderPositions();
  });
});

document.querySelectorAll(".segment").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".segment").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    state.sort = button.dataset.sort;
    renderStrategies();
    renderPositions();
  });
});

document.getElementById("searchInput").addEventListener("input", (event) => {
  state.query = event.target.value;
  renderStrategies();
  renderPositions();
});

document.getElementById("refreshButton").addEventListener("click", () => {
  loadData().catch((error) => {
    document.getElementById("strategyGrid").innerHTML = `<div class="empty-state">${error.message}</div>`;
  });
});

loadData().catch((error) => {
  document.getElementById("strategyGrid").innerHTML = `<div class="empty-state">${error.message}</div>`;
});
