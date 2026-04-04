<script lang="ts">
  import { onMount } from "svelte";
  import { api, type Health, type Status as ProjectStatus, type UsagePayload } from "../lib/api";

  function formatCurrency(value: number): string {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: "USD",
      minimumFractionDigits: value < 1 ? 4 : 2,
      maximumFractionDigits: value < 1 ? 4 : 2,
    }).format(value || 0);
  }

  function formatNumber(value: number): string {
    return new Intl.NumberFormat("en-US").format(value || 0);
  }

  let health = $state<Health | null>(null);
  let projectStatus = $state<ProjectStatus | null>(null);
  let usage = $state<UsagePayload | null>(null);
  let loading = $state(true);
  let error = $state("");

  async function loadStatus() {
    loading = true;
    error = "";
    try {
      const [healthPayload, statusPayload, usagePayload] = await Promise.all([
        api.health(),
        api.status(),
        api.usage(),
      ]);
      health = healthPayload;
      projectStatus = statusPayload;
      usage = usagePayload;
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    } finally {
      loading = false;
    }
  }

  onMount(() => {
    void loadStatus();
  });
</script>

<section class="status-page">
  <div class="hero">
    <div>
      <p class="eyebrow">Status</p>
      <h1>Project health, coverage, and token spend</h1>
      <p class="subtle">
        Confirm the local service, inspect source and wiki counts, and track monthly usage by
        operation before you kick off larger runs.
      </p>
    </div>
    <button class="secondary" type="button" onclick={() => void loadStatus()}>
      Refresh status
    </button>
  </div>

  {#if error}
    <p class="error">{error}</p>
  {/if}

  {#if loading}
    <p class="dim">Loading status…</p>
  {:else if projectStatus && usage && health}
    <div class="metric-grid">
      <article class="metric-card">
        <p class="eyebrow">Service</p>
        <h2>{health.status}</h2>
        <p class="detail">Version {health.version}</p>
      </article>

      <article class="metric-card">
        <p class="eyebrow">Project</p>
        <h2>{projectStatus.project_name}</h2>
        <p class="detail">Default provider: {projectStatus.default_provider}</p>
      </article>

      <article class="metric-card">
        <p class="eyebrow">Raw sources</p>
        <h2>{formatNumber(projectStatus.raw_source_count)}</h2>
        <p class="detail">Available for compile/update sessions</p>
      </article>

      <article class="metric-card">
        <p class="eyebrow">Wiki articles</p>
        <h2>{formatNumber(projectStatus.wiki_article_count)}</h2>
        <p class="detail">Indexed knowledge pages</p>
      </article>
    </div>

    <div class="panel">
      <div class="panel-header">
        <div>
          <p class="eyebrow">Usage</p>
          <h2>{usage.summary.month}</h2>
        </div>
        <div class="usage-summary">
          <span>{formatNumber(usage.summary.total_tokens)} tokens</span>
          <strong>{formatCurrency(usage.summary.estimated_cost)}</strong>
        </div>
      </div>

      {#if Object.keys(usage.breakdown).length === 0}
        <p class="dim">No tracked usage for this month yet.</p>
      {:else}
        <div class="usage-table">
          <div class="usage-row usage-head">
            <span>Operation</span>
            <span>Tokens</span>
            <span>Estimated cost</span>
          </div>
          {#each Object.entries(usage.breakdown) as [operation, totals]}
            <div class="usage-row">
              <span>{operation}</span>
              <span>{formatNumber(totals.tokens)}</span>
              <span>{formatCurrency(totals.estimated_cost)}</span>
            </div>
          {/each}
        </div>
      {/if}
    </div>
  {/if}
</section>

<style>
  .status-page {
    display: flex;
    flex-direction: column;
    gap: 20px;
  }

  .hero,
  .panel,
  .metric-card {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 20px;
    padding: 20px;
    box-shadow: var(--shadow-soft);
  }

  .hero,
  .panel-header,
  .usage-summary,
  .usage-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
  }

  .hero {
    align-items: flex-start;
  }

  .hero h1,
  .panel h2,
  .metric-card h2 {
    margin: 6px 0 8px;
  }

  .subtle,
  .detail,
  .dim {
    color: var(--text-dim);
  }

  .metric-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 16px;
  }

  .metric-card h2 {
    font-size: 1.8rem;
  }

  .usage-summary {
    color: var(--text-dim);
  }

  .usage-summary strong {
    color: var(--accent-strong);
    font-size: 1.1rem;
  }

  .usage-table {
    display: flex;
    flex-direction: column;
    margin-top: 16px;
    border-top: 1px solid var(--border);
  }

  .usage-row {
    padding: 12px 0;
    border-bottom: 1px solid var(--border);
    display: grid;
    grid-template-columns: 1.4fr 1fr 1fr;
  }

  .usage-head {
    font-size: 0.84rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--text-dim);
  }

  .secondary {
    background: transparent;
    color: var(--accent-strong);
    border: 1px solid rgba(60, 91, 168, 0.22);
    box-shadow: none;
  }

  .secondary:hover {
    background: var(--accent-soft);
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

  @media (max-width: 760px) {
    .hero,
    .panel-header {
      flex-direction: column;
      align-items: flex-start;
    }

    .metric-grid {
      grid-template-columns: 1fr;
    }

    .usage-row {
      grid-template-columns: 1fr;
      gap: 6px;
    }
  }
</style>
