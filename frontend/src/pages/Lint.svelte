<script lang="ts">
  import { api, type LintResult } from "../lib/api";

  let result: LintResult | null = $state(null);
  let loading = $state(false);
  let error = $state("");

  async function runLint() {
    loading = true;
    error = "";
    try {
      result = await api.lint();
    } catch (e) {
      error = String(e);
    } finally {
      loading = false;
    }
  }

  function severityColor(s: string): string {
    if (s === "critical") return "var(--red)";
    if (s === "warning") return "var(--yellow)";
    return "var(--text-dim)";
  }
</script>

<div class="lint-page">
  <div class="header">
    <h1>Wiki Health Check</h1>
    <button onclick={runLint} disabled={loading}>
      {loading ? "Running..." : "Run Lint"}
    </button>
  </div>

  {#if error}
    <p class="error">{error}</p>
  {/if}

  {#if result}
    <div class="summary">
      <div class="stat">
        <span class="count">{result.total}</span>
        <span class="label">Total</span>
      </div>
      <div class="stat">
        <span class="count" style="color: var(--red)">{result.critical}</span>
        <span class="label">Critical</span>
      </div>
      <div class="stat">
        <span class="count" style="color: var(--yellow)">{result.warning}</span>
        <span class="label">Warning</span>
      </div>
      <div class="stat">
        <span class="count" style="color: var(--text-dim)">{result.info}</span>
        <span class="label">Info</span>
      </div>
    </div>

    {#if result.issues.length === 0}
      <p class="success">No issues found. Wiki is healthy!</p>
    {:else}
      <div class="issues">
        {#each result.issues as issue}
          <div class="issue">
            <span class="severity" style="color: {severityColor(issue.severity)}">
              {issue.severity.toUpperCase()}
            </span>
            <span class="location">{issue.location}</span>
            <span class="description">{issue.description}</span>
            {#if issue.suggestion}
              <span class="suggestion">{issue.suggestion}</span>
            {/if}
          </div>
        {/each}
      </div>
    {/if}
  {:else if !loading}
    <p class="dim">Click "Run Lint" to check wiki health.</p>
  {/if}
</div>

<style>
  .lint-page h1 { margin-bottom: 0; }
  .header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px; }
  .summary { display: flex; gap: 24px; margin-bottom: 20px; }
  .stat { display: flex; flex-direction: column; align-items: center; }
  .stat .count { font-size: 28px; font-weight: 700; }
  .stat .label { font-size: 12px; color: var(--text-dim); }
  .issues { display: flex; flex-direction: column; gap: 8px; }
  .issue {
    display: grid;
    grid-template-columns: 70px 150px 1fr;
    gap: 8px;
    padding: 10px 14px;
    background: var(--bg-secondary);
    border-radius: var(--radius);
    font-size: 13px;
    align-items: start;
  }
  .severity { font-weight: 700; font-size: 11px; }
  .location { color: var(--accent); }
  .description { color: var(--text); }
  .suggestion { grid-column: 3; color: var(--text-dim); font-size: 12px; }
  .dim { color: var(--text-dim); }
  .success { color: var(--green); font-weight: 600; }
  .error { color: var(--red); }
</style>
