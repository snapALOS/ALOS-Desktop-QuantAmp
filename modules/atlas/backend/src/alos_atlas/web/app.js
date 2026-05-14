const state = {
  repos: [],
  repo: "",
  history: [],
  token: ""
};

const $ = (id) => document.getElementById(id);

function selectedRepo() {
  return $("repoSelect").value || state.repo;
}

function log(message, payload) {
  const time = new Date().toLocaleTimeString();
  state.history.unshift({ time, message, payload });
  state.history = state.history.slice(0, 20);
  $("activityLog").textContent = state.history
    .map((entry) => `[${entry.time}] ${entry.message}${entry.payload ? "\n" + JSON.stringify(entry.payload, null, 2) : ""}`)
    .join("\n\n");
}

async function request(path, options = {}) {
  const token = readToken();
  const headers = {
    "content-type": "application/json",
    ...(token ? { "x-alos_atlas-token": token } : {}),
    ...(options.headers || {})
  };
  const response = await fetch(path, {
    ...options,
    headers
  });
  const text = await response.text();
  const payload = text ? JSON.parse(text) : {};
  if (!response.ok || payload.error) {
    throw new Error(payload.error || `Request failed: ${response.status}`);
  }
  return payload;
}

function readToken() {
  const input = $("apiTokenInput");
  const value = input ? input.value.trim() : "";
  if (value) return value;
  try {
    return window.localStorage.getItem("alos_atlas.apiToken") || "";
  } catch (_error) {
    return state.token || "";
  }
}

function saveToken() {
  state.token = $("apiTokenInput").value.trim();
  try {
    if (state.token) {
      window.localStorage.setItem("alos_atlas.apiToken", state.token);
    } else {
      window.localStorage.removeItem("alos_atlas.apiToken");
    }
  } catch (_error) {
    // Private browsing modes can reject storage; keep the token for this page.
  }
  log(state.token ? "API token saved" : "API token cleared");
}

function restoreToken() {
  try {
    state.token = window.localStorage.getItem("alos_atlas.apiToken") || "";
  } catch (_error) {
    state.token = "";
  }
  $("apiTokenInput").value = state.token;
}

function api(path, params = {}) {
  const url = new URL(path, window.location.origin);
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") {
      url.searchParams.set(key, value);
    }
  }
  return request(url.pathname + url.search);
}

function renderItems(target, items, renderer) {
  const el = $(target);
  if (!items || !items.length) {
    el.innerHTML = '<div class="item"><strong>No results</strong><span class="meta">Run an index or refine the query.</span></div>';
    return;
  }
  el.innerHTML = items.map(renderer).join("");
}

