/**
 * Frameworks Knowledge Graph & Wikilink Engine
 * Handles:
 * 1. Force-directed Graph rendering (Full site & local 1-2 hop views)
 * 2. List | Graph view toggle with URL state (?view=graph&node=...) & localStorage
 * 3. Live search driving both list filtering and graph highlights
 * 4. Automatic wikilink resolution and backlinks/relations hydration
 */

const CATEGORY_COLORS = {
  "Law": "#ef4444",
  "Policy": "#10b981",
  "Economics": "#3b82f6",
  "Society": "#8b5cf6",
  "Default": "#64748b"
};

let globalGraphData = null;
let globalBacklinksData = null;
let activeGraphSimulation = null;
let currentHopDistance = 1;
let selectedNodeId = null;

// Initialize on DOM load
document.addEventListener("DOMContentLoaded", async () => {
  try {
    const [graphRes, backlinksRes] = await Promise.all([
      fetch("/assets/graph.json").catch(() => fetch("../assets/graph.json")),
      fetch("/assets/backlinks.json").catch(() => fetch("../assets/backlinks.json"))
    ]);
    
    if (graphRes.ok) globalGraphData = await graphRes.json();
    if (backlinksRes && backlinksRes.ok) globalBacklinksData = await backlinksRes.json();
  } catch (e) {
    console.warn("Could not load graph data files directly via fetch:", e);
  }

  initUrlState();
  initViewToggle();
  initSearch();
  initWikilinksAndBacklinks();
  initLocalGraph();
});

/* ----------------------------------------------------
   1. URL State & View Toggle
---------------------------------------------------- */
function initUrlState() {
  const urlParams = new URLSearchParams(window.location.search);
  const viewParam = urlParams.get("view");
  const nodeParam = urlParams.get("node");
  
  if (nodeParam) {
    selectedNodeId = nodeParam;
  }
  
  const savedView = localStorage.getItem("frameworks_view_pref");
  const isMobile = window.innerWidth < 768;
  
  let targetView = "list";
  if (viewParam) {
    targetView = viewParam;
  } else if (!isMobile && savedView === "graph") {
    targetView = "graph";
  }
  
  applyView(targetView, false);
}

function initViewToggle() {
  const listBtn = document.getElementById("toggle-view-list");
  const graphBtn = document.getElementById("toggle-view-graph");
  
  if (listBtn && graphBtn) {
    listBtn.addEventListener("click", () => applyView("list", true));
    graphBtn.addEventListener("click", () => applyView("graph", true));
  }
}

function applyView(viewName, updateUrl = true) {
  const listBtn = document.getElementById("toggle-view-list");
  const graphBtn = document.getElementById("toggle-view-graph");
  const listContainer = document.getElementById("main-list-view");
  const graphContainer = document.getElementById("main-graph-view");
  
  if (listBtn && graphBtn) {
    if (viewName === "graph") {
      listBtn.classList.remove("active");
      graphBtn.classList.add("active");
      if (listContainer) listContainer.style.display = "none";
      if (graphContainer) {
        graphContainer.style.display = "block";
        renderMainGraph();
      }
    } else {
      graphBtn.classList.remove("active");
      listBtn.classList.add("active");
      if (listContainer) listContainer.style.display = "block";
      if (graphContainer) graphContainer.style.display = "none";
    }
  }
  
  localStorage.setItem("frameworks_view_pref", viewName);
  
  if (updateUrl) {
    const url = new URL(window.location.href);
    url.searchParams.set("view", viewName);
    if (selectedNodeId) url.searchParams.set("node", selectedNodeId);
    window.history.replaceState({}, "", url);
  }
}

/* ----------------------------------------------------
   2. Live Search Filter & Graph Highlighting
---------------------------------------------------- */
function initSearch() {
  const searchInput = document.getElementById("framework-search");
  if (!searchInput) return;

  searchInput.addEventListener("input", (e) => {
    const query = e.target.value.toLowerCase().trim();
    filterListItems(query);
    highlightGraphNodes(query);
  });
}

function filterListItems(query) {
  const cards = document.querySelectorAll(".framework-card, .listing-item");
  let matchCount = 0;
  
  cards.forEach(card => {
    const title = (card.querySelector(".card-title, .title")?.textContent || "").toLowerCase();
    const summary = (card.querySelector(".card-summary, .summary, .description")?.textContent || "").toLowerCase();
    const cat = (card.querySelector(".card-category-badge, .badge")?.textContent || "").toLowerCase();
    
    const matches = !query || title.includes(query) || summary.includes(query) || cat.includes(query);
    card.style.display = matches ? "" : "none";
    if (matches) matchCount++;
  });

  const searchStats = document.getElementById("search-stats");
  if (searchStats) {
    searchStats.textContent = query ? `Showing ${matchCount} matching frameworks` : "";
  }
}

function highlightGraphNodes(query) {
  if (!query) {
    d3.selectAll(".graph-node").attr("opacity", 1);
    d3.selectAll(".graph-edge").attr("opacity", 0.4);
    return;
  }
  
  d3.selectAll(".graph-node").attr("opacity", (d) => {
    const text = (d.title + " " + d.summary + " " + d.category).toLowerCase();
    return text.includes(query) ? 1 : 0.15;
  });
  
  d3.selectAll(".graph-edge").attr("opacity", 0.1);
}

