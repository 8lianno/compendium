<script lang="ts">
  import { api, type Status as StatusType } from "../lib/api";

  let status: StatusType | null = $state(null);
  let version = $state("");
  let loading = $state(true);

  async function load() {
    try {
      const [s, h] = await Promise.all([api.status(), api.health()]);
      status = s;
      version = h.version;
    } catch {
      // Server might not be running
    } finally {
      loading = false;
    }
  }

  load();
</script>

<div class="status-page">
  <h1>Project Status</h1>

  {#if loading}
    <p class="dim">Loading...</p>
  {:else if status}
    <div class="cards">
      <div class="card">
        <div class="value">{status.project_name}</div>
        <div class="label">Project</div>
      </div>
      <div class="card">
        <div class="value">{status.raw_source_count}</div>
        <div class="label">Raw Sources</div>
      </div>
      <div class="card">
        <div class="value">{status.wiki_article_count}</div>
        <div class="label">Wiki Articles</div>
      </div>
      <div class="card">
        <div class="value">{status.default_provider}</div>
        <div class="label">LLM Provider</div>
      </div>
    </div>

    <div class="info">
      <p>Compendium v{version}</p>
      <p class="dim">
        Manage your project via CLI: <code>compendium --help</code>
      </p>
    </div>
  {:else}
    <p class="dim">Could not connect to Compendium server.</p>
  {/if}
</div>

<style>
  .status-page h1 { margin-bottom: 24px; }
  .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px; margin-bottom: 32px; }
  .card {
    background: var(--bg-secondary);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 20px;
    text-align: center;
  }
  .card .value { font-size: 24px; font-weight: 700; color: var(--accent); }
  .card .label { font-size: 12px; color: var(--text-dim); margin-top: 4px; }
  .info { margin-top: 24px; }
  .info code { background: var(--bg-secondary); padding: 2px 6px; border-radius: 4px; }
  .dim { color: var(--text-dim); }
</style>