function esc(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function nodeItem(item) {
  return `<div class="item">
    <strong>${esc(item.type)}: ${esc(item.name)}</strong>
    <div class="meta">${esc(item.path)}${item.start_line ? `:${esc(item.start_line)}` : ""}</div>
    <span class="badge">confidence ${esc(item.confidence)}</span>
    ${item.signature ? `<div>${esc(item.signature)}</div>` : ""}
  </div>`;
}

function edgeItem(item) {
  return `<div class="item">
    <strong>${esc(item.type)}: ${esc(item.source_name || item.source_id)} -> ${esc(item.target_name || item.target_id)}</strong>
    <div class="meta">${esc(item.source_node_path || item.source_path)}${item.source_line ? `:${esc(item.source_line)}` : ""}</div>
    <span class="badge">confidence ${esc(item.confidence)}</span>
    <div>${esc(item.reason)}</div>
  </div>`;
}

function fileItem(item) {
  return `<div class="item">
    <strong>${esc(item.path)}</strong>
    <span class="badge">${esc(item.language)}</span>
    <span class="badge">${esc(item.file_class)}</span>
    <span class="badge">${item.indexed ? "indexed" : "skipped"}</span>
    <div class="meta">${esc(item.reason)} - ${esc(item.size_bytes)} bytes</div>
  </div>`;
}

function countItem(item, labelKey = "type") {
  return `<div class="item"><strong>${esc(item[labelKey])}</strong><span class="badge">${esc(item.count)}</span></div>`;
}

function topFileItem(item) {
  return `<div class="item"><strong>${esc(item.path)}</strong><span class="badge">${esc(item.symbols)} symbols</span></div>`;
}

function overviewSection(title, items, renderer) {
  const rows = items && items.length ? items.map(renderer).join("") : '<div class="item"><strong>No data</strong></div>';
  return `<section class="overview-group"><h2>${esc(title)}</h2>${rows}</section>`;
}

function renderGraphOverview(graph) {
  const status = graph.status || {};
  $("graphOutput").innerHTML = [
    `<div class="item"><strong>${esc(status.repo_name || selectedRepo())}</strong><span class="badge">${status.stale ? "stale" : "fresh"}</span><span class="badge">${esc(status.repo_id || "")}</span></div>`,
    overviewSection("Node Counts", graph.node_counts || [], (item) => countItem(item)),
    overviewSection("Edge Counts", graph.edge_counts || [], (item) => countItem(item)),
    overviewSection("File Classes", graph.file_classes || [], (item) => countItem(item, "file_class")),
    overviewSection("Top Files", graph.top_files || [], topFileItem)
  ].join("");
}

async function loadRepos() {
  const data = await request("/api/repos");
  state.repos = data.repositories || [];
  const current = selectedRepo();
  $("repoSelect").innerHTML = state.repos
    .map((repo) => `<option value="${esc(repo.repo_name)}">${esc(repo.repo_name)}</option>`)
    .join("");
  if (current && state.repos.some((repo) => repo.repo_name === current || repo.repo_id === current)) {
    $("repoSelect").value = current;
  }
  state.repo = selectedRepo();
  log("Repositories loaded", { count: state.repos.length });
  if (state.repo) {
    await loadStatus();
  }
}

async function loadStatus() {
  const repo = selectedRepo();
  if (!repo) return;
  const status = await api("/api/status", { repo });
  $("freshnessValue").textContent = status.stale ? "Stale" : "Fresh";
  $("freshnessValue").className = status.stale ? "warn" : "";
  const counts = status.counts || {};
  $("fileCountValue").textContent = counts.indexed_files ?? status.files_indexed ?? 0;
  $("nodeCountValue").textContent = counts.nodes ?? status.node_count ?? 0;
  $("edgeCountValue").textContent = counts.edges ?? status.edge_count ?? 0;
  log("Status loaded", status);
}

async function registerRepo(event) {
  event.preventDefault();
  const name = $("repoNameInput").value.trim();
  const path = $("repoPathInput").value.trim();
  const data = await request("/api/register", {
    method: "POST",
    body: JSON.stringify({ name, path })
  });
  log("Repository registered", data);
  await loadRepos();
}

async function indexSelected() {
  const repo = selectedRepo();
  if (!repo) throw new Error("Select or register a repository first.");
  const data = await request("/api/index", {
    method: "POST",
    body: JSON.stringify({ repo })
  });
  log("Index completed", data);
  await loadStatus();
  await loadOverview();
}

async function loadOverview() {
  const repo = selectedRepo();
  const graph = await api("/api/graph", { repo });
  renderGraphOverview(graph);
  const graphData = await api("/api/graph-data", { repo, limit: "80" });
  drawGraph(graphData.nodes || [], graphData.edges || []);
  log("Graph overview loaded", {
    nodes: (graph.node_counts || []).length,
    edges: (graph.edge_counts || []).length,
    top_files: (graph.top_files || []).length
  });
}

async function loadGraphMap() {
  const data = await api("/api/graph-data", { repo: selectedRepo(), limit: "80" });
  drawGraph(data.nodes || [], data.edges || []);
  log("Graph map drawn", { nodes: data.nodes.length, edges: data.edges.length });
}

function drawGraph(nodes, edges) {
  const target = $("graphMap");
  if (!nodes.length) {
    target.innerHTML = '<div class="item"><strong>No graph nodes</strong></div>';
    return;
  }
  const width = 900;
  const height = 360;
  const centerX = width / 2;
  const centerY = height / 2;
  const radius = Math.min(width, height) * 0.38;
  const positions = new Map();
  nodes.forEach((node, index) => {
    const angle = (Math.PI * 2 * index) / nodes.length - Math.PI / 2;
    positions.set(node.id, {
      x: centerX + Math.cos(angle) * radius,
      y: centerY + Math.sin(angle) * radius
    });
  });
  const edgeSvg = edges
    .map((edge) => {
      const a = positions.get(edge.source_id);
      const b = positions.get(edge.target_id);
      if (!a || !b) return "";
      return `<line x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}" stroke="#8fc7bf" stroke-width="${Math.max(1, Number(edge.confidence || 0.5) * 2)}"><title>${esc(edge.type)} ${esc(edge.reason)}</title></line>`;
    })
    .join("");
  const nodeSvg = nodes
    .map((node) => {
      const point = positions.get(node.id);
      const fill = node.type === "File" ? "#d8f0ec" : node.type === "Route" ? "#ffe7a3" : node.type === "Endpoint" ? "#ffd2c9" : "#ffffff";
      const label = node.name.length > 22 ? `${node.name.slice(0, 21)}...` : node.name;
      return `<g>
        <circle cx="${point.x}" cy="${point.y}" r="14" fill="${fill}" stroke="#1f2526"><title>${esc(node.type)} ${esc(node.name)} ${esc(node.path)}</title></circle>
        <text x="${point.x + 18}" y="${point.y + 4}">${esc(label)}</text>
      </g>`;
    })
    .join("");
  target.innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Repository dependency graph">${edgeSvg}${nodeSvg}</svg>`;
}

async function loadFiles() {
  const data = await api("/api/files", { repo: selectedRepo(), indexed_only: "false" });
  renderItems("inventoryOutput", data.files, fileItem);
  log("Files loaded", { count: data.files.length });
}

async function loadSymbols() {
  const data = await api("/api/symbols", { repo: selectedRepo() });
  renderItems("inventoryOutput", data.symbols, nodeItem);
  log("Symbols loaded", { count: data.symbols.length });
}

async function runSearch(event) {
  event.preventDefault();
  const data = await api("/api/search", { repo: selectedRepo(), q: $("searchInput").value.trim() });
  renderItems("searchOutput", data.results, (item) => nodeItem({ type: item.type, name: item.name, path: item.path, confidence: "search", signature: item.text }));
  log("Search completed", { query: data.query, count: data.results.length });
}

async function loadContext(event) {
  event.preventDefault();
  const repo = selectedRepo();
  const type = $("contextType").value;
  const value = $("contextInput").value.trim();
  let data;
  if (type === "file") data = await api("/api/file-context", { repo, path: value });
  if (type === "symbol") data = await api("/api/symbol-context", { repo, symbol: value });
  if (type === "route") data = await api("/api/route-context", { repo, route: value });
  const nodes = data.nodes || data.matches || [];
  const edges = data.relationships || [];
  $("contextOutput").innerHTML = [
    "<h2>Nodes</h2>",
    ...nodes.map(nodeItem),
    "<h2>Relationships</h2>",
    ...edges.map(edgeItem)
  ].join("") || '<div class="item"><strong>No context found</strong></div>';
  log("Context loaded", { type, value });
}

async function runImpact(event) {
  event.preventDefault();
  const data = await api("/api/impact", {
    repo: selectedRepo(),
    target: $("impactTarget").value.trim(),
    type: $("impactType").value,
    depth: $("impactDepth").value
  });
  $("impactOutput").innerHTML = [
    `<div class="item"><strong>Risk: ${esc(data.risk_level)}</strong><span class="badge">confidence ${esc(data.confidence)}</span></div>`,
    "<h2>Direct Dependents</h2>",
    ...data.direct_dependents.map(edgeItem),
    "<h2>Indirect Dependents</h2>",
    ...data.indirect_dependents.map(edgeItem),
    "<h2>Affected Tests</h2>",
    ...data.affected_tests.map((item) => `<div class="item"><strong>${esc(item.path)}</strong><div>${esc(item.reason)}</div></div>`),
    "<h2>Verification</h2>",
    ...data.recommended_verification.map((item) => `<div class="item">${esc(item)}</div>`)
  ].join("");
  log("Impact completed", { target: data.target, risk: data.risk_level });
}

async function runScope(event) {
  event.preventDefault();
  const files = $("scopeFiles").value.split(",").map((item) => item.trim()).filter(Boolean);
  const data = await request("/api/change-scope", {
    method: "POST",
    body: JSON.stringify({ repo: selectedRepo(), files, git: $("scopeGit").checked })
  });
  $("scopeOutput").innerHTML = [
    `<div class="item"><strong>Changed files</strong><div>${esc(data.changed_files.join(", "))}</div></div>`,
    "<h2>Files</h2>",
    ...data.files.map((item) => `<div class="item"><strong>${esc(item.path)}</strong><span class="badge">${esc(item.changed_symbols.length)} changed symbols</span><span class="badge">risk ${esc(item.impact.risk_level)}</span></div>`),
    "<h2>Recommended Tests</h2>",
    ...data.recommended_tests.map((item) => `<div class="item"><strong>${esc(item.path)}</strong><div>${esc(item.reason || item.relationship_reason || "")}</div></div>`)
  ].join("");
  log("Change scope completed", { files: data.changed_files.length });
}

async function runTests(event) {
  event.preventDefault();
  const files = $("testsFiles").value.split(",").map((item) => item.trim()).filter(Boolean).join(",");
  const data = await api("/api/recommend-tests", {
    repo: selectedRepo(),
    target: $("testsTarget").value.trim(),
    files
  });
  renderItems("testsOutput", data.tests, (item) => `<div class="item"><strong>${esc(item.path)}</strong><div>${esc(item.name || "")}</div><div class="meta">${esc(item.reason || item.relationship_reason || "")}</div></div>`);
  log("Tests recommended", { count: data.tests.length });
}

async function loadProfile() {
  const data = await api("/api/profile", { repo: selectedRepo() });
  $("profileEditor").value = JSON.stringify(data.profile, null, 2);
  $("profileOutput").innerHTML = '<div class="item"><strong>Profile loaded</strong></div>';
  log("Profile loaded");
}

async function saveProfile() {
  const profile = JSON.parse($("profileEditor").value);
  const data = await request("/api/profile", {
    method: "POST",
    body: JSON.stringify({ repo: selectedRepo(), profile })
  });
  $("profileEditor").value = JSON.stringify(data.profile, null, 2);
  $("profileOutput").innerHTML = '<div class="item"><strong>Profile saved</strong><span class="meta">Re-index to apply parser/discovery changes.</span></div>';
  log("Profile saved");
}

async function exportReport(event) {
  event.preventDefault();
  const data = await api("/api/export", {
    repo: selectedRepo(),
    target: $("reportTarget").value.trim(),
    type: $("reportType").value
  });
  $("reportOutput").value = data.report;
  log("Markdown report exported");
}

async function refreshIfStale() {
  const data = await request("/api/refresh", {
    method: "POST",
    body: JSON.stringify({ repo: selectedRepo() })
  });
  $("storageOutput").innerHTML = `<div class="item"><strong>${data.refreshed ? "Refreshed" : "Already fresh"}</strong><pre>${esc(JSON.stringify(data, null, 2))}</pre></div>`;
  await loadStatus();
  log("Refresh checked", data);
}

async function exportIndexArchive() {
  const data = await request("/api/export-index", {
    method: "POST",
    body: JSON.stringify({ repo: selectedRepo() })
  });
  $("storageOutput").innerHTML = `<div class="item"><strong>Index archive exported</strong><div>${esc(data.archive)}</div><span class="badge">${esc(data.bytes)} bytes</span></div>`;
  log("Index archive exported", data);
}

async function exportEncryptedArchive() {
  const passphrase = $("vaultPassphrase").value;
  const data = await request("/api/export-encrypted", {
    method: "POST",
    body: JSON.stringify({ repo: selectedRepo(), passphrase })
  });
  $("storageOutput").innerHTML = `<div class="item"><strong>Encrypted archive exported</strong><div>${esc(data.encrypted_archive)}</div><span class="badge">${esc(data.algorithm)}</span><span class="badge">${esc(data.bytes)} bytes</span></div>`;
  log("Encrypted archive exported", { archive: data.encrypted_archive, algorithm: data.algorithm });
}

async function lockIndex() {
  const passphrase = $("vaultPassphrase").value;
  const data = await request("/api/lock-index", {
    method: "POST",
    body: JSON.stringify({ repo: selectedRepo(), passphrase })
  });
  $("storageOutput").innerHTML = `<div class="item"><strong>Index locked</strong><div>${esc(data.encrypted_archive)}</div><span class="badge">${esc(data.algorithm)}</span></div>`;
  log("Index locked", { repo: data.repo_name });
}

async function unlockIndex() {
  const passphrase = $("vaultPassphrase").value;
  const data = await request("/api/unlock-index", {
    method: "POST",
    body: JSON.stringify({ repo: selectedRepo(), passphrase })
  });
  $("storageOutput").innerHTML = `<div class="item"><strong>Index unlocked</strong><div>${esc(data.repo_dir)}</div></div>`;
  await loadStatus();
  log("Index unlocked", { repo: data.repo_name });
}

async function deleteIndex() {
  const repo = selectedRepo();
  const confirmed = window.confirm(`Delete local AlosAtlas index for ${repo}? The source repository is not modified.`);
  if (!confirmed) return;
  const data = await request("/api/delete-index", {
    method: "POST",
    body: JSON.stringify({ repo, remove_files: true, unregister: false })
  });
  $("storageOutput").innerHTML = `<div class="item"><strong>Index deleted</strong><pre>${esc(JSON.stringify(data, null, 2))}</pre></div>`;
  await loadStatus().catch(() => {});
  log("Index deleted", data);
}

async function recordTrace(event) {
  event.preventDefault();
  const target = $("traceTarget").value.trim();
  const trace = {
    event_type: $("traceType").value.trim(),
    label: $("traceLabel").value.trim(),
    path: target.includes(".") && !target.startsWith("/") ? target : undefined,
    route: target.startsWith("/") ? target : undefined,
    endpoint: target.startsWith("/") ? target : undefined,
    symbol: !target.includes("/") && target ? target : undefined,
    metadata: { source: "alos_atlas-local-app" }
  };
  const data = await request("/api/traces", {
    method: "POST",
    body: JSON.stringify({ repo: selectedRepo(), trace })
  });
  $("traceOutput").innerHTML = `<div class="item"><strong>Trace recorded</strong><pre>${esc(JSON.stringify(data, null, 2))}</pre></div>`;
  log("Runtime trace recorded", data.trace);
}

async function loadTraces() {
  const data = await api("/api/traces", { repo: selectedRepo(), limit: "100" });
  renderItems("traceOutput", data.traces, (item) => `<div class="item"><strong>${esc(item.event_type)}: ${esc(item.label)}</strong><div class="meta">${esc(item.observed_at)}</div><span class="badge">${esc(item.path || item.symbol || item.route || item.endpoint || "unlinked")}</span></div>`);
  log("Runtime traces loaded", { count: data.traces.length });
}

function wireTabs() {
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((item) => item.classList.remove("active"));
      document.querySelectorAll(".panel").forEach((item) => item.classList.remove("active"));
      tab.classList.add("active");
      $(tab.dataset.panel).classList.add("active");
    });
  });
}

