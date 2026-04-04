<script lang="ts">
  import { onMount } from "svelte";
  import { api, type ItemPath, type SessionSummary } from "../lib/api";

  interface Props {
    onContentChanged?: () => void;
    refreshToken?: number;
  }

  let { onContentChanged = () => {}, refreshToken = 0 }: Props = $props();

  let sources: ItemPath[] = $state([]);
  let loadingSources = $state(true);
  let compileMode = $state<"interactive" | "batch">("interactive");
  let compileBranch = $state("");
  let compileSession: SessionSummary | null = $state(null);
  let compileSummaryEditor = $state("");
  let compileBusy = $state(false);
  let compileError = $state("");

  let updateUseAllNew = $state(true);
  let selectedUpdatePaths = $state<string[]>([]);
  let updateBranch = $state("");
  let updateSession: SessionSummary | null = $state(null);
  let updateBusy = $state(false);
  let updateError = $state("");
  let lastRefresh = -1;

  async function loadSources() {
    loadingSources = true;
    try {
      sources = await api.sources();
    } catch (err) {
      compileError = err instanceof Error ? err.message : String(err);
    } finally {
      loadingSources = false;
    }
  }

  function syncSummaryEditor(session: SessionSummary | null) {
    compileSummaryEditor = session?.pending_summary
      ? JSON.stringify(session.pending_summary, null, 2)
      : "";
  }

  async function startCompile() {
    compileBusy = true;
    compileError = "";
    try {
      compileSession = await api.startCompileSession({
        mode: compileMode,
        branch: compileBranch.trim() || undefined,
      });
      syncSummaryEditor(compileSession);
      if (compileSession.status === "completed") {
        onContentChanged();
      }
    } catch (err) {
      compileError = err instanceof Error ? err.message : String(err);
    } finally {
      compileBusy = false;
    }
  }

  async function approveSummary(approve: boolean) {
    if (!compileSession) {
      return;
    }

    compileBusy = true;
    compileError = "";
    try {
      const payload: { approve: boolean; summary_override?: Record<string, unknown> } = { approve };
      if (approve && compileSummaryEditor.trim()) {
        payload.summary_override = JSON.parse(compileSummaryEditor) as Record<string, unknown>;
      }
      compileSession = await api.approveCompileSession(compileSession.session_id, payload);
      syncSummaryEditor(compileSession);
      if (compileSession.status === "completed") {
        onContentChanged();
      }
    } catch (err) {
      compileError = err instanceof Error ? err.message : String(err);
    } finally {
      compileBusy = false;
    }
  }

  function toggleUpdatePath(path: string) {
    if (selectedUpdatePaths.includes(path)) {
      selectedUpdatePaths = selectedUpdatePaths.filter((item) => item !== path);
    } else {
      selectedUpdatePaths = [...selectedUpdatePaths, path];
    }
  }

  async function startUpdate() {
    updateBusy = true;
    updateError = "";
    try {
      updateSession = await api.startUpdateSession({
        paths: updateUseAllNew ? undefined : selectedUpdatePaths,
        branch: updateBranch.trim() || undefined,
      });
      if (updateSession.status === "completed") {
        onContentChanged();
      }
    } catch (err) {
      updateError = err instanceof Error ? err.message : String(err);
    } finally {
      updateBusy = false;
    }
  }

  onMount(() => {
    void loadSources();
  });

  $effect(() => {
    if (refreshToken !== lastRefresh) {
      lastRefresh = refreshToken;
      void loadSources();
    }
  });
</script>

