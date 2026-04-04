<script lang="ts">
  import { onMount } from "svelte";
  import * as d3 from "d3";
  import { api } from "../lib/api";

  interface Props {
    onOpenArticle?: (path: string) => void;
    refreshToken?: number;
  }

  interface Node extends d3.SimulationNodeDatum {
    id: string;
    name: string;
    category: string;
    path: string;
    links: number;
  }

  interface Link extends d3.SimulationLinkDatum<Node> {
    source: string | Node;
    target: string | Node;
  }

  let { onOpenArticle = () => {}, refreshToken = 0 }: Props = $props();

  let svgEl: SVGSVGElement;
  let loading = $state(true);
  let error = $state("");
  let nodeCount = $state(0);
  let edgeCount = $state(0);
  let categories: string[] = $state([]);
  let filterCategory = $state("");
  let searchQuery = $state("");
  let ready = false;
  let lastRefresh = -1;

  let allNodes: Node[] = [];
  let allLinks: Link[] = [];
  let simulation: d3.Simulation<Node, Link> | null = null;

  async function loadGraph() {
    loading = true;
    error = "";
    try {
      const data = await api.graph();
      allNodes = data.nodes.map((node) => ({ ...node }));
      allLinks = data.edges.map((edge) => ({ ...edge }));
      nodeCount = data.node_count;
      edgeCount = data.edge_count;
      categories = [...new Set(allNodes.map((node) => node.category))].sort();
      applyFilter();
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    } finally {
      loading = false;
    }
  }

  function getFilteredData(): { nodes: Node[]; links: Link[] } {
    let nodes = allNodes;
    if (filterCategory) {
      const keep = new Set(
        allNodes.filter((node) => node.category === filterCategory).map((node) => node.id),
      );
      for (const link of allLinks) {
        const source = typeof link.source === "string" ? link.source : link.source.id;
        const target = typeof link.target === "string" ? link.target : link.target.id;
        if (keep.has(source)) keep.add(target);
        if (keep.has(target)) keep.add(source);
      }
      nodes = allNodes.filter((node) => keep.has(node.id));
    }
    const nodeIds = new Set(nodes.map((node) => node.id));
    const links = allLinks.filter((link) => {
      const source = typeof link.source === "string" ? link.source : link.source.id;
      const target = typeof link.target === "string" ? link.target : link.target.id;
      return nodeIds.has(source) && nodeIds.has(target);
    });
    return { nodes, links };
  }

  function applyFilter() {
    if (!svgEl) {
      return;
    }
    const { nodes, links } = getFilteredData();
    renderGraph(nodes, links);
  }

  function exportSvg() {
    if (!svgEl) {
      return;
    }
    const svgData = new XMLSerializer().serializeToString(svgEl);
    const blob = new Blob([svgData], { type: "image/svg+xml;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "compendium-graph.svg";
    anchor.click();
    URL.revokeObjectURL(url);
  }

  async function exportPng() {
    if (!svgEl) {
      return;
    }
    const rect = svgEl.getBoundingClientRect();
    const width = Math.max(Math.round(rect.width), 960);
    const height = Math.max(Math.round(rect.height), 640);

    const svgData = new XMLSerializer().serializeToString(svgEl);
    const blob = new Blob([svgData], { type: "image/svg+xml;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const image = new Image();

    try {
      await new Promise<void>((resolve, reject) => {
        image.onload = () => resolve();
        image.onerror = () => reject(new Error("Could not render PNG export"));
        image.src = url;
      });

      const canvas = document.createElement("canvas");
      canvas.width = width * 2;
      canvas.height = height * 2;
      const context = canvas.getContext("2d");
      if (!context) {
        throw new Error("Canvas context unavailable");
      }

      context.scale(2, 2);
      context.fillStyle = "#f4efe7";
      context.fillRect(0, 0, width, height);
      context.drawImage(image, 0, 0, width, height);

      const pngUrl = canvas.toDataURL("image/png");
      const anchor = document.createElement("a");
      anchor.href = pngUrl;
      anchor.download = "compendium-graph.png";
      anchor.click();
    } finally {
      URL.revokeObjectURL(url);
    }
  }

  function renderGraph(nodes: Node[], links: Link[]) {
    const width = svgEl.clientWidth || 960;
    const height = svgEl.clientHeight || 640;
    const colorScale = d3.scaleOrdinal(d3.schemeTableau10);
    const query = searchQuery.trim().toLowerCase();

    simulation?.stop();
    simulation = d3
      .forceSimulation(nodes)
      .force("link", d3.forceLink<Node, Link>(links).id((node) => node.id).distance(95))
      .force("charge", d3.forceManyBody().strength(-220))
      .force("center", d3.forceCenter(width / 2, height / 2))
      .force("collision", d3.forceCollide().radius((node) => 22 + Math.min(node.links * 2, 10)));

    const svg = d3.select(svgEl).attr("viewBox", `0 0 ${width} ${height}`);
    svg.selectAll("*").remove();

    const stage = svg.append("g");
    svg.call(
      d3
        .zoom<SVGSVGElement, unknown>()
        .scaleExtent([0.3, 4])
        .on("zoom", (event) => {
          stage.attr("transform", event.transform);
        }) as never,
    );

    const link = stage
      .append("g")
      .attr("stroke", "#a9a096")
      .attr("stroke-opacity", 0.55)
      .selectAll("line")
      .data(links)
      .join("line")
      .attr("stroke-width", 1.4);

    const node = stage
      .append("g")
      .selectAll("circle")
      .data(nodes)
      .join("circle")
      .attr("r", (entry) => 9 + Math.min(entry.links * 1.5, 10))
      .attr("fill", (entry) => colorScale(entry.category))
      .attr("stroke", (entry) =>
        query && entry.name.toLowerCase().includes(query) ? "#1d4ed8" : "#fff8f0",
      )
      .attr("stroke-width", (entry) =>
        query && entry.name.toLowerCase().includes(query) ? 3 : 1.8,
      )
      .style("cursor", "pointer")
      .on("click", (_, entry) => onOpenArticle(entry.path))
      .call(drag(simulation));

    node.append("title").text(
      (entry) => `${entry.name}\nCategory: ${entry.category}\nIncoming links: ${entry.links}`,
    );

    const label = stage
      .append("g")
      .selectAll("text")
      .data(nodes)
      .join("text")
      .text((entry) => entry.name)
      .attr("font-size", 11)
      .attr("font-weight", (entry) =>
        query && entry.name.toLowerCase().includes(query) ? "700" : "500",
      )
      .attr("fill", (entry) =>
        query && entry.name.toLowerCase().includes(query) ? "#1d4ed8" : "#4a4035",
      )
      .attr("dx", 14)
      .attr("dy", 4)
      .style("pointer-events", "none");

    simulation.on("tick", () => {
      link
        .attr("x1", (entry) => (entry.source as Node).x ?? 0)
        .attr("y1", (entry) => (entry.source as Node).y ?? 0)
        .attr("x2", (entry) => (entry.target as Node).x ?? 0)
        .attr("y2", (entry) => (entry.target as Node).y ?? 0);

      node.attr("cx", (entry) => entry.x ?? 0).attr("cy", (entry) => entry.y ?? 0);
      label.attr("x", (entry) => entry.x ?? 0).attr("y", (entry) => entry.y ?? 0);
    });
  }

  function drag(sim: d3.Simulation<Node, Link>) {
    return d3
      .drag<SVGCircleElement, Node>()
      .on("start", (event, node) => {
        if (!event.active) {
          sim.alphaTarget(0.3).restart();
        }
        node.fx = node.x;
        node.fy = node.y;
      })
      .on("drag", (event, node) => {
        node.fx = event.x;
        node.fy = event.y;
      })
      .on("end", (event, node) => {
        if (!event.active) {
          sim.alphaTarget(0);
        }
        node.fx = null;
        node.fy = null;
      });
  }

  onMount(() => {
    ready = true;
    void loadGraph();
  });

  $effect(() => {
    if (!ready) {
      return;
    }
    if (refreshToken !== lastRefresh) {
      lastRefresh = refreshToken;
      void loadGraph();
    }
  });
</script>

<section class="graph-page">
  <div class="hero">
    <div>
      <p class="eyebrow">Knowledge Graph</p>
      <h1>{nodeCount} nodes · {edgeCount} edges</h1>
      <p class="subtle">Click a node to open the article. Export the current view as SVG or PNG.</p>
    </div>
    <div class="actions">
      <button class="secondary" type="button" onclick={exportSvg}>Export SVG</button>
      <button type="button" onclick={() => void exportPng()}>Export PNG</button>
    </div>
  </div>

  <div class="controls">
    <select bind:value={filterCategory} onchange={applyFilter}>
      <option value="">All categories</option>
      {#each categories as category}
        <option value={category}>{category}</option>
      {/each}
    </select>
    <input
      type="text"
      bind:value={searchQuery}
      placeholder="Highlight nodes..."
      oninput={applyFilter}
    />
    <button class="secondary" type="button" onclick={() => void loadGraph()}>Refresh graph</button>
  </div>

  {#if error}
    <p class="error">{error}</p>
  {/if}

  {#if loading}
    <p class="dim">Loading graph…</p>
  {/if}

  <svg bind:this={svgEl} class="graph-svg"></svg>
</section>

<style>
  .graph-page {
    display: flex;
    flex-direction: column;
    gap: 16px;
    min-height: calc(100vh - 48px);
  }

  .hero,
  .controls,
  .graph-svg {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 18px;
    box-shadow: var(--shadow-soft);
  }

  .hero {
    padding: 24px;
    display: flex;
    justify-content: space-between;
    gap: 18px;
    align-items: flex-start;
  }

  .hero h1 {
    margin: 6px 0 8px;
    font-size: clamp(1.6rem, 4vw, 2.8rem);
  }

  .subtle,
  .dim {
    color: var(--text-dim);
  }

  .controls {
    padding: 12px;
    display: grid;
    grid-template-columns: 220px 1fr auto;
    gap: 10px;
  }

  .graph-svg {
    width: 100%;
    min-height: 640px;
    background: radial-gradient(circle at top, #fff8ef, #f4efe7);
  }

  .actions {
    display: flex;
    gap: 10px;
    align-items: center;
  }

  .secondary {
    background: var(--bg-secondary);
    color: var(--text);
    border: 1px solid var(--border);
    box-shadow: none;
  }

  .secondary:hover {
    background: var(--bg-hover);
  }

  .eyebrow {
    text-transform: uppercase;
    letter-spacing: 0.14em;
    font-size: 0.72rem;
    color: var(--accent);
  }

  .error {
    color: var(--red);
  }

  @media (max-width: 840px) {
    .hero {
      flex-direction: column;
    }

    .controls {
      grid-template-columns: 1fr;
    }
  }
</style>
