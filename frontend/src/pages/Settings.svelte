<script lang="ts">
  import { onMount } from "svelte";
  import {
    api,
    type ModelDraft,
    type ProviderTestResult,
    type SettingsPayload,
  } from "../lib/api";
  import { formatContextWindow, formatPricing } from "../lib/format";

  interface Props {
    onContentChanged?: () => void;
  }

  interface SettingsDraft {
    default_provider: string;
    compilation: ModelDraft;
    qa: ModelDraft;
    lint_model: ModelDraft;
    templates: {
      default: string;
      domain: string;
    };
    lint_settings: {
      schedule: "manual" | "daily" | "weekly";
      missing_data_web_search: boolean;
    };
  }

  let { onContentChanged = () => {} }: Props = $props();

  const templateOptions = [
    "research",
    "book-reading",
    "competitive-analysis",
    "personal-tracking",
    "course-notes",
  ];

  let settings = $state<SettingsPayload | null>(null);
  let draft = $state<SettingsDraft>({
    default_provider: "anthropic",
    compilation: { provider: "anthropic", model: "" },
    qa: { provider: "anthropic", model: "" },
    lint_model: { provider: "anthropic", model: "" },
    templates: { default: "research", domain: "" },
    lint_settings: { schedule: "manual", missing_data_web_search: false },
  });
  let keyInputs = $state<Record<string, string>>({
    anthropic: "",
    openai: "",
    gemini: "",
    ollama: "",
  });
  let testResults = $state<Record<string, ProviderTestResult | null>>({
    compilation: null,
    qa: null,
    lint: null,
  });
  let loading = $state(true);
  let saving = $state(false);
  let message = $state("");
  let error = $state("");

  function applyDraft(payload: SettingsPayload) {
    settings = payload;
    draft = {
      default_provider: payload.operations.default_provider,
      compilation: { ...payload.models.compilation },
      qa: { ...payload.models.qa },
      lint_model: { ...payload.models.lint },
      templates: { ...payload.templates },
      lint_settings: { ...payload.lint },
    };
    message = payload.changed?.length ? `Saved: ${payload.changed.join(", ")}` : "";
  }

  async function loadSettings() {
    loading = true;
    error = "";
    try {
      const payload = await api.settings();
      applyDraft(payload);
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    } finally {
      loading = false;
    }
  }

  async function saveSettings() {
    saving = true;
    error = "";
    message = "";
    try {
      const payload = await api.saveSettings(draft);
      applyDraft(payload);
      onContentChanged();
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    } finally {
      saving = false;
    }
  }

  async function testAssignment(kind: "compilation" | "qa" | "lint") {
    error = "";
    try {
      const payload =
        kind === "lint" ? draft.lint_model : kind === "qa" ? draft.qa : draft.compilation;
      testResults = {
        ...testResults,
        [kind]: await api.testProvider(payload),
      };
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    }
  }

  async function saveKey(provider: string) {
    error = "";
    message = "";
    try {
      await api.saveProviderKey(provider, keyInputs[provider] ?? "");
      message = `Saved ${provider} key`;
      await loadSettings();
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    }
  }

  async function deleteKey(provider: string) {
    error = "";
    message = "";
    try {
      await api.deleteProviderKey(provider);
      keyInputs = { ...keyInputs, [provider]: "" };
      message = `Removed ${provider} key`;
      await loadSettings();
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    }
  }

  function operationDetails(kind: "compilation" | "qa" | "lint") {
    return testResults[kind] ?? settings?.operations[kind] ?? null;
  }

  onMount(() => {
    void loadSettings();
  });
</script>

