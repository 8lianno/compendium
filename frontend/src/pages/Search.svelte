<script lang="ts">
  import { api, type SearchResult } from "../lib/api";

  let query = $state("");
  let results: SearchResult[] = $state([]);
  let searched = $state(false);
  let loading = $state(false);

  let debounceTimer: ReturnType<typeof setTimeout>;

  function onInput() {
    clearTimeout(debounceTimer);
    if (!query.trim()) {
      results = [];
      searched = false;
      return;
    }
    debounceTimer = setTimeout(doSearch, 200);
  }

  async function doSearch() {
    if (!query.trim()) return;
    loading = true;
    try {
      const res = await api.search(query, 10);
      results = res.results;
      searched = true;
    } catch {
      results = [];
    } finally {
      loading = false;
    }
  }
</script>

<div class="search-page">
  <h1>Search</h1>
  <input
    type="text"
    bind:value={query}
    placeholder="Search wiki articles..."
    oninput={onInput}
    autofocus
  />

  {#if loading}
    <p class="dim">Searching...</p>
  {:else if searched && results.length === 0}
    <p class="dim">No results for "{query}"</p>
  {:else}
    <div class="results">
      {#each results as r}
        <div class="result">
          <div class="result-title">{r.title}</div>
          <div class="result-meta">{r.category} &middot; score: {r.score}</div>
          {#if r.snippet}
            <div class="result-snippet">{r.snippet}</div>
          {/if}
        </div>
      {/each}
    </div>
  {/if}
</div>

<style>
  .search-page h1 { margin-bottom: 16px; }
  input { margin-bottom: 16px; }
  .results { display: flex; flex-direction: column; gap: 12px; }
  .result {
    padding: 12px 16px;
    background: var(--bg-secondary);
    border-radius: var(--radius);
    border: 1px solid var(--border);
  }
  .result-title { font-weight: 600; color: var(--accent); }
  .result-meta { font-size: 12px; color: var(--text-dim); margin: 4px 0; }
  .result-snippet { font-size: 13px; color: var(--text-dim); }
  .dim { color: var(--text-dim); margin-top: 12px; }
</style>
