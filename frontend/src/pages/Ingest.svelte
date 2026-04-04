<script lang="ts">
  import { onMount } from "svelte";
  import { api, type ItemPath, type UploadResponse } from "../lib/api";

  interface Props {
    onContentChanged?: () => void;
  }

  let { onContentChanged = () => {} }: Props = $props();

  let duplicateMode = $state("keep_both");
  let selectedFiles: File[] = $state([]);
  let uploadResult: UploadResponse | null = $state(null);
  let sources: ItemPath[] = $state([]);
  let loadingSources = $state(true);
  let dragging = $state(false);
  let uploading = $state(false);
  let error = $state("");

  async function loadSources() {
    loadingSources = true;
    try {
      sources = await api.sources();
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    } finally {
      loadingSources = false;
    }
  }

  function setFiles(files: FileList | File[] | null) {
    if (!files) {
      return;
    }
    selectedFiles = Array.from(files);
    uploadResult = null;
    error = "";
  }

  async function uploadFiles() {
    if (selectedFiles.length === 0) {
      return;
    }

    uploading = true;
    error = "";
    try {
      uploadResult = await api.upload(selectedFiles, duplicateMode);
      selectedFiles = [];
      await loadSources();
      onContentChanged();
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    } finally {
      uploading = false;
    }
  }

  onMount(() => {
    void loadSources();
  });
</script>

<section class="ingest-page">
  <div class="hero">
    <div>
      <p class="eyebrow">Ingest</p>
      <h1>Drop files into the raw source pool</h1>
      <p class="subtle">
        Batch uploads run through the file-drop pipeline with duplicate handling and OCR metadata.
      </p>
    </div>
    <div class="hero-meta">
      <span>{sources.length} raw sources</span>
      <button class="secondary" type="button" onclick={() => void loadSources()}>Refresh list</button>
    </div>
  </div>

  <div class="layout">
    <div class="panel">
      <label class="field">
        <span>Duplicate handling</span>
        <select bind:value={duplicateMode}>
          <option value="keep_both">Keep both</option>
          <option value="overwrite">Overwrite</option>
          <option value="cancel">Cancel on duplicates</option>
        </select>
      </label>

      <label
        class="dropzone"
        class:dragging={dragging}
        ondragenter={() => (dragging = true)}
        ondragover={(event) => {
          event.preventDefault();
          dragging = true;
        }}
        ondragleave={() => (dragging = false)}
        ondrop={(event) => {
          event.preventDefault();
          dragging = false;
          setFiles(event.dataTransfer?.files ?? null);
        }}
      >
        <input
          type="file"
          multiple
          onchange={(event) => setFiles((event.currentTarget as HTMLInputElement).files)}
        />
        <div class="dropzone-copy">
          <strong>Drag files here or browse</strong>
          <span>PDF, markdown, HTML, text, and OCR-able documents are supported.</span>
        </div>
      </label>

      {#if selectedFiles.length > 0}
        <div class="selection">
          <div class="selection-header">
            <h2>{selectedFiles.length} selected</h2>
            <button type="button" onclick={() => (selectedFiles = [])}>Clear</button>
          </div>
          <ul>
            {#each selectedFiles as file}
              <li>{file.name}</li>
            {/each}
          </ul>
          <button type="button" onclick={() => void uploadFiles()} disabled={uploading}>
            {uploading ? "Uploading…" : "Upload batch"}
          </button>
        </div>
      {/if}

      {#if error}
        <p class="error">{error}</p>
      {/if}
    </div>

    <div class="panel">
      <div class="panel-header">
        <h2>Raw library</h2>
        {#if loadingSources}
          <span class="dim">Loading…</span>
        {/if}
      </div>

      {#if sources.length === 0}
        <p class="dim">No raw sources yet.</p>
      {:else}
        <div class="source-list">
          {#each sources as source}
            <div class="source-row">
              <strong>{source.name}</strong>
              <span>{source.path}</span>
            </div>
          {/each}
        </div>
      {/if}
    </div>
  </div>

  {#if uploadResult}
    <div class="panel">
      <div class="panel-header">
        <h2>Last upload</h2>
        <span class="dim">
          {uploadResult.succeeded}/{uploadResult.total} succeeded · mode {uploadResult.duplicate_mode}
        </span>
      </div>

      <div class="upload-results">
        {#each uploadResult.results as result}
          <div class="upload-row" class:failed={!result.success}>
            <div>
              <strong>{result.source_path}</strong>
              <p>{result.message}</p>
            </div>
            <div class="result-meta">
              {#if result.output_path}
                <span>{result.output_path}</span>
              {/if}
              {#if result.duplicate_of}
                <span>duplicate of {result.duplicate_of}</span>
              {/if}
              {#if result.ocr_confidence !== null}
                <span>OCR confidence {result.ocr_confidence.toFixed(2)}</span>
              {/if}
            </div>
          </div>
        {/each}
      </div>
    </div>
  {/if}
</section>

<style>
  .ingest-page,
  .layout,
  .selection,
  .source-list,
  .upload-results {
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

  .hero-meta {
    display: flex;
    gap: 10px;
    align-items: center;
    color: var(--text-dim);
  }

  .layout {
    display: grid;
    grid-template-columns: 1.1fr 0.9fr;
  }

  .panel {
    padding: 20px;
  }

  .field {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .field span {
    font-size: 0.9rem;
    color: var(--text-dim);
  }

  .dropzone {
    margin-top: 14px;
    border: 2px dashed var(--border-strong);
    border-radius: 18px;
    padding: 30px 18px;
    position: relative;
    background: var(--bg-secondary);
    transition: border-color 0.15s ease, background 0.15s ease;
    cursor: pointer;
  }

  .dropzone.dragging {
    border-color: var(--accent);
    background: var(--accent-soft);
  }

  .dropzone input {
    position: absolute;
    inset: 0;
    opacity: 0;
    cursor: pointer;
  }

  .dropzone-copy {
    display: flex;
    flex-direction: column;
    gap: 6px;
    pointer-events: none;
  }

  .dropzone-copy strong {
    font-size: 1.05rem;
  }

  .dropzone-copy span,
  .dim,
  .source-row span,
  .result-meta,
  .upload-row p {
    color: var(--text-dim);
  }

  .selection-header,
  .panel-header {
    display: flex;
    justify-content: space-between;
    gap: 16px;
    align-items: center;
  }

  .source-row,
  .upload-row {
    display: flex;
    justify-content: space-between;
    gap: 16px;
    padding: 12px 14px;
    border: 1px solid var(--border);
    border-radius: 14px;
    background: var(--bg-secondary);
  }

  .result-meta {
    display: flex;
    flex-direction: column;
    gap: 4px;
    min-width: 220px;
    text-align: right;
    font-size: 0.82rem;
  }

  .upload-row.failed {
    border-color: rgba(191, 64, 64, 0.35);
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

  @media (max-width: 980px) {
    .layout {
      grid-template-columns: 1fr;
    }

    .hero {
      flex-direction: column;
    }

    .upload-row,
    .source-row {
      flex-direction: column;
    }

    .result-meta {
      text-align: left;
      min-width: 0;
    }
  }
</style>