<section class="compile-page">
  <div class="hero">
    <div>
      <p class="eyebrow">Compile / Update</p>
      <h1>Run batch or human-in-the-loop rebuilds</h1>
      <p class="subtle">
        Interactive compile pauses after each summary for approval. Update runs incremental rebuilds
        against all new or selected raw sources.
      </p>
    </div>
    <button class="secondary" type="button" onclick={() => void loadSources()}>
      Refresh sources
    </button>
  </div>

  <div class="layout">
    <div class="panel">
      <div class="panel-header">
        <div>
          <p class="eyebrow">Full compile</p>
          <h2>Rebuild the wiki</h2>
        </div>
        {#if compileSession?.audit_log_path}
          <a class="pill-link" href={api.downloadUrl(compileSession.audit_log_path)} target="_blank">
            Download audit log
          </a>
        {/if}
      </div>

      <div class="form-grid">
        <label class="field">
          <span>Mode</span>
          <select bind:value={compileMode}>
            <option value="interactive">Interactive</option>
            <option value="batch">Batch</option>
          </select>
        </label>
        <label class="field">
          <span>Experimental branch</span>
          <input bind:value={compileBranch} placeholder="feature/rebuild-pass" />
        </label>
      </div>

      <button type="button" onclick={() => void startCompile()} disabled={compileBusy}>
        {compileBusy ? "Running…" : `Start ${compileMode} compile`}
      </button>

      {#if compileError}
        <p class="error">{compileError}</p>
      {/if}

      {#if compileSession}
        <div class="session-card">
          <div class="session-top">
            <strong>{compileSession.status}</strong>
            <span class="dim">
              {compileSession.current_index + (compileSession.pending_summary ? 1 : 0)}/
              {compileSession.source_count} reviewed
            </span>
          </div>

          {#if compileSession.pending_source}
            <div class="pending-source">
              <p class="eyebrow">Pending source</p>
              <h3>{compileSession.pending_source.title}</h3>
              <p class="dim">{compileSession.pending_source.path}</p>
            </div>
          {/if}

          {#if compileSession.pending_summary}
            <label class="field">
              <span>Editable summary JSON</span>
              <textarea bind:value={compileSummaryEditor} rows="14"></textarea>
            </label>
            <div class="actions">
              <button type="button" onclick={() => void approveSummary(true)} disabled={compileBusy}>
                Approve and continue
              </button>
              <button
                class="secondary"
                type="button"
                onclick={() => void approveSummary(false)}
                disabled={compileBusy}
              >
                Cancel session
              </button>
            </div>
          {/if}

          {#if compileSession.result}
            <pre>{JSON.stringify(compileSession.result, null, 2)}</pre>
          {/if}

          {#if compileSession.error}
            <p class="error">{compileSession.error}</p>
          {/if}
        </div>
      {/if}
    </div>

    <div class="panel">
      <div class="panel-header">
        <div>
          <p class="eyebrow">Incremental update</p>
          <h2>Compile only new material</h2>
        </div>
        {#if updateSession?.audit_log_path}
          <a class="pill-link" href={api.downloadUrl(updateSession.audit_log_path)} target="_blank">
            Download audit log
          </a>
        {/if}
      </div>

      <label class="checkbox">
        <input type="checkbox" bind:checked={updateUseAllNew} />
        <span>Use automatic all-new detection</span>
      </label>

      <label class="field">
        <span>Experimental branch</span>
        <input bind:value={updateBranch} placeholder="feature/incremental-pass" />
      </label>

      {#if !updateUseAllNew}
        <div class="source-picker">
          {#if loadingSources}
            <p class="dim">Loading sources…</p>
          {:else}
            {#each sources as source}
              <label class="checkbox">
                <input
                  type="checkbox"
                  checked={selectedUpdatePaths.includes(source.path)}
                  onchange={() => toggleUpdatePath(source.path)}
                />
                <span>{source.name}</span>
                <small>{source.path}</small>
              </label>
            {/each}
          {/if}
        </div>
      {/if}

      <button
        type="button"
        onclick={() => void startUpdate()}
        disabled={updateBusy || (!updateUseAllNew && selectedUpdatePaths.length === 0)}
      >
        {updateBusy ? "Updating…" : "Run incremental update"}
      </button>

      {#if updateError}
        <p class="error">{updateError}</p>
      {/if}

      {#if updateSession}
        <div class="session-card">
          <div class="session-top">
            <strong>{updateSession.status}</strong>
            <span class="dim">{updateSession.source_count} explicit sources</span>
          </div>
          {#if updateSession.result}
            <pre>{JSON.stringify(updateSession.result, null, 2)}</pre>
          {/if}
          {#if updateSession.error}
            <p class="error">{updateSession.error}</p>
          {/if}
        </div>
      {/if}
    </div>
  </div>
</section>

<style>
  .compile-page,
  .layout {
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  .hero,
  .panel,
  .session-card {
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
    font-size: clamp(1.8rem, 4vw, 2.8rem);
  }

  .layout {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .panel {
    padding: 20px;
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  .panel-header,
  .session-top,
  .actions {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    align-items: center;
  }

  .form-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 12px;
  }

  .field {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .field span,
  .dim,
  .checkbox small {
    color: var(--text-dim);
  }

  .session-card {
    padding: 16px;
  }

  .pending-source h3 {
    margin: 4px 0 6px;
  }

  .checkbox {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 8px;
    align-items: start;
  }

  .checkbox small {
    grid-column: 2;
    font-size: 0.78rem;
  }

  .source-picker {
    display: flex;
    flex-direction: column;
    gap: 10px;
    max-height: 280px;
    overflow-y: auto;
    padding-right: 4px;
  }

  .pill-link {
    display: inline-flex;
    align-items: center;
    padding: 8px 12px;
    border: 1px solid var(--border);
    border-radius: 999px;
    background: var(--bg-secondary);
    color: var(--text);
    font-size: 0.86rem;
  }

  .pill-link:hover {
    background: var(--bg-hover);
    color: var(--text);
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

  .subtle {
    color: var(--text-dim);
  }

  .error {
    color: var(--red);
  }

  pre {
    background: var(--bg-secondary);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 14px;
    overflow-x: auto;
    font-size: 0.82rem;
  }

  @media (max-width: 980px) {
    .hero,
    .layout,
    .form-grid {
      grid-template-columns: 1fr;
      flex-direction: column;
    }
  }
</style>