function wireEvents() {
  restoreToken();
  wireTabs();
  $("saveTokenBtn").addEventListener("click", saveToken);
  $("refreshReposBtn").addEventListener("click", () => loadRepos().catch(showError));
  $("repoSelect").addEventListener("change", () => loadStatus().catch(showError));
  $("registerForm").addEventListener("submit", (event) => registerRepo(event).catch(showError));
  $("indexBtn").addEventListener("click", () => indexSelected().catch(showError));
  $("loadOverviewBtn").addEventListener("click", () => loadOverview().catch(showError));
  $("loadGraphMapBtn").addEventListener("click", () => loadGraphMap().catch(showError));
  $("loadFilesBtn").addEventListener("click", () => loadFiles().catch(showError));
  $("loadSymbolsBtn").addEventListener("click", () => loadSymbols().catch(showError));
  $("searchForm").addEventListener("submit", (event) => runSearch(event).catch(showError));
  $("contextForm").addEventListener("submit", (event) => loadContext(event).catch(showError));
  $("impactForm").addEventListener("submit", (event) => runImpact(event).catch(showError));
  $("scopeForm").addEventListener("submit", (event) => runScope(event).catch(showError));
  $("testsForm").addEventListener("submit", (event) => runTests(event).catch(showError));
  $("loadProfileBtn").addEventListener("click", () => loadProfile().catch(showError));
  $("saveProfileBtn").addEventListener("click", () => saveProfile().catch(showError));
  $("reportForm").addEventListener("submit", (event) => exportReport(event).catch(showError));
  $("refreshIfStaleBtn").addEventListener("click", () => refreshIfStale().catch(showError));
  $("exportIndexBtn").addEventListener("click", () => exportIndexArchive().catch(showError));
  $("exportEncryptedBtn").addEventListener("click", () => exportEncryptedArchive().catch(showError));
  $("lockIndexBtn").addEventListener("click", () => lockIndex().catch(showError));
  $("unlockIndexBtn").addEventListener("click", () => unlockIndex().catch(showError));
  $("deleteIndexBtn").addEventListener("click", () => deleteIndex().catch(showError));
  $("traceForm").addEventListener("submit", (event) => recordTrace(event).catch(showError));
  $("loadTracesBtn").addEventListener("click", () => loadTraces().catch(showError));
}

function showError(error) {
  log("Error", { message: error.message });
}

wireEvents();
loadRepos().catch(showError);
