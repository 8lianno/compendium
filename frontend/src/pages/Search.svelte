<script lang="ts">
  import { api, type SearchResult } from "../lib/api";
  import { highlightText } from "../lib/format";

  interface Props {
    onOpenArticle?: (path: string) => void;
    refreshToken?: number;
  }

  let { onOpenArticle = () => {}, refreshToken = 0 }: Props = $props();

  let query = $state("");
  let results: SearchResult[] = $state([]);
  let searched = $state(false);
  let loading = $state(false);
  let error = $state("");
  let debounceTimer: ReturnType<typeof setTimeout> | null = null;

  function onInput() {
    if (debounceTimer) {
      clearTimeout(debounceTimer);
    }
    if (!query.trim()) {
      results = [];
      searched = false;
      error = "";
      return;
    }
    debounceTimer = setTimeout(() => {
      void doSearch();
    }, 180);
  }

  async function doSearch() {
    if (!query.trim()) {
      return;
    }
    loading = true;
    error = "";
    try {
      const res = await api.search(query, 12);
      results = res.results;
      searched = true;
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
      results = [];
    } finally {
      loading = false;
    }
  }

  $effect(() => {
    refreshToken;
    if (query.trim()) {
      void doSearch();
    }
  });
</script>

<section class="search-page">
  <div class="hero">
    <p class="eyebrow">Custom Search</p>
    <h1>Search the compiled wiki</h1>
    <p class="subtle">
      Results highlight matching terms and open directly into the wiki viewer.
    </p>
  </div>

  <div class="toolbar">
    <input
      type="text"
      bind:value={query}
      placeholder="Search wiki articles, concepts, and notes..."
      oninput={onInput}
    />
    <button type="button" onclick={() => void doSearch()} disabled={!query.trim() || loading}>
      {loading ? "Searching…" : "Search"}
    </button>
  </div>

  {#if error}
    <p class="error">{error}</p>
  {/if}

  {#if loading}
    <p class="dim">Searching…</p>
  {:else if searched && results.length === 0}
    <div class="empty">
      <p class="eyebrow">No matches</p>
      <h2>Nothing matched “{query}”.</h2>
      <p class="dim">Try a broader concept name or a raw-source term.</p>
    </div>
  {:else if results.length > 0}
    <div class="results">
      {#each results as result}
        <button class="result" type="button" onclick={() => onOpenArticle(result.path)}>
          <div class="result-top">
            <span class="category">{result.category || "uncategorized"}</span>
            <span class="score">score {result.score}</span>
          </div>
          <div class="result-title">{@html highlightText(result.title, query)}</div>
          <div class="result-snippet">{@html highlightText(result.snippet, query)}</div>
          <div class="result-path">{result.path}</div>
        </button>
      {/each}
    </div>
  {:else}
    <div class="empty">
      <p class="eyebrow">Ready</p>
      <h2>Start with a concept, source name, or phrase.</h2>
      <p class="dim">The custom search index refreshes after every wiki mutation.</p>
    </div>
  {/if}
</section>

<style>
  .search-page {
    display: flex;
    flex-direction: column;
    gap: 18px;
  }

  .hero,
  .result,
  .empty {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 18px;
    box-shadow: var(--shadow-soft);
  }

  .hero {
    padding: 24px;
  }

  .hero h1 {
    font-size: clamp(1.8rem, 4vw, 3rem);
    margin: 6px 0 8px;
  }

  .subtle,
  .dim {
    color: var(--text-dim);
  }

  .toolbar {
    display: grid;
    grid-template-columns: 1fr auto;
    gap: 10px;
  }

  .results {
    display: grid;
    gap: 12px;
  }

  .result {
    text-align: left;
    padding: 16px 18px;
    background: var(--panel);
    color: var(--text);
  }

  .result:hover {
    transform: translateY(-1px);
    border-color: var(--accent);
  }

  .result-top {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 10px;
  }

  .category {
    text-transform: uppercase;
    letter-spacing: 0.12em;
    font-size: 0.72rem;
    color: var(--accent);
  }

  .score,
  .result-path {
    color: var(--text-dim);
    font-size: 0.82rem;
  }

  .result-title {
    font-size: 1.08rem;
    font-weight: 700;
    margin-bottom: 8px;
  }

  .result-snippet {
    color: var(--text-dim);
    margin-bottom: 10px;
    line-height: 1.6;
  }

  .empty {
    padding: 28px;
  }

  .empty h2 {
    margin: 6px 0 8px;
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

  :global(mark) {
    background: var(--highlight);
    color: var(--accent-strong);
    padding: 0 2px;
    border-radius: 4px;
  }

  @media (max-width: 720px) {
    .toolbar {
      grid-template-columns: 1fr;
    }
  }
</style>
