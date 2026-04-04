<script lang="ts">
  import { onMount } from "svelte";
  import * as d3 from "d3";
  import { api } from "../lib/api";

  interface Node extends d3.SimulationNodeDatum {
    id: string;
    name: string;
    category: string;
    links: number;
  }

  interface Link extends d3.SimulationLinkDatum<Node> {
    source: string | Node;
    target: string | Node;
  }

  let svgEl: SVGSVGElement;
  let loading = $state(true);
  let nodeCount = $state(0);
  let edgeCount = $state(0);
  let categories: string[] = $state([]);
  let filterCategory = $state("");
  let searchQuery = $state("");

  let allNodes: Node[] = [];
  let allLinks: Link[] = [];
  let simulation: d3.Simulation<Node, Link> | null = null;

  onMount(async () => {
    try {
      const data = await api.graph();
      if (data.node_count === 0) {
        loading = false;
        return;
      }

      allNodes = data.nodes.map((n) => ({ ...n }));
      allLinks = data.edges.map((e) => ({ ...e }));
      nodeCount = data.node_count;
      edgeCount = data.edge_count;
      categories = [...new Set(allNodes.map((n) => n.category))].sort();
      loading = false;

      renderGraph(allNodes, allLinks);
    } catch {
      loading = false;
    }
  });

  function getFilteredData(): { nodes: Node[]; links: Link[] } {
    let nodes = allNodes;
    if (filterCategory) {
      const keep = new Set(
        allNodes.filter((n) => n.category === filterCategory).map((n) => n.id)
      );
      // Also include nodes linked from/to the category
      for (const l of allLinks) {
        const s = typeof l.source === "string" ? l.source : l.source.id;
        const t = typeof l.target === "string" ? l.target : l.target.id;
        if (keep.has(s)) keep.add(t);
        if (keep.has(t)) keep.add(s);
      }
      nodes = allNodes.filter((n) => keep.has(n.id));
    }
    const nodeIds = new Set(nodes.map((n) => n.id));
    const links = allLinks.filter((l) => {
      const s = typeof l.source === "string" ? l.source : l.source.id;
      const t = typeof l.target === "string" ? l.target : l.target.id;
      return nodeIds.has(s) && nodeIds.has(t);
    });
    return { nodes, links };
  }

  function applyFilter() {
    const { nodes, links } = getFilteredData();
    renderGraph(nodes, links);
  }

  function exportSVG() {
    if (!svgEl) return;
    const svgData = new XMLSerializer().serializeToString(svgEl);
    const blob = new Blob([svgData], { type: "image/svg+xml" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "knowledge-graph.svg";
    a.click();
    URL.revokeObjectURL(url);
  }

  function renderGraph(nodes: Node[], links: Link[]) {
    const width = svgEl.clientWidth || 800;
    const height = svgEl.clientHeight || 600;

    const colorScale = d3.scaleOrdinal(d3.schemeTableau10);

    if (simulation) simulation.stop();
    simulation = d3
      .forceSimulation(nodes)
      .force("link", d3.forceLink<Node, Link>(links).id((d) => d.id).distance(80))
      .force("charge", d3.forceManyBody().strength(-200))
      .force("center", d3.forceCenter(width / 2, height / 2))
      .force("collision", d3.forceCollide().radius(30));

    const svg = d3.select(svgEl).attr("viewBox", `0 0 ${width} ${height}`);
    svg.selectAll("*").remove();

    const g = svg.append("g");
    svg.call(
      d3.zoom<SVGSVGElement, unknown>().scaleExtent([0.2, 5]).on("zoom", (e) => {
        g.attr("transform", e.transform);
      }) as any
    );

    const link = g
      .append("g")
      .selectAll("line")
      .data(links)
      .join("line")
      .attr("stroke", "#333")
      .attr("stroke-width", 1)
      .attr("stroke-opacity", 0.6);

    const node = g
      .append("g")
      .selectAll("circle")
      .data(nodes)
      .join("circle")
      .attr("r", (d) => 6 + Math.min(d.links * 2, 14))
      .attr("fill", (d) => colorScale(d.category))
      .attr("stroke", "#1a1d27")
      .attr("stroke-width", 1.5)
      .attr("class", (d) =>
        searchQuery && d.name.toLowerCase().includes(searchQuery.toLowerCase())
          ? "highlighted"
          : ""
      )
      .call(drag(simulation) as any);

    const label = g
      .append("g")
      .selectAll("text")
      .data(nodes)
      .join("text")
      .text((d) => d.name)
      .attr("font-size", 11)
      .attr("fill", (d) =>
        searchQuery && d.name.toLowerCase().includes(searchQuery.toLowerCase())
          ? "#fff"
          : "#999"
      )
      .attr("font-weight", (d) =>
        searchQuery && d.name.toLowerCase().includes(searchQuery.toLowerCase())
          ? "bold"
          : "normal"
      )
      .attr("dx", 12)
      .attr("dy", 4);

    node.append("title").text((d) => `${d.name}\nCategory: ${d.category}\nLinks: ${d.links}`);

    simulation.on("tick", () => {
      link
        .attr("x1", (d: any) => d.source.x)
        .attr("y1", (d: any) => d.source.y)
        .attr("x2", (d: any) => d.target.x)
        .attr("y2", (d: any) => d.target.y);
      node.attr("cx", (d: any) => d.x).attr("cy", (d: any) => d.y);
      label.attr("x", (d: any) => d.x).attr("y", (d: any) => d.y);
    });
  }

  function drag(sim: d3.Simulation<Node, Link>) {
    return d3
      .drag<SVGCircleElement, Node>()
      .on("start", (event, d) => {
        if (!event.active) sim.alphaTarget(0.3).restart();
        d.fx = d.x;
        d.fy = d.y;
      })
      .on("drag", (event, d) => {
        d.fx = event.x;
        d.fy = event.y;
      })
      .on("end", (event, d) => {
        if (!event.active) sim.alphaTarget(0);
        d.fx = null;
        d.fy = null;
      });
  }
</script>

<div class="graph-page">
  <div class="header">
    <h1>Knowledge Graph</h1>
    {#if nodeCount > 0}
      <span class="stats">{nodeCount} nodes &middot; {edgeCount} edges</span>
    {/if}
  </div>

  {#if !loading && nodeCount > 0}
    <div class="controls">
      <select bind:value={filterCategory} onchange={applyFilter}>
        <option value="">All categories</option>
        {#each categories as cat}
          <option value={cat}>{cat}</option>
        {/each}
      </select>
      <input
        type="text"
        bind:value={searchQuery}
        placeholder="Search nodes..."
        oninput={applyFilter}
      />
      <button onclick={exportSVG}>Export SVG</button>
    </div>
  {/if}

  {#if loading}
    <p class="dim">Loading graph...</p>
  {:else if nodeCount === 0}
    <p class="dim">No articles to visualize. Compile your wiki first.</p>
  {/if}
  <svg bind:this={svgEl} class="graph-svg"></svg>
</div>

<style>
  .graph-page { height: calc(100vh - 48px); display: flex; flex-direction: column; }
  .header { display: flex; align-items: baseline; gap: 16px; margin-bottom: 8px; }
  .stats { color: var(--text-dim); font-size: 13px; }
  .controls { display: flex; gap: 8px; margin-bottom: 8px; }
  .controls select, .controls input { width: auto; flex: 0 0 auto; }
  .controls input { flex: 1; }
  .controls button { flex: 0 0 auto; font-size: 12px; padding: 6px 12px; }
  .graph-svg { flex: 1; width: 100%; background: var(--bg); border-radius: var(--radius); }
  .dim { color: var(--text-dim); }
  :global(.highlighted) { stroke: #6c8cff !important; stroke-width: 3px !important; }
</style>
