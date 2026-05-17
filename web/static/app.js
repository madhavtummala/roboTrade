const BUCKET_NAMES = ["accumulate", "sell"];
const MAX_AMOUNT = 100;
const WHEEL_STEP = 5;
const GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5));

const ENABLED_COLORS = {
  accumulate: "#024c4a",
  sell: "#7a3800",
};

const DISABLED_COLORS = {
  accumulate: "#c8cfd3",
  sell: "#d1cfc7",
};

const state = {
  status: null,
  account: null,
  universe: [],
  controls: null,
  dca: null,
  selected: null,
  layout: null,
  layoutKey: "",
  nodes: [],
  nodesById: new Map(),
  simulations: {},
  boundaryTimer: null,
  draft: null,
  invalidNodes: [],
  historyPayload: null,
};

const $ = (selector) => document.querySelector(selector);

function showToast(message) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.classList.add("show");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => toast.classList.remove("show"), 2400);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || `Request failed: ${response.status}`);
  return payload;
}

function money(value, digits = 0) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "--";
  return Number(value).toLocaleString(undefined, {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: digits,
  });
}

function signedMoney(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "--";
  return `${Number(value) > 0 ? "+" : ""}${money(value)}`;
}

function num(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "--";
  return Number(value).toFixed(digits);
}

