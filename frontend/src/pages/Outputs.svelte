<script lang="ts">
  import Markdown from "../components/Markdown.svelte";
  import { api, type AskResult, type FilingResult } from "../lib/api";
  import { toProjectRelativePath } from "../lib/format";

  interface Props {
    onContentChanged?: () => void;
    onOpenArticle?: (path: string) => void;
  }

  type OutputMode = "text" | "report" | "slides" | "html" | "chart";

  let { onContentChanged = () => {}, onOpenArticle = () => {} }: Props = $props();

  let question = $state("");
  let outputMode = $state<OutputMode>("text");
  let slideCount = $state(10);
  let autoFile = $state(false);
  let defaultResolution = $state<"" | "merge" | "replace" | "keep_both">("");
  let loading = $state(false);
  let result: AskResult | null = $state(null);
  let filingResult: FilingResult | null = $state(null);
  let error = $state("");

  async function runOutput() {
    if (!question.trim()) {
      return;
    }

    loading = true;
    error = "";
    filingResult = null;
    try {
      result = await api.ask({
        question,
        output: outputMode,
        sessionId: "web-outputs",
        file: autoFile && outputMode !== "text",
        resolution: defaultResolution || undefined,
        count: outputMode === "slides" ? slideCount : undefined,
      });
      filingResult = result.filing ?? null;
      if (filingResult?.status === "filed") {
        onContentChanged();
      }
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    } finally {
      loading = false;
    }
  }

  async function resolveFiling(resolution: "merge" | "replace" | "keep_both" | "cancel") {
    if (!result?.output_path) {
      return;
    }
    loading = true;
    error = "";
    try {
      filingResult = await api.fileToWiki(result.output_path, resolution);
      result = { ...result, filing: filingResult };
      if (filingResult.status === "filed") {
        onContentChanged();
      }
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    } finally {
      loading = false;
    }
  }

  function openFiledArticle() {
    const relative = toProjectRelativePath(filingResult?.filed_path);
    if (relative) {
      onOpenArticle(relative);
    }
  }
</script>