/* ----------------------------------------------------
   3. Interactive Force-Directed Graph Engine
---------------------------------------------------- */
function renderMainGraph() {
  const container = document.getElementById("main-graph-canvas");
  if (!container || !globalGraphData) return;
  
  renderGraph(container, globalGraphData.nodes, globalGraphData.edges, {
    height: 580,
    centerNodeId: selectedNodeId,
    hops: 99 // full site
  });
}

function initLocalGraph() {
  const container = document.getElementById("local-graph-canvas");
  if (!container || !globalGraphData) return;
  
  const currentId = container.dataset.nodeId;
  if (!currentId) return;
  
  const hopBtn = document.getElementById("btn-toggle-hops");
  if (hopBtn) {
    hopBtn.addEventListener("click", () => {
      currentHopDistance = currentHopDistance === 1 ? 2 : 1;
      hopBtn.textContent = `${currentHopDistance} Hop${currentHopDistance > 1 ? 's' : ''}`;
      drawLocalSubGraph(container, currentId, currentHopDistance);
    });
  }
  
  drawLocalSubGraph(container, currentId, currentHopDistance);
}

function drawLocalSubGraph(container, centerId, hops) {
  if (!globalGraphData) return;
  
  // Calculate subgraph within N hops
  const nodeSet = new Set([centerId]);
  let currentFrontier = new Set([centerId]);
  
  for (let h = 0; h < hops; h++) {
    const nextFrontier = new Set();
    globalGraphData.edges.forEach(edge => {
      const src = typeof edge.source === "object" ? edge.source.id : edge.source;
      const tgt = typeof edge.target === "object" ? edge.target.id : edge.target;
      
      if (currentFrontier.has(src) && !nodeSet.has(tgt)) {
        nodeSet.add(tgt);
        nextFrontier.add(tgt);
      }
      if (currentFrontier.has(tgt) && !nodeSet.has(src)) {
        nodeSet.add(src);
        nextFrontier.add(src);
      }
    });
    currentFrontier = nextFrontier;
  }
  
  const subNodes = globalGraphData.nodes.filter(n => nodeSet.has(n.id));
  const subEdges = globalGraphData.edges.filter(edge => {
    const src = typeof edge.source === "object" ? edge.source.id : edge.source;
    const tgt = typeof edge.target === "object" ? edge.target.id : edge.target;
    return nodeSet.has(src) && nodeSet.has(tgt);
  });
  
  renderGraph(container, subNodes, subEdges, {
    height: 350,
    centerNodeId: centerId,
    hops: hops,
    isLocal: true
  });
}

