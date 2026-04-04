<script lang="ts">
  import Viewer from "./pages/Viewer.svelte";
  import Chat from "./pages/Chat.svelte";
  import Search from "./pages/Search.svelte";
  import Graph from "./pages/Graph.svelte";
  import Lint from "./pages/Lint.svelte";
  import Status from "./pages/Status.svelte";

  const pages = ["viewer", "chat", "search", "graph", "lint", "status"] as const;
  type Page = (typeof pages)[number];

  let currentPage: Page = $state("viewer");
</script>

<div class="layout">
  <nav class="sidebar">
    <div class="logo">Compendium</div>
    {#each pages as page}
      <button
        class="nav-btn"
        class:active={currentPage === page}
        onclick={() => (currentPage = page)}
      >
        {page.charAt(0).toUpperCase() + page.slice(1)}
      </button>
    {/each}
  </nav>

  <main class="content">
    {#if currentPage === "viewer"}
      <Viewer />
    {:else if currentPage === "chat"}
      <Chat />
    {:else if currentPage === "search"}
      <Search />
    {:else if currentPage === "graph"}
      <Graph />
    {:else if currentPage === "lint"}
      <Lint />
    {:else if currentPage === "status"}
      <Status />
    {/if}
  </main>
</div>

<style>
  .layout {
    display: flex;
    height: 100vh;
    overflow: hidden;
  }
  .sidebar {
    width: 200px;
    background: var(--bg-secondary);
    border-right: 1px solid var(--border);
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 4px;
    flex-shrink: 0;
  }
  .logo {
    font-size: 18px;
    font-weight: 700;
    color: var(--accent);
    padding: 8px 0 16px;
    border-bottom: 1px solid var(--border);
    margin-bottom: 12px;
  }
  .nav-btn {
    background: none;
    color: var(--text-dim);
    text-align: left;
    padding: 8px 12px;
    border-radius: var(--radius);
    font-size: 14px;
  }
  .nav-btn:hover {
    background: var(--bg-hover);
    color: var(--text);
  }
  .nav-btn.active {
    background: var(--bg-hover);
    color: var(--accent);
  }
  .content {
    flex: 1;
    overflow-y: auto;
    padding: 24px;
  }
</style>