<section class="settings-page">
  <div class="hero">
    <div>
      <p class="eyebrow">Settings</p>
      <h1>Configure providers, templates, and scheduled linting</h1>
      <p class="subtle">
        Save provider credentials locally, assign models per operation, and choose the starter
        schema template that drives compilation.
      </p>
    </div>
    <button class="secondary" type="button" onclick={() => void loadSettings()}>
      Refresh settings
    </button>
  </div>

  {#if loading}
    <p class="dim">Loading settings…</p>
  {:else}
    <div class="panel">
      <div class="panel-header">
        <h2>Operation assignments</h2>
        <button type="button" onclick={() => void saveSettings()} disabled={saving}>
          {saving ? "Saving…" : "Save settings"}
        </button>
      </div>

      <label class="field">
        <span>Default provider</span>
        <select bind:value={draft.default_provider}>
          <option value="anthropic">Anthropic</option>
          <option value="openai">OpenAI</option>
          <option value="gemini">Gemini</option>
          <option value="ollama">Ollama</option>
        </select>
      </label>

      <div class="operation-grid">
        {#each [
          { key: "compilation", label: "Compilation", draft: draft.compilation },
          { key: "qa", label: "Q&A", draft: draft.qa },
          { key: "lint", label: "Lint", draft: draft.lint_model },
        ] as operation}
          <div class="operation-card">
            <div class="panel-header">
              <div>
                <p class="eyebrow">{operation.label}</p>
                <h3>{operation.draft.provider}</h3>
              </div>
              <button
                class="secondary"
                type="button"
                onclick={() => void testAssignment(operation.key as "compilation" | "qa" | "lint")}
              >
                Test
              </button>
            </div>

            <label class="field">
              <span>Provider</span>
              <select bind:value={operation.draft.provider}>
                <option value="anthropic">Anthropic</option>
                <option value="openai">OpenAI</option>
                <option value="gemini">Gemini</option>
                <option value="ollama">Ollama</option>
              </select>
            </label>

            <label class="field">
              <span>Model</span>
              <input bind:value={operation.draft.model} placeholder="model name" />
            </label>

            <label class="field">
              <span>Endpoint (optional)</span>
              <input bind:value={operation.draft.endpoint} placeholder="http://localhost:11434" />
            </label>

            {#if operationDetails(operation.key as "compilation" | "qa" | "lint") as details}
              <div class="details">
                <span>
                  Context window: {formatContextWindow(details.context_window)}
                </span>
                <span>{formatPricing(details.pricing ?? null)}</span>
                {#if "saved" in details && typeof details.saved === "boolean"}
                  <span>Credential saved: {details.saved ? "yes" : "no"}</span>
                {/if}
                {#if details.error}
                  <span class="error">{details.error}</span>
                {/if}
                {#if "ok" in details && typeof details.ok === "boolean"}
                  <span>Connection test: {details.ok ? "passed" : "failed"}</span>
                {/if}
              </div>
            {/if}
          </div>
        {/each}
      </div>

      <div class="form-grid">
        <label class="field">
          <span>Starter schema template</span>
          <select bind:value={draft.templates.default}>
            {#each templateOptions as template}
              <option value={template}>{template}</option>
            {/each}
          </select>
        </label>

        <label class="field">
          <span>Domain description</span>
          <input bind:value={draft.templates.domain} placeholder="Optional domain context" />
        </label>
      </div>

      <div class="form-grid">
        <label class="field">
          <span>Lint schedule</span>
          <select bind:value={draft.lint_settings.schedule}>
            <option value="manual">Manual</option>
            <option value="daily">Daily</option>
            <option value="weekly">Weekly</option>
          </select>
        </label>

        <label class="checkbox checkbox-card">
          <input type="checkbox" bind:checked={draft.lint_settings.missing_data_web_search} />
          <span>Attach missing-data research leads to lint suggestions</span>
        </label>
      </div>
    </div>

    <div class="panel">
      <div class="panel-header">
        <h2>Provider credentials</h2>
      </div>
      <div class="credential-grid">
        {#each ["anthropic", "openai", "gemini"] as provider}
          <div class="credential-card">
            <div class="panel-header">
              <div>
                <p class="eyebrow">{provider}</p>
                <h3>{settings?.providers[provider]?.saved ? "Saved" : "Not saved"}</h3>
              </div>
              <button class="secondary" type="button" onclick={() => void deleteKey(provider)}>
                Clear
              </button>
            </div>
            <label class="field">
              <span>API key</span>
              <input
                type="password"
                value={keyInputs[provider]}
                placeholder="Paste key to save locally"
                oninput={(event) =>
                  (keyInputs = {
                    ...keyInputs,
                    [provider]: (event.currentTarget as HTMLInputElement).value,
                  })}
              />
            </label>
            <button type="button" onclick={() => void saveKey(provider)} disabled={!keyInputs[provider]}>
              Save key
            </button>
          </div>
        {/each}

        <div class="credential-card">
          <p class="eyebrow">ollama</p>
          <h3>Local endpoint</h3>
          <p class="dim">
            Ollama uses the configured endpoint on the model assignment and does not store an API
            key.
          </p>
        </div>
      </div>
    </div>
  {/if}

  {#if message}
    <p class="success">{message}</p>
  {/if}

  {#if error}
    <p class="error">{error}</p>
  {/if}
</section>

<style>
  .settings-page,
  .operation-grid,
  .credential-grid {
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  .hero,
  .panel,
  .operation-card,
  .credential-card {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 18px;
    box-shadow: var(--shadow-soft);
  }

  .hero,
  .panel {
    padding: 24px;
  }

  .hero {
    display: flex;
    justify-content: space-between;
    gap: 18px;
    align-items: flex-start;
  }

  .hero h1 {
    margin: 6px 0 8px;
    font-size: clamp(1.8rem, 4vw, 2.8rem);
  }

  .panel-header {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    align-items: flex-start;
  }

  .operation-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .operation-card,
  .credential-card {
    padding: 18px;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .credential-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .form-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 12px;
    margin-top: 14px;
  }

  .field {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .field span,
  .subtle,
  .dim,
  .details {
    color: var(--text-dim);
  }

  .details {
    display: flex;
    flex-direction: column;
    gap: 5px;
    font-size: 0.88rem;
  }

  .checkbox {
    display: inline-flex;
    align-items: center;
    gap: 8px;
  }

  .checkbox-card {
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 14px;
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

  .success {
    color: var(--green);
  }

  .error {
    color: var(--red);
  }

  @media (max-width: 1080px) {
    .operation-grid,
    .credential-grid,
    .form-grid {
      grid-template-columns: 1fr;
    }

    .hero {
      flex-direction: column;
    }
  }
</style>
