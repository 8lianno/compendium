<script lang="ts">
  import { api, type AskResult } from "../lib/api";
  import Markdown from "../components/Markdown.svelte";

  interface Message {
    role: "user" | "assistant";
    content: string;
    sources?: string[];
  }

  let messages: Message[] = $state([]);
  let input = $state("");
  let loading = $state(false);

  async function sendMessage() {
    const question = input.trim();
    if (!question || loading) return;

    messages = [...messages, { role: "user", content: question }];
    input = "";
    loading = true;

    try {
      const result: AskResult = await api.ask(question);
      messages = [
        ...messages,
        {
          role: "assistant",
          content: result.answer,
          sources: result.sources_used,
        },
      ];
    } catch (e) {
      messages = [
        ...messages,
        { role: "assistant", content: `Error: ${e}` },
      ];
    } finally {
      loading = false;
    }
  }

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  }
</script>

<div class="chat">
  <div class="messages">
    {#if messages.length === 0}
      <div class="empty">
        <h2>Ask your knowledge base</h2>
        <p>Questions are answered from your compiled wiki with source citations.</p>
      </div>
    {/if}
    {#each messages as msg}
      <div class="msg" class:user={msg.role === "user"}>
        <div class="role">{msg.role === "user" ? "You" : "Compendium"}</div>
        {#if msg.role === "assistant"}
          <Markdown source={msg.content} />
        {:else}
          <p>{msg.content}</p>
        {/if}
        {#if msg.sources && msg.sources.length > 0}
          <div class="sources">
            Sources: {msg.sources.join(", ")}
          </div>
        {/if}
      </div>
    {/each}
    {#if loading}
      <div class="msg">
        <div class="role">Compendium</div>
        <p class="dim">Researching...</p>
      </div>
    {/if}
  </div>

  <div class="input-row">
    <textarea
      bind:value={input}
      placeholder="Ask a question..."
      rows="2"
      onkeydown={handleKeydown}
    ></textarea>
    <button onclick={sendMessage} disabled={loading || !input.trim()}>
      Send
    </button>
  </div>
</div>

<style>
  .chat { display: flex; flex-direction: column; height: calc(100vh - 48px); }
  .messages { flex: 1; overflow-y: auto; padding-bottom: 16px; }
  .empty { text-align: center; padding: 80px 0; color: var(--text-dim); }
  .empty h2 { color: var(--text); margin-bottom: 8px; }
  .msg {
    margin-bottom: 16px;
    padding: 12px 16px;
    border-radius: var(--radius);
    background: var(--bg-secondary);
  }
  .msg.user { background: var(--bg-hover); }
  .role { font-size: 12px; color: var(--accent); font-weight: 600; margin-bottom: 4px; }
  .sources { font-size: 12px; color: var(--text-dim); margin-top: 8px; }
  .input-row { display: flex; gap: 8px; padding-top: 12px; border-top: 1px solid var(--border); }
  .input-row textarea { flex: 1; resize: none; }
  .dim { color: var(--text-dim); }
</style>