function renderGraph(container, rawNodes, rawEdges, options = {}) {
  // Deep clone to prevent D3 mutation issues
  const nodes = rawNodes.map(d => ({ ...d }));
  const edges = rawEdges.map(d => ({ ...d }));
  
  container.innerHTML = "";
  const width = container.clientWidth || 800;
  const height = options.height || 500;
  
  const svg = d3.select(container)
    .append("svg")
    .attr("width", width)
    .attr("height", height)
    .attr("viewBox", [0, 0, width, height]);
    
  const g = svg.append("g");
  
  // Zoom & Pan
  const zoom = d3.zoom()
    .scaleExtent([0.3, 3])
    .on("zoom", (event) => g.attr("transform", event.transform));
  svg.call(zoom);

  // Arrow markers for directed relations
  svg.append("defs").selectAll("marker")
    .data(["end"])
    .enter().append("marker")
    .attr("id", "arrow")
    .attr("viewBox", "0 -5 10 10")
    .attr("refX", 22)
    .attr("refY", 0)
    .attr("markerWidth", 5)
    .attr("markerHeight", 5)
    .attr("orient", "auto")
    .append("path")
    .attr("fill", "#94a3b8")
    .attr("d", "M0,-5L10,0L0,5");

  // Force simulation
  const simulation = d3.forceSimulation(nodes)
    .force("link", d3.forceLink(edges).id(d => d.id).distance(options.isLocal ? 120 : 100))
    .force("charge", d3.forceManyBody().strength(options.isLocal ? -350 : -250))
    .force("center", d3.forceCenter(width / 2, height / 2))
    .force("collision", d3.forceCollide().radius(35));

  // Edges
  const edge = g.append("g")
    .attr("class", "graph-edges")
    .selectAll("line")
    .data(edges)
    .enter().append("line")
    .attr("class", "graph-edge")
    .attr("stroke", "#cbd5e1")
    .attr("stroke-width", 1.5)
    .attr("stroke-opacity", 0.6)
    .attr("marker-end", "url(#arrow)");

  // Edge labels (typed relations)
  const edgeLabel = g.append("g")
    .attr("class", "edge-labels")
    .selectAll("text")
    .data(edges.filter(e => e.label && e.label !== "mentions"))
    .enter().append("text")
    .attr("font-size", "9px")
    .attr("fill", "#94a3b8")
    .attr("text-anchor", "middle")
    .text(d => d.label);

  // Tooltip
  let tooltip = d3.select("body").select(".graph-tooltip");
  if (tooltip.empty()) {
    tooltip = d3.select("body").append("div").attr("class", "graph-tooltip");
  }

  // Nodes
  const node = g.append("g")
    .attr("class", "graph-nodes")
    .selectAll("g")
    .data(nodes)
    .enter().append("g")
    .attr("class", "graph-node")
    .call(d3.drag()
      .on("start", (event, d) => {
        if (!event.active) simulation.alphaTarget(0.3).restart();
        d.fx = d.x;
        d.fy = d.y;
      })
      .on("drag", (event, d) => {
        d.fx = event.x;
        d.fy = event.y;
      })
      .on("end", (event, d) => {
        if (!event.active) simulation.alphaTarget(0);
        d.fx = null;
        d.fy = null;
      }));

  // Node Circle
  node.append("circle")
    .attr("r", d => (d.id === options.centerNodeId ? 18 : 12 + Math.min(d.degree || 1, 8)))
    .attr("fill", d => CATEGORY_COLORS[d.category] || CATEGORY_COLORS["Default"])
    .attr("stroke", d => (d.id === options.centerNodeId ? "#0f172a" : "#ffffff"))
    .attr("stroke-width", d => (d.id === options.centerNodeId ? 3.5 : 2))
    .attr("cursor", "pointer");

  // Node Labels
  node.append("text")
    .attr("dy", 24)
    .attr("text-anchor", "middle")
    .attr("font-size", "11px")
    .attr("font-weight", "600")
    .attr("fill", "#1e293b")
    .text(d => d.title);

  // Hover & Click Interactions
  let clickTimeout = null;
  node.on("mouseenter", (event, d) => {
    tooltip.style("opacity", 1)
      .html(`<strong>${d.title}</strong><br/><span style="color:#93c5fd">${d.category}</span><br/><p style="margin:4px 0 0 0;font-size:11px;color:#cbd5e1;">${d.summary || ''}</p>`)
      .style("left", (event.pageX + 12) + "px")
      .style("top", (event.pageY - 28) + "px");
  })
  .on("mousemove", (event) => {
    tooltip.style("left", (event.pageX + 12) + "px")
      .style("top", (event.pageY - 28) + "px");
  })
  .on("mouseleave", () => {
    tooltip.style("opacity", 0);
  })
  .on("click", (event, d) => {
    if (clickTimeout) {
      // Double click -> navigate directly
      clearTimeout(clickTimeout);
      clickTimeout = null;
      window.location.href = d.url;
    } else {
      // Single click -> highlight & update URL state
      clickTimeout = setTimeout(() => {
        clickTimeout = null;
        selectedNodeId = d.id;
        const url = new URL(window.location.href);
        url.searchParams.set("node", d.id);
        window.history.replaceState({}, "", url);
        
        // Highlight active node
        node.selectAll("circle")
          .attr("stroke", n => (n.id === d.id ? "#0f172a" : "#ffffff"))
          .attr("stroke-width", n => (n.id === d.id ? 4 : 2));
      }, 250);
    }
  });

  // Tick update
  simulation.on("tick", () => {
    edge
      .attr("x1", d => d.source.x)
      .attr("y1", d => d.source.y)
      .attr("x2", d => d.target.x)
      .attr("y2", d => d.target.y);

    edgeLabel
      .attr("x", d => (d.source.x + d.target.x) / 2)
      .attr("y", d => (d.source.y + d.target.y) / 2);

    node.attr("transform", d => `translate(${d.x},${d.y})`);
  });
}

/* ----------------------------------------------------
   4. Wikilinks & Backlinks Auto-Hydration
---------------------------------------------------- */
function initWikilinksAndBacklinks() {
  if (!globalGraphData) return;
  
  const nodeMap = new Map();
  globalGraphData.nodes.forEach(n => nodeMap.set(n.id, n));
  
  // Transform body text [[item-id]] -> <a href="...">
  const contentBody = document.querySelector("main.content, article, .quarto-body");
  if (contentBody) {
    const walker = document.createTreeWalker(contentBody, NodeFilter.SHOW_TEXT);
    const textNodes = [];
    while (walker.nextNode()) textNodes.push(walker.currentNode);
    
    const wikilinkRegex = /\[\[([a-zA-Z0-9_\-]+)(?:\|([^\]]+))?\]\]/g;
    
    textNodes.forEach(node => {
      if (node.parentElement && ["SCRIPT", "STYLE", "A"].includes(node.parentElement.tagName)) return;
      if (wikilinkRegex.test(node.nodeValue)) {
        const span = document.createElement("span");
        span.innerHTML = node.nodeValue.replace(wikilinkRegex, (match, id, alias) => {
          const target = nodeMap.get(id);
          if (target) {
            return `<a href="${target.url}" class="wikilink" title="${target.summary}">${alias || target.title}</a>`;
          }
          return alias || id;
        });
        node.parentElement.replaceChild(span, node);
      }
    });
  }
}