<section class="outputs-page">
  <div class="hero">
    <div>
      <p class="eyebrow">Outputs</p>
      <h1>Ask the wiki and render deliverables</h1>
      <p class="subtle">
        Generate text, reports, slides, standalone HTML, or charts, then decide whether to file
        the result back into the wiki.
      </p>
    </div>
  </div>

  <div class="panel composer">
    <label class="field">
      <span>Question</span>
      <textarea bind:value={question} rows="5" placeholder="What should Compendium answer?"></textarea>
    </label>

    <div class="row">
      <label class="field">
        <span>Output</span>
        <select bind:value={outputMode}>
          <option value="text">Text</option>
          <option value="report">Report</option>
          <option value="slides">Slides</option>
          <option value="html">HTML</option>
          <option value="chart">Chart</option>
        </select>
      </label>

      {#if outputMode === "slides"}
        <label class="field compact">
          <span>Slides</span>
          <input type="number" min="4" max="20" bind:value={slideCount} />
        </label>
      {/if}

      {#if outputMode !== "text"}
        <label class="field">
          <span>Default filing resolution</span>
          <select bind:value={defaultResolution}>
            <option value="">Ask later</option>
            <option value="merge">Merge</option>
            <option value="replace">Replace</option>
            <option value="keep_both">Keep both</option>
          </select>
        </label>
      {/if}
    </div>

    {#if outputMode !== "text"}
      <label class="checkbox">
        <input type="checkbox" bind:checked={autoFile} />
        <span>Prompt filing automatically after rendering</span>
      </label>
    {/if}

    <button type="button" onclick={() => void runOutput()} disabled={loading || !question.trim()}>
      {loading ? "Generating…" : "Generate output"}
    </button>

    {#if error}
      <p class="error">{error}</p>
    {/if}
  </div>

  {#if result}
    <div class="panel result-panel">
      <div class="result-header">
        <div>
          <p class="eyebrow">Answer</p>
          <h2>{outputMode === "text" ? "Inline response" : `${outputMode} output ready`}</h2>
        </div>
        <div class="meta">
          <span>{result.articles_loaded} articles loaded</span>
          <span>{result.tokens_used} tokens</span>
        </div>
      </div>

      <Markdown source={result.answer} />

      {#if result.sources_used.length > 0}
        <div class="sources">
          <h3>Sources consulted</h3>
          <ul>
            {#each result.sources_used as source}
              <li>{source}</li>
            {/each}
          </ul>
        </div>
      {/if}

      {#if result.output_path}
        <div class="artifacts">
          <h3>Generated files</h3>
          <a href={api.downloadUrl(result.output_path)} target="_blank">{result.output_path}</a>
          {#each result.extra_paths ?? [] as extraPath}
            <a href={api.downloadUrl(extraPath)} target="_blank">{extraPath}</a>
          {/each}
        </div>
      {/if}

      {#if outputMode === "html" && result.output_path}
        <iframe title="HTML output preview" class="preview-frame" src={api.downloadUrl(result.output_path)}></iframe>
      {/if}

      {#if outputMode === "chart" && result.extra_paths?.[0]}
        <img
          class="chart-preview"
          src={api.downloadUrl(result.extra_paths[0])}
          alt="Chart preview"
        />
      {/if}
    </div>

    {#if outputMode !== "text" && result.output_path}
      <div class="panel filing-panel">
        <div class="result-header">
          <div>
            <p class="eyebrow">File output</p>
            <h2>Decide how this output should enter the wiki</h2>
          </div>
          {#if filingResult?.status === "filed"}
            <button class="secondary" type="button" onclick={openFiledArticle}>Open filed article</button>
          {/if}
        </div>

        {#if filingResult}
          <div class="filing-status">
            <strong>{filingResult.status}</strong>
            {#if filingResult.message}
              <span>{filingResult.message}</span>
            {/if}
            {#if filingResult.filed_path}
              <span>{filingResult.filed_path}</span>
            {/if}
          </div>
        {/if}

        {#if !filingResult || filingResult.status === "similar"}
          <div class="actions">
            <button type="button" onclick={() => void resolveFiling("merge")} disabled={loading}>
              Merge
            </button>
            <button type="button" onclick={() => void resolveFiling("replace")} disabled={loading}>
              Replace
            </button>
            <button
              class="secondary"
              type="button"
              onclick={() => void resolveFiling("keep_both")}
              disabled={loading}
            >
              Keep both
            </button>
            <button
              class="secondary"
              type="button"
              onclick={() => void resolveFiling("cancel")}
              disabled={loading}
            >
              Cancel
            </button>
          </div>
        {:else if filingResult.status === "duplicate"}
          <p class="dim">This output already exists verbatim in the wiki.</p>
        {:else if filingResult.status === "filed"}
          <p class="dim">Filed and committed successfully.</p>
        {/if}
      </div>
    {/if}
  {/if}
</section>

<style>
  .outputs-page,
  .composer,
  .sources,
  .artifacts,
  .filing-panel {
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  .hero,
  .panel {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 18px;
    box-shadow: var(--shadow-soft);
  }

  .hero,
  .panel {
    padding: 24px;
  }

  .hero h1 {
    margin: 6px 0 8px;
    font-size: clamp(1.8rem, 4vw, 2.8rem);
  }

  .row,
  .result-header,
  .actions {
    display: flex;
    gap: 12px;
    align-items: flex-start;
    justify-content: space-between;
    flex-wrap: wrap;
  }

  .field {
    display: flex;
    flex-direction: column;
    gap: 8px;
    flex: 1;
  }

  .field.compact {
    max-width: 130px;
  }

  .field span,
  .subtle,
  .dim,
  .meta,
  .filing-status span {
    color: var(--text-dim);
  }

  .checkbox {
    display: inline-flex;
    align-items: center;
    gap: 8px;
  }

  .meta {
    display: flex;
    gap: 12px;
    font-size: 0.9rem;
  }

  .artifacts a {
    width: fit-content;
  }

  .preview-frame {
    width: 100%;
    min-height: 520px;
    border: 1px solid var(--border);
    border-radius: 14px;
    background: white;
  }

  .chart-preview {
    width: 100%;
    max-width: 780px;
    border: 1px solid var(--border);
    border-radius: 14px;
    background: white;
  }

  .filing-status {
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding: 14px 16px;
    border: 1px solid var(--border);
    border-radius: 14px;
    background: var(--bg-secondary);
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

  @media (max-width: 860px) {
    .row {
      flex-direction: column;
    }
  }
</style>