function valueClass(value) {
  const parsed = Number(value);
  if (!parsed || Number.isNaN(parsed)) return "";
  return parsed > 0 ? "positive" : "negative";
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function isDcaEnabled() {
  return Boolean(state.dca?.plan?.enabled);
}

function bucketColor(bucketName) {
  return isDcaEnabled() ? ENABLED_COLORS[bucketName] : DISABLED_COLORS[bucketName];
}

function nodeId(bucketName, symbol) {
  return `${bucketName}:${symbol}`;
}

function bucketItems(bucket) {
  return state.dca?.plan?.[bucket]?.items || [];
}

function positionOrNull(position) {
  if (!position || typeof position !== "object") return null;
  return {
    x: clamp(Number(position.x || 0), -1, 1),
    y: clamp(Number(position.y || 0), -1, 1),
  };
}

function setBucketItems(bucket, items) {
  state.dca.plan[bucket].items = items.map((item) => {
    const sanitized = {
      ...item,
      amount: clamp(Number(item.amount || 0), 0, MAX_AMOUNT),
    };
    const position = positionOrNull(item.position);
    if (position) sanitized.position = position;
    return sanitized;
  });
  state.dca.plan[bucket].amount = state.dca.plan[bucket].items.reduce(
    (total, item) => total + Number(item.amount || 0),
    0,
  );
}

function assignedSymbols() {
  return new Set(BUCKET_NAMES.flatMap((bucket) => bucketItems(bucket).map((item) => item.symbol)));
}

function itemRadius(amount) {
  return 18 + Math.sqrt(clamp(amount, 0, MAX_AMOUNT)) * 3.45;
}

function calculateLayout() {
  const svg = $("#bubbleBoard");
  const width = svg.clientWidth || 1200;
  const height = svg.clientHeight || 720;
  const stacked = width < 760;
  const baseR = stacked ? Math.min(width * 0.35, height * 0.19, 210) : Math.min(width * 0.2, height * 0.36, 292);
  const maxR = stacked ? Math.min(width * 0.43, height * 0.24, 260) : Math.min(width * 0.27, height * 0.44, 365);
  const nextKey = `${Math.round(width)}:${Math.round(height)}:${stacked}`;
  const changed = nextKey !== state.layoutKey;

  state.layoutKey = nextKey;
  state.layout = {
    width,
    height,
    changed,
    stacked,
    buckets: stacked
      ? {
        accumulate: { cx: width / 2, cy: height * 0.27, r: baseR, baseR, maxR, label: "BUY" },
        sell: { cx: width / 2, cy: height * 0.72, r: baseR, baseR, maxR, label: "SELL" },
      }
      : {
        accumulate: { cx: width * 0.29, cy: height * 0.51, r: baseR, baseR, maxR, label: "BUY" },
        sell: { cx: width * 0.71, cy: height * 0.51, r: baseR, baseR, maxR, label: "SELL" },
      },
  };
}

function fitBucketRadii() {
  BUCKET_NAMES.forEach((bucketName) => {
    const bucket = state.layout.buckets[bucketName];
    const areaRadius = Math.sqrt(
      bucketItems(bucketName).reduce((sum, item) => sum + (itemRadius(item.amount) + 12) ** 2, 0),
    );
    bucket.r = clamp(Math.max(bucket.baseR, areaRadius * 1.22 + 42), bucket.baseR, bucket.maxR);
  });
}

function fallbackPosition(index, count, bucketName) {
  if (count <= 1) return { x: 0, y: 0 };
  const ring = Math.sqrt((index + 1) / (count + 1));
  const angle = index * GOLDEN_ANGLE + (bucketName === "sell" ? 0.9 : 0);
  return {
    x: Math.cos(angle) * ring * 0.68,
    y: Math.sin(angle) * ring * 0.68,
  };
}

function pointFromPosition(position, bucket, radius) {
  const usable = Math.max(bucket.r - radius - 18, 1);
  return {
    x: bucket.cx + clamp(position.x, -1, 1) * usable,
    y: bucket.cy + clamp(position.y, -1, 1) * usable,
  };
}

function pointToPosition(point, bucket, radius) {
  const usable = Math.max(bucket.r - radius - 18, 1);
  return {
    x: clamp((point.x - bucket.cx) / usable, -1, 1),
    y: clamp((point.y - bucket.cy) / usable, -1, 1),
  };
}

function clampPointToBucket(point, bucketName, radius) {
  const bucket = state.layout.buckets[bucketName];
  const dx = point.x - bucket.cx;
  const dy = point.y - bucket.cy;
  const maxDistance = Math.max(bucket.r - radius - 18, 1);
  const currentDistance = Math.hypot(dx, dy);
  if (currentDistance <= maxDistance) return { x: point.x, y: point.y };
  const scale = maxDistance / Math.max(currentDistance, 1);
  return {
    x: bucket.cx + dx * scale,
    y: bucket.cy + dy * scale,
  };
}

function distance(point, bucket) {
  return Math.hypot(point.x - bucket.cx, point.y - bucket.cy);
}

function nearestBucket(point) {
  const buckets = state.layout.buckets;
  return distance(point, buckets.accumulate) <= distance(point, buckets.sell) ? "accumulate" : "sell";
}

function bucketAtPoint(point) {
  const bucketName = nearestBucket(point);
  const bucket = state.layout.buckets[bucketName];
  return distance(point, bucket) <= bucket.r + 44 ? bucketName : null;
}

function buildNodes() {
  const nextNodesById = new Map();
  const nodes = [];

  BUCKET_NAMES.forEach((bucketName) => {
    const bucket = state.layout.buckets[bucketName];
    const items = bucketItems(bucketName);
    items.forEach((item, index) => {
      const id = nodeId(bucketName, item.symbol);
      const radius = itemRadius(item.amount);
      const previous = state.layout.changed ? null : state.nodesById.get(id);
      const stored = positionOrNull(item.position) || fallbackPosition(index, items.length, bucketName);
      const point = previous || pointFromPosition(stored, bucket, radius);
      const clamped = clampPointToBucket(point, bucketName, radius);
      const node = {
        id,
        symbol: item.symbol,
        name: item.name,
        amount: clamp(Number(item.amount || 0), 0, MAX_AMOUNT),
        bucketName,
        radius,
        x: clamped.x,
        y: clamped.y,
        targetBucket: bucketName,
      };
      nodes.push(node);
      nextNodesById.set(id, node);
    });
  });

  state.nodes = nodes;
  state.nodesById = nextNodesById;
}

function findItem(bucketName, symbol) {
  return bucketItems(bucketName).find((item) => item.symbol === symbol);
}

function applyNodeToItem(node) {
  if (!state.layout) return;
  const item = findItem(node.bucketName, node.symbol);
  if (!item) return;
  const bucket = state.layout.buckets[node.bucketName];
  const clamped = clampPointToBucket({ x: node.x, y: node.y }, node.bucketName, node.radius);
  node.x = clamped.x;
  node.y = clamped.y;
  item.amount = clamp(node.amount, 0, MAX_AMOUNT);
  item.position = pointToPosition(clamped, bucket, node.radius);
  setBucketItems(node.bucketName, bucketItems(node.bucketName));
}

function syncNodePositions() {
  if (!state.layout) return;
  state.nodes.forEach(applyNodeToItem);
}

function angleDelta(a, b) {
  return Math.atan2(Math.sin(a - b), Math.cos(a - b));
}

function organicPath(bucketName, phase = 0) {
  const bucket = state.layout.buckets[bucketName];
  const nodes = state.nodes.filter((node) => node.bucketName === bucketName);
  const points = d3.range(30).map((index) => {
    const angle = (index / 30) * Math.PI * 2;
    let radius =
      bucket.r +
      Math.sin(angle * 2.1 + phase) * bucket.r * 0.028 +
      Math.cos(angle * 3.4 - phase * 0.7) * bucket.r * 0.022;

    nodes.forEach((node) => {
      const nodeAngle = Math.atan2(node.y - bucket.cy, node.x - bucket.cx);
      const influence = Math.exp(-(angleDelta(angle, nodeAngle) ** 2) / 0.15);
      const reach = Math.hypot(node.x - bucket.cx, node.y - bucket.cy) + node.radius + 24;
      radius = Math.max(radius, bucket.r + Math.max(0, reach - bucket.r) * influence + node.radius * 0.09 * influence);
    });

    radius = Math.min(radius, bucket.maxR + 58);
    return [bucket.cx + Math.cos(angle) * radius, bucket.cy + Math.sin(angle) * radius];
  });

  return d3.line().curve(d3.curveBasisClosed)(points);
}

function updateBucketArtwork() {
  const phase = performance.now() / 1050;
  const svg = d3.select("#bubbleBoard");
  BUCKET_NAMES.forEach((bucketName) => {
    const total = bucketItems(bucketName).reduce((sum, item) => sum + Number(item.amount || 0), 0);
    svg.select(`#${bucketName}-blob`).attr("d", organicPath(bucketName, phase));
    svg.select(`#${bucketName}-total`).text(isDcaEnabled() ? money(total) : "DCA off");
  });
}

function updateAssetArtwork() {
  const svg = d3.select("#bubbleBoard");
  svg
    .selectAll("g.asset.live")
    .data(state.nodes, (node) => node.id)
    .attr("class", (node) => `asset live ${state.selected === node.symbol ? "selected" : ""}`)
    .attr("transform", (node) => `translate(${node.x}, ${node.y})`)
    .select("circle")
    .attr("r", (node) => node.radius)
    .attr("fill", (node) => bucketColor(node.bucketName));

  svg
    .selectAll("g.asset.live")
    .select(".amount-label")
    .text((node) => `$${Math.round(node.amount || 0)}`);
}

function updateArtwork() {
  updateAssetArtwork();
  updateBucketArtwork();
}

function stopMotion() {
  Object.values(state.simulations).forEach((simulation) => simulation.stop());
  state.simulations = {};
  if (state.boundaryTimer) {
    state.boundaryTimer.stop();
    state.boundaryTimer = null;
  }
}

function keepNodesInside(bucketName) {
  state.nodes
    .filter((node) => node.bucketName === bucketName)
    .forEach((node) => {
      const clamped = clampPointToBucket({ x: node.x, y: node.y }, bucketName, node.radius);
      node.x = clamped.x;
      node.y = clamped.y;
    });
}

function startMotion() {
  stopMotion();
  BUCKET_NAMES.forEach((bucketName) => {
    const bucket = state.layout.buckets[bucketName];
    const nodes = state.nodes.filter((node) => node.bucketName === bucketName);
    if (!nodes.length) return;
    state.simulations[bucketName] = d3
      .forceSimulation(nodes)
      .alpha(0.85)
      .alphaDecay(0.045)
      .velocityDecay(0.42)
      .force("x", d3.forceX(bucket.cx).strength(0.027))
      .force("y", d3.forceY(bucket.cy).strength(0.027))
      .force("collide", d3.forceCollide((node) => node.radius + 8).iterations(5))
      .on("tick", () => {
        keepNodesInside(bucketName);
        updateArtwork();
      })
      .on("end", syncNodePositions);
  });
  state.boundaryTimer = d3.timer(() => updateBucketArtwork());
}

function restartBucket(bucketName) {
  const simulation = state.simulations[bucketName];
  if (!simulation) return;
  simulation.force("collide", d3.forceCollide((node) => node.radius + 8).iterations(5));
  simulation.alpha(0.72).restart();
}

function renderDraft(svg) {
  if (!state.draft) return;
  const draft = state.draft;
  const group = svg.append("g").attr("class", "asset draft").attr("transform", `translate(${draft.x}, ${draft.y})`);
  group.append("circle").attr("r", draft.radius).attr("fill", bucketColor(draft.bucketName));
}

function renderInvalidNodes(svg) {
  const now = Date.now();
  state.invalidNodes = state.invalidNodes.filter((node) => node.expiresAt > now);
  const invalids = svg.append("g").attr("class", "invalid-layer");
  invalids
    .selectAll("g.asset.invalid")
    .data(state.invalidNodes, (node) => node.id)
    .join("g")
    .attr("class", "asset invalid")
    .attr("transform", (node) => `translate(${node.x}, ${node.y})`)
    .each(function renderInvalid(node) {
      const group = d3.select(this);
      group.append("circle").attr("r", node.radius).attr("fill", "#b42318");
      group.append("text").attr("class", "symbol-label").attr("y", -4).text(node.symbol);
      group.append("text").attr("class", "amount-label").attr("y", 14).text("not found");
    });
}

function renderBoard() {
  if (!window.d3 || !state.dca?.plan) return;
  document.body.classList.toggle("dca-off", !isDcaEnabled());
  calculateLayout();
  fitBucketRadii();
  buildNodes();

  const svg = d3.select("#bubbleBoard");
  const { width, height, buckets } = state.layout;
  svg.attr("viewBox", `0 0 ${width} ${height}`);
  svg.selectAll("*").remove();
  svg.on("dblclick", handleBoardDoubleClick);

  const bucketLayer = svg.append("g").attr("class", "bucket-layer");
  BUCKET_NAMES.forEach((bucketName) => {
    const bucket = buckets[bucketName];
    const color = bucketColor(bucketName);
    bucketLayer
      .append("path")
      .attr("id", `${bucketName}-blob`)
      .attr("class", `bucket-blob ${bucketName}`)
      .attr("fill", color)
      .attr("stroke", d3.rgb(color).darker(1.5).toString())
      .attr("d", organicPath(bucketName));
    bucketLayer
      .append("text")
      .attr("class", "bucket-label")
      .attr("x", bucket.cx)
      .attr("y", bucket.cy - 14)
      .attr("text-anchor", "middle")
      .attr("fill", color)
      .text(bucket.label);
    bucketLayer
      .append("text")
      .attr("id", `${bucketName}-total`)
      .attr("class", "bucket-total")
      .attr("x", bucket.cx)
      .attr("y", bucket.cy + 24)
      .attr("text-anchor", "middle")
      .attr("fill", color)
      .text(isDcaEnabled() ? money(bucketItems(bucketName).reduce((sum, item) => sum + Number(item.amount || 0), 0)) : "DCA off");
  });

  const assets = svg
    .append("g")
    .attr("class", "asset-layer")
    .selectAll("g.asset")
    .data(state.nodes, (node) => node.id)
    .join("g")
    .attr("class", (node) => `asset live ${state.selected === node.symbol ? "selected" : ""}`)
    .attr("transform", (node) => `translate(${node.x}, ${node.y})`)
    .call(d3.drag().on("start", dragStart).on("drag", dragging).on("end", dragEnd))
    .on("click", (_, node) => {
      state.selected = node.symbol;
      updateArtwork();
    })
    .on("dblclick", (event, node) => {
      event.stopPropagation();
      removeSymbol(node.bucketName, node.symbol);
    })
    .on("wheel", wheelAsset);

  assets
    .append("circle")
    .attr("r", (node) => node.radius)
    .attr("fill", (node) => bucketColor(node.bucketName));
  assets.append("title").text((node) => `${node.symbol}: $${node.amount} ${node.bucketName}`);
  assets.append("text").attr("class", "symbol-label").attr("y", -5).text((node) => node.symbol);
  assets
    .append("text")
    .attr("class", "amount-label")
    .attr("y", 14)
    .text((node) => `$${Math.round(node.amount || 0)}`);

  renderDraft(svg);
  renderInvalidNodes(svg);
  startMotion();
}

function dragStart(event, node) {
  hideSymbolEntry();
  state.selected = node.symbol;
  node.fx = node.x;
  node.fy = node.y;
  d3.select(this).raise().classed("dragging", true);
  restartBucket(node.bucketName);
}

function dragging(event, node) {
  const targetBucket = nearestBucket({ x: event.x, y: event.y });
  const clamped = clampPointToBucket({ x: event.x, y: event.y }, targetBucket, node.radius);
  node.targetBucket = targetBucket;
  node.x = clamped.x;
  node.y = clamped.y;
  node.fx = clamped.x;
  node.fy = clamped.y;
  d3.select(this)
    .attr("transform", `translate(${node.x}, ${node.y})`)
    .select("circle")
    .attr("fill", bucketColor(targetBucket));
  updateBucketArtwork();
}

function dragEnd(event, node) {
  node.fx = null;
  node.fy = null;
  d3.select(this).classed("dragging", false);
  moveAsset(node.bucketName, node.targetBucket || node.bucketName, node.symbol, node.amount, { x: node.x, y: node.y });
  renderDca();
}

function wheelAsset(event, node) {
  event.preventDefault();
  event.stopPropagation();
  const direction = event.deltaY < 0 ? 1 : -1;
  const amount = clamp(Math.round(node.amount / WHEEL_STEP) * WHEEL_STEP + direction * WHEEL_STEP, 0, MAX_AMOUNT);
  if (amount === node.amount) return;

  node.amount = amount;
  node.radius = itemRadius(amount);
  const clamped = clampPointToBucket({ x: node.x, y: node.y }, node.bucketName, node.radius);
  node.x = clamped.x;
  node.y = clamped.y;
  applyNodeToItem(node);
  updateArtwork();
  restartBucket(node.bucketName);
}

function handleBoardDoubleClick(event) {
  if (event.target.closest(".asset")) return;
  const point = eventToSvgPoint(event);
  const bucketName = bucketAtPoint(point);
  if (!bucketName) return;
  event.preventDefault();
  event.stopPropagation();
  showSymbolEntry(bucketName, point);
}

function eventToSvgPoint(event) {
  const [x, y] = d3.pointer(event, $("#bubbleBoard"));
  return { x, y };
}

function showSymbolEntry(bucketName, point) {
  const radius = itemRadius(25);
  const clamped = clampPointToBucket(point, bucketName, radius);
  state.draft = {
    id: `draft:${Date.now()}`,
    bucketName,
    x: clamped.x,
    y: clamped.y,
    radius,
  };
  renderBoard();

  const entry = $("#symbolEntry");
  const rect = $("#bubbleBoard").getBoundingClientRect();
  entry.value = "";
  entry.placeholder = "SYM";
  entry.dataset.bucket = bucketName;
  entry.style.left = `${rect.left + (clamped.x / state.layout.width) * rect.width}px`;
  entry.style.top = `${rect.top + (clamped.y / state.layout.height) * rect.height}px`;
  entry.className = "show";
  window.setTimeout(() => {
    entry.focus();
    entry.select();
  }, 0);
}

function hideSymbolEntry(cancelDraft = true) {
  const entry = $("#symbolEntry");
  const hadEntry = entry.classList.contains("show") || Boolean(state.draft);
  entry.className = "";
  if (cancelDraft && hadEntry) {
    state.draft = null;
    renderBoard();
  }
}

function commitSymbolEntry() {
  const entry = $("#symbolEntry");
  if (!state.draft || !entry.classList.contains("show")) return;
  const symbol = entry.value.trim().toUpperCase();
  const draft = { ...state.draft };
  entry.className = "";
  state.draft = null;

  if (!symbol) {
    renderBoard();
    return;
  }

  const row = state.universe.find((item) => item.enabled && item.symbol === symbol);
  if (!row || assignedSymbols().has(symbol)) {
    addInvalidSymbol(symbol, draft);
    return;
  }

  addSymbolAt(draft.bucketName, row, { x: draft.x, y: draft.y });
}

function addInvalidSymbol(symbol, draft) {
  const invalid = {
    id: `invalid:${symbol}:${Date.now()}`,
    symbol,
    bucketName: draft.bucketName,
    x: draft.x,
    y: draft.y,
    radius: draft.radius,
    expiresAt: Date.now() + 5000,
  };
  state.invalidNodes.push(invalid);
  renderBoard();
  window.setTimeout(() => {
    state.invalidNodes = state.invalidNodes.filter((node) => node.id !== invalid.id);
    renderBoard();
  }, 5100);
}

function addSymbolAt(bucketName, row, point) {
  const amount = 25;
  const radius = itemRadius(amount);
  const bucket = state.layout.buckets[bucketName];
  const clamped = clampPointToBucket(point, bucketName, radius);
  state.dca.plan[bucketName].items.push({
    symbol: row.symbol,
    name: row.name,
    bucket: row.bucket,
    amount,
    position: pointToPosition(clamped, bucket, radius),
  });
  setBucketItems(bucketName, state.dca.plan[bucketName].items);
  renderDca();
  showToast(`${row.symbol} added`);
}

function renderControls() {
  const plan = state.dca?.plan;
  if (!plan) return;
  plan.max_item_amount = MAX_AMOUNT;
  $("#dcaEnabled").checked = Boolean(plan.enabled);
  $("#algorithmEnabled").checked = Boolean(state.controls?.algorithm_enabled);
  $("#optionsEnabled").checked = Boolean(state.controls?.options_trading_enabled);
}

function renderAccount() {
  const account = state.account;
  if (!account) return;
  const dayPl = Number(account.day_pl || 0);
  document.body.dataset.pnl = dayPl > 0 ? "positive" : dayPl < 0 ? "negative" : "flat";
  $("#equity").textContent = money(account.equity);
  $("#cash").textContent = money(account.cash);
  $("#dayPl").textContent = signedMoney(account.day_pl);
  $("#dayPl").className = valueClass(account.day_pl);
  $("#totalPl").textContent = signedMoney(account.total_pl ?? account.open_pl);
  $("#totalPl").className = valueClass(account.total_pl ?? account.open_pl);
  $("#positionsBody").innerHTML = account.positions.length
    ? account.positions
      .map(
        (row) => `
            <tr>
              <td><strong>${escapeHtml(row.symbol)}</strong></td>
              <td>${num(row.qty, 3)}</td>
              <td>${money(row.market_value)}</td>
              <td class="${valueClass(row.unrealized_pl)}">${signedMoney(row.unrealized_pl)}</td>
            </tr>
          `,
      )
      .join("")
    : `<tr><td colspan="4">No open positions.</td></tr>`;
}

function renderOrders(payload) {
  const rows = payload?.rows || [];
  const ordersPanel = $("#ordersPanel table");
  if (!ordersPanel) return;

  if (rows.length) {
    const tbody = ordersPanel.querySelector("tbody");
    tbody.innerHTML = rows
      .map((order) => {
        const qty = order.notional ? money(order.notional) : `${num(order.qty, 3)} sh`;
        return `
          <tr>
            <td><strong>${escapeHtml(order.symbol)}</strong></td>
            <td>${escapeHtml(order.side)}</td>
            <td>${qty}</td>
            <td>${escapeHtml(order.status)}</td>
          </tr>
        `;
      })
      .join("");
  } else {
    const tbody = ordersPanel.querySelector("tbody");
    tbody.innerHTML = `<tr><td colspan="4">No orders today.</td></tr>`;
  }


  function renderGrowthChart(payload) {
    const svg = d3.select("#growthChart");
    let rows = (payload?.rows || [])
      .map((row) => ({ ...row, date: new Date(row.timestamp), equity: Number(row.equity) }))
      .filter((row) => Number.isFinite(row.equity) && !Number.isNaN(row.date.getTime()));
    const firstFundedIndex = rows.findIndex((row) => row.equity > 0);
    if (firstFundedIndex > 0) rows = rows.slice(firstFundedIndex);
    const width = $("#growthChart").clientWidth || 420;
    const height = $("#growthChart").clientHeight || 180;
    const margin = { top: 14, right: 12, bottom: 22, left: 42 };
    svg.attr("viewBox", `0 0 ${width} ${height}`);
    svg.selectAll("*").remove();

    if (rows.length < 2) {
      svg
        .append("text")
        .attr("x", width / 2)
        .attr("y", height / 2)
        .attr("text-anchor", "middle")
        .attr("class", "empty-chart")
        .text("No history yet");
      return;
    }

    const x = d3
      .scaleTime()
      .domain(d3.extent(rows, (row) => row.date))
      .range([margin.left, width - margin.right]);
    const y = d3
      .scaleLinear()
      .domain(expandedDomain(d3.extent(rows, (row) => row.equity)))
      .nice()
      .range([height - margin.bottom, margin.top]);
    const positive = rows.at(-1).equity >= rows[0].equity;
    const color = positive ? "#057a55" : "#b42318";

    svg
      .append("path")
      .datum(rows)
      .attr("class", "growth-area")
      .attr("fill", color)
      .attr(
        "d",
        d3
          .area()
          .x((row) => x(row.date))
          .y0(height - margin.bottom)
          .y1((row) => y(row.equity))
          .curve(d3.curveMonotoneX),
      );

    svg
      .append("path")
      .datum(rows)
      .attr("class", "growth-line")
      .attr("stroke", color)
      .attr(
        "d",
        d3
          .line()
          .x((row) => x(row.date))
          .y((row) => y(row.equity))
          .curve(d3.curveMonotoneX),
      );

    svg
      .append("text")
      .attr("x", margin.left)
      .attr("y", height - 4)
      .attr("class", "chart-label")
      .text(money(rows[0].equity));
    svg
      .append("text")
      .attr("x", width - margin.right)
      .attr("y", margin.top + 10)
      .attr("text-anchor", "end")
      .attr("class", "chart-label")
      .text(money(rows.at(-1).equity));
  }

  function expandedDomain(domain) {
    const [min, max] = domain;
    if (min !== max) return domain;
    const padding = Math.max(Math.abs(min) * 0.01, 1);
    return [min - padding, max + padding];
  }

  function renderDca() {
    syncNodePositions();
    renderControls();
    renderBoard();
  }

  function syncControls() {
    const plan = state.dca.plan;
    plan.enabled = $("#dcaEnabled").checked;
    plan.max_item_amount = MAX_AMOUNT;
    plan.accumulate.enabled = true;
    plan.sell.enabled = true;
    state.controls.algorithm_enabled = $("#algorithmEnabled").checked;
    state.controls.options_trading_enabled = $("#optionsEnabled").checked;
    setBucketItems("accumulate", bucketItems("accumulate"));
    setBucketItems("sell", bucketItems("sell"));
  }

  function removeSymbol(bucketName, symbol) {
    setBucketItems(
      bucketName,
      bucketItems(bucketName).filter((item) => item.symbol !== symbol),
    );
    state.nodesById.delete(nodeId(bucketName, symbol));
    renderDca();
    showToast(`${symbol} removed`);
  }

  function moveAsset(sourceBucket, targetBucket, symbol, amount, point) {
    const sourceItems = bucketItems(sourceBucket);
    const index = sourceItems.findIndex((item) => item.symbol === symbol);
    if (index < 0) return;
    const [item] = sourceItems.splice(index, 1);
    const bucket = state.layout.buckets[targetBucket];
    const radius = itemRadius(amount);
    const clamped = clampPointToBucket(point, targetBucket, radius);
    item.amount = clamp(amount, 0, MAX_AMOUNT);
    item.position = pointToPosition(clamped, bucket, radius);
    delete item.bucketName;
    state.dca.plan[targetBucket].items.push(item);
    setBucketItems("accumulate", bucketItems("accumulate"));
    setBucketItems("sell", bucketItems("sell"));
  }

  async function savePlan(button = null, quiet = false) {
    syncNodePositions();
    syncControls();
    if (button) button.disabled = true;
    try {
      const [dcaPayload, controlsPayload] = await Promise.all([
        api("/api/dca", {
          method: "POST",
          body: JSON.stringify({ plan: state.dca.plan }),
        }),
        api("/api/controls", {
          method: "POST",
          body: JSON.stringify({ controls: state.controls }),
        }),
      ]);
      state.dca = dcaPayload;
      state.controls = controlsPayload.controls;
      renderDca();
      if (!quiet) showToast("Saved");
    } catch (error) {
      showToast(error.message);
    } finally {
      if (button) button.disabled = false;
    }
  }

  async function loadOptional(path, renderer, fallbackMessage) {
    try {
      renderer(await api(path));
    } catch (error) {
      fallbackMessage(error);
    }
  }

  async function loadAll() {
    state.status = await api("/api/status");
    state.universe = (await api("/api/universe")).rows || [];
    state.dca = await api("/api/dca");
    state.controls = (await api("/api/controls")).controls;
    state.dca.plan.max_item_amount = MAX_AMOUNT;
    renderDca();

    await loadOptional(
      "/api/account",
      (payload) => {
        state.account = payload;
        renderAccount();
      },
      (error) => {
        $("#positionsBody").innerHTML = `<tr><td colspan="4">${escapeHtml(error.message)}</td></tr>`;
      },
    );
    await loadOptional(
      "/api/portfolio-history",
      (payload) => {
        state.historyPayload = payload;
        renderGrowthChart(payload);
      },
      (error) => {
        d3.select("#growthChart").selectAll("*").remove();
        d3.select("#growthChart")
          .append("text")
          .attr("x", 20)
          .attr("y", 28)
          .attr("class", "empty-chart")
          .text(error.message);
      },
    );
    await loadOptional("/api/open-orders", renderOrders, (error) => {
      const tbody = $("#ordersBody");
      if (tbody) tbody.innerHTML = `<tr><td colspan="4">${escapeHtml(error.message)}</td></tr>`;
    });
  }

  function wireEvents() {
    $("#dcaEnabled").addEventListener("change", () => {
      state.dca.plan.enabled = $("#dcaEnabled").checked;
      renderDca();
      savePlan(null, true);
    });
    $("#algorithmEnabled").addEventListener("change", () => {
      state.controls.algorithm_enabled = $("#algorithmEnabled").checked;
      savePlan(null, true);
    });
    $("#optionsEnabled").addEventListener("change", () => {
      state.controls.options_trading_enabled = $("#optionsEnabled").checked;
      savePlan(null, true);
    });
    $("#symbolEntry").addEventListener("keydown", (event) => {
      if (event.key === "Enter") commitSymbolEntry();
      if (event.key === "Escape") hideSymbolEntry();
    });
    $("#symbolEntry").addEventListener("blur", () => window.setTimeout(commitSymbolEntry, 80));
    window.addEventListener("resize", () => {
      syncNodePositions();
      renderBoard();
      if (state.historyPayload) renderGrowthChart(state.historyPayload);
    });
  }

  async function init() {
    if (!window.d3) {
      showToast("D3 failed to load. Check internet access for the CDN.");
      return;
    }
    wireEvents();
    try {
      await loadAll();
    } catch (error) {
      showToast(error.message);
    }
  }

  init();
