<script lang="ts">
  import { api, type Article, type ArticleContent } from "../lib/api";
  import Markdown from "../components/Markdown.svelte";

  let articles: Article[] = $state([]);
  let selected: ArticleContent | null = $state(null);
  let loading = $state(true);
  let error = $state("");

  async function loadArticles() {
    try {
      articles = await api.articles();
      loading = false;
    } catch (e) {
      error = String(e);
      loading = false;
    }
  }

  async function openArticle(path: string) {
    try {
      selected = await api.article(path);
    } catch (e) {
      error = String(e);
    }
  }

  loadArticles();
</script>

<div class="viewer">
  <div class="article-list">
    <h2>Wiki Articles</h2>
    {#if loading}
      <p class="dim">Loading...</p>
    {:else if articles.length === 0}
      <p class="dim">No articles yet. Run <code>compendium compile</code> first.</p>
    {:else}
      {#each articles as article}
        <button class="article-item" onclick={() => openArticle(article.path)}>
          {article.name.replace(".md", "")}
        </button>
      {/each}
    {/if}
  </div>

  <div class="article-content">
    {#if selected}
      <Markdown source={selected.content} />
    {:else}
      <p class="dim">Select an article to view</p>
    {/if}
    {#if error}
      <p class="error">{error}</p>
    {/if}
  </div>
</div>

<style>
  .viewer { display: flex; gap: 24px; height: calc(100vh - 48px); }
  .article-list {
    width: 250px;
    flex-shrink: 0;
    overflow-y: auto;
    border-right: 1px solid var(--border);
    padding-right: 16px;
  }
  .article-list h2 { font-size: 14px; color: var(--text-dim); margin-bottom: 12px; }
  .article-item {
    display: block;
    width: 100%;
    background: none;
    color: var(--text);
    text-align: left;
    padding: 6px 10px;
    border-radius: var(--radius);
    font-size: 13px;
    margin-bottom: 2px;
  }
  .article-item:hover { background: var(--bg-hover); }
  .article-content { flex: 1; overflow-y: auto; }
  .dim { color: var(--text-dim); }
  .error { color: var(--red); }
</style>
