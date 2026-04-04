<script lang="ts">
  import { api, type ArticleContent, type ItemPath } from "../lib/api";
  import Markdown from "../components/Markdown.svelte";

  interface Props {
    selectedPath?: string | null;
    refreshToken?: number;
    onSelect?: (path: string) => void;
  }

  let {
    selectedPath = null,
    refreshToken = 0,
    onSelect = () => {},
  }: Props = $props();

  let articles: ItemPath[] = $state([]);
  let selected: ArticleContent | null = $state(null);
  let currentPath = $state<string | null>(null);
  let loadingList = $state(true);
  let loadingArticle = $state(false);
  let error = $state("");
  let filter = $state("");
  let loadedToken = -1;

  const filteredArticles = $derived(
    articles.filter((article) =>
      article.name.toLowerCase().includes(filter.trim().toLowerCase()),
    ),
  );

  async function loadArticles() {
    loadingList = true;
    error = "";
    try {
      articles = await api.articles();
      if (!selected && articles.length > 0) {
        await openArticle(selectedPath ?? articles[0].path, false);
      }
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    } finally {
      loadingList = false;
    }
  }

  async function openArticle(path: string, emit = true) {
    if (!path || path === currentPath) {
      return;
    }

    loadingArticle = true;
    error = "";
    try {
      selected = await api.article(path);
      currentPath = path;
      if (emit) {
        onSelect(path);
      }
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    } finally {
      loadingArticle = false;
    }
  }

  $effect(() => {
    if (refreshToken !== loadedToken) {
      loadedToken = refreshToken;
      void loadArticles();
    }
  });

  $effect(() => {
    if (selectedPath && selectedPath !== currentPath) {
      void openArticle(selectedPath, false);
    }
  });
</script>

<div class="viewer">
  <aside class="article-list">
    <div class="list-header">
      <div>
        <p class="eyebrow">Wiki Library</p>
        <h2>{articles.length} articles</h2>
      </div>
      <button class="secondary" type="button" onclick={() => void loadArticles()}>Refresh</button>
    </div>

    <input bind:value={filter} placeholder="Filter articles..." />

    {#if loadingList}
      <p class="dim">Loading articles…</p>
    {:else if filteredArticles.length === 0}
      <p class="dim">No matching articles.</p>
    {:else}
      <div class="article-items">
        {#each filteredArticles as article}
          <button
            class="article-item"
            class:active={currentPath === article.path}
            type="button"
            onclick={() => void openArticle(article.path)}
          >
            <span>{article.name.replace(".md", "")}</span>
            <small>{article.path}</small>
          </button>
        {/each}
      </div>
    {/if}
  </aside>

  <section class="article-content">
    {#if loadingArticle}
      <p class="dim">Loading article…</p>
    {:else if selected}
      <div class="article-shell">
        <div class="article-meta">
          <p class="eyebrow">Active Page</p>
          <h1>{selected.path.split("/").pop()?.replace(".md", "")}</h1>
          <p class="dim">{selected.path}</p>
        </div>
        <Markdown source={selected.content} />
      </div>
    {:else}
      <p class="dim">Select an article to view.</p>
    {/if}

    {#if error}
      <p class="error">{error}</p>
    {/if}
  </section>
</div>

<style>
  .viewer {
    display: grid;
    grid-template-columns: minmax(280px, 340px) 1fr;
    gap: 24px;
    min-height: calc(100vh - 48px);
  }

  .article-list,
  .article-content {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 18px;
    box-shadow: var(--shadow-soft);
  }

  .article-list {
    padding: 18px;
    display: flex;
    flex-direction: column;
    gap: 14px;
    min-height: 0;
  }

  .list-header {
    display: flex;
    justify-content: space-between;
    gap: 16px;
    align-items: flex-start;
  }

  .list-header h2 {
    font-size: 1.05rem;
    margin-top: 4px;
  }

  .article-items {
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 8px;
    padding-right: 4px;
  }

  .article-item {
    width: 100%;
    text-align: left;
    display: flex;
    flex-direction: column;
    gap: 3px;
    padding: 12px 14px;
    border: 1px solid var(--border);
    background: var(--bg-secondary);
    color: var(--text);
  }

  .article-item small {
    color: var(--text-dim);
    font-size: 0.75rem;
  }

  .article-item.active {
    border-color: var(--accent);
    background: var(--accent-soft);
    color: var(--accent-strong);
  }

  .article-content {
    padding: 22px;
    overflow-y: auto;
  }

  .article-shell {
    max-width: 880px;
  }

  .article-meta {
    margin-bottom: 18px;
  }

  .article-meta h1 {
    margin: 4px 0 8px;
    font-size: clamp(1.6rem, 4vw, 2.8rem);
  }

  .eyebrow {
    text-transform: uppercase;
    letter-spacing: 0.14em;
    font-size: 0.72rem;
    color: var(--accent);
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

  .dim {
    color: var(--text-dim);
  }

  .error {
    color: var(--red);
    margin-top: 18px;
  }

  @media (max-width: 960px) {
    .viewer {
      grid-template-columns: 1fr;
    }
  }
</style>
