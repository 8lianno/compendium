<script lang="ts">
  import Compile from "./pages/Compile.svelte";
  import Graph from "./pages/Graph.svelte";
  import Ingest from "./pages/Ingest.svelte";
  import Lint from "./pages/Lint.svelte";
  import Outputs from "./pages/Outputs.svelte";
  import Search from "./pages/Search.svelte";
  import Settings from "./pages/Settings.svelte";
  import Status from "./pages/Status.svelte";
  import Viewer from "./pages/Viewer.svelte";

  const pages = [
    { id: "library", label: "Library" },
    { id: "ingest", label: "Ingest" },
    { id: "compile", label: "Compile / Update" },
    { id: "outputs", label: "Outputs" },
    { id: "search", label: "Search" },
    { id: "graph", label: "Graph" },
    { id: "lint", label: "Lint" },
    { id: "settings", label: "Settings" },
    { id: "status", label: "Status" },
  ] as const;

  type Page = (typeof pages)[number]["id"];

  let currentPage = $state<Page>("library");
  let selectedArticlePath = $state<string | null>(null);
  let refreshToken = $state(0);

  function openArticle(path: string) {
    selectedArticlePath = path;
    currentPage = "library";
  }

  function markContentChanged() {
    refreshToken += 1;
  }
</script>

<div class="layout">
  <nav class="sidebar">
    <div class="brand">
      <span class="eyebrow">Compendium</span>
      <h1>v1.0 operations</h1>
      <p>Compile, query, file, lint, and inspect the knowledge graph from one local app.</p>
    </div>

    <div class="nav-list">
      {#each pages as page}
        <button
          class="nav-btn"
          class:active={currentPage === page.id}
          type="button"
          onclick={() => (currentPage = page.id)}
        >
          {page.label}
        </button>
      {/each}
    </div>
  </nav>

  <main class="content">
    {#if currentPage === "library"}
      <Viewer
        selectedPath={selectedArticlePath}
        refreshToken={refreshToken}
        onSelect={(path) => (selectedArticlePath = path)}
      />
    {:else if currentPage === "ingest"}
      <Ingest onContentChanged={markContentChanged} />
    {:else if currentPage === "compile"}
      <Compile onContentChanged={markContentChanged} refreshToken={refreshToken} />
    {:else if currentPage === "outputs"}
      <Outputs onContentChanged={markContentChanged} onOpenArticle={openArticle} />
    {:else if currentPage === "search"}
      <Search onOpenArticle={openArticle} refreshToken={refreshToken} />
    {:else if currentPage === "graph"}
      <Graph onOpenArticle={openArticle} refreshToken={refreshToken} />
    {:else if currentPage === "lint"}
      <Lint />
    {:else if currentPage === "settings"}
      <Settings onContentChanged={markContentChanged} />
    {:else if currentPage === "status"}
      <Status />
    {/if}
  </main>
</div>

<style>
  .layout {
    display: grid;
    grid-template-columns: 290px 1fr;
    min-height: 100vh;
    background:
      radial-gradient(circle at top left, rgba(194, 137, 82, 0.16), transparent 28%),
      radial-gradient(circle at bottom left, rgba(57, 87, 151, 0.18), transparent 32%),
      var(--bg);
  }

  .sidebar {
    padding: 24px 20px;
    border-right: 1px solid var(--border);
    background: rgba(251, 246, 238, 0.76);
    backdrop-filter: blur(22px);
    display: flex;
    flex-direction: column;
    gap: 24px;
  }

  .brand {
    padding: 18px;
    border: 1px solid var(--border);
    border-radius: 20px;
    background: var(--panel);
    box-shadow: var(--shadow-soft);
  }

  .brand h1 {
    margin: 6px 0 8px;
    font-size: 1.45rem;
  }

  .brand p {
    color: var(--text-dim);
    font-size: 0.92rem;
  }

  .eyebrow {
    text-transform: uppercase;
    letter-spacing: 0.14em;
    font-size: 0.72rem;
    color: var(--accent);
  }

  .nav-list {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .nav-btn {
    text-align: left;
    padding: 12px 14px;
    border-radius: 14px;
    background: transparent;
    color: var(--text-dim);
    border: 1px solid transparent;
    box-shadow: none;
  }

  .nav-btn:hover {
    background: var(--bg-hover);
    color: var(--text);
    border-color: var(--border);
  }

  .nav-btn.active {
    background: var(--accent-soft);
    color: var(--accent-strong);
    border-color: rgba(60, 91, 168, 0.22);
  }

  .content {
    padding: 24px;
    overflow-y: auto;
  }

  @media (max-width: 980px) {
    .layout {
      grid-template-columns: 1fr;
    }

    .sidebar {
      border-right: 0;
      border-bottom: 1px solid var(--border);
    }

    .nav-list {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
  }

  @media (max-width: 620px) {
    .content {
      padding: 16px;
    }

    .nav-list {
      grid-template-columns: 1fr;
    }
  }
</style>
