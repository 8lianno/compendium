# Compendium — LLM Wiki

## Product Requirements Document

| Field | Value |
|---|---|
| **Version** | 3.0 |
| **Date** | 2026-04-04 |
| **Product Manager** | Ali Naserifar |
| **Status** | Draft |
| **Confidentiality** | Personal Project |
| **Source** | Based on Andrej Karpathy's "LLM Wiki" pattern document (2026) |

---

## 1. Executive summary

> **One-liner:** A local-first tool where an LLM incrementally compiles your raw sources into a persistent, interlinked wiki — a compounding knowledge artifact that gets richer with every source you add and every question you ask.

Most people's experience with LLMs and documents looks like RAG: upload files, retrieve chunks at query time, generate an answer. The LLM rediscovers knowledge from scratch on every question. Nothing accumulates. Ask a subtle question that requires synthesizing five documents, and the LLM has to find and piece together the relevant fragments every time. NotebookLM, ChatGPT file uploads, and most RAG systems work this way.

Compendium is different. Instead of retrieving from raw documents at query time, the LLM **incrementally builds and maintains a persistent wiki** — a structured, interlinked collection of markdown files that sits between you and the raw sources. When you add a new source, the LLM doesn't just index it. It reads it, extracts key information, and integrates it into the existing wiki — updating entity pages, revising topic summaries, noting contradictions, strengthening or challenging the evolving synthesis. The knowledge is **compiled once and kept current**, not re-derived on every query.

### The core difference

The wiki is a **persistent, compounding artifact**. The cross-references are already there. The contradictions have already been flagged. The synthesis already reflects everything you've read. A single new source might touch 10–15 wiki pages. Your explorations and queries file back as new pages, so they compound too.

You never (or rarely) write the wiki yourself. The LLM writes and maintains all of it. **You curate sources, direct the analysis, ask good questions, and think about what it all means. The LLM does everything else** — summarizing, cross-referencing, filing, and the bookkeeping that makes a knowledge base actually useful over time.

> The idea is related in spirit to Vannevar Bush's **Memex** (1945) — a personal, curated knowledge store with associative trails between documents. Bush's vision was closer to this than to what the web became: private, actively curated, with the connections between documents as valuable as the documents themselves. The part he couldn't solve was who does the maintenance. The LLM handles that.

---

## 2. Problem definition

### 2.1 Why humans abandon knowledge bases

The tedious part of maintaining a knowledge base is not the reading or the thinking — it's the **bookkeeping**. Updating cross-references, keeping summaries current, noting when new data contradicts old claims, maintaining consistency across dozens of pages. Humans abandon wikis because the maintenance burden grows faster than the value. LLMs don't get bored, don't forget to update a cross-reference, and can touch 15 files in one pass. The wiki stays maintained because the cost of maintenance is near zero.

### 2.2 The fragmentation problem

- **Volume:** A researcher reads 200+ papers/year. A podcaster with diverse interests accumulates 500+ reference documents across psychology, philosophy, behavioral economics, and systems thinking.
- **Isolation:** Each source is siloed. Cross-referencing requires manual effort. The insight connecting Paper A's methodology to Dataset B's findings goes undiscovered.
- **Decay:** Knowledge extracted in one session is lost by the next. No persistent, queryable representation of accumulated learning.
- **No synthesis:** Existing AI tools answer questions against sources but never produce new knowledge artifacts. Output is ephemeral chat, not durable infrastructure.

### 2.3 Why existing solutions fail

| Tool | How it works | What's missing |
|---|---|---|
| **NotebookLM** | Upload sources → Q&A + Audio Overview | Sources are read-only. No wiki output. Sessions are stateless. Nothing compounds. Cloud-only, Google-locked. |
| **ChatGPT file uploads** | Upload files → RAG retrieval at query time | Re-derives knowledge from scratch every question. No persistent structure. No cross-referencing. |
| **Notion AI** | In-page AI summaries | Shallow, per-page only. No cross-source synthesis. No feedback loop. Cloud SaaS. |
| **Obsidian + AI plugins** | Local vault + plugin ecosystem | Plugin-dependent, fragmented. No compilation pipeline. Manual cross-referencing. |
| **Mem.ai** | Auto-captured memory | Memory-based recall, not structured synthesis. Cloud. |
| **RAG pipelines** | Embed → retrieve → generate | Infrastructure, not product. No persistent artifact. No compilation. |
| **Compendium** | **Raw → LLM-compiled wiki → query + file back** | **Full synthesis, compounding feedback loop, self-healing lint, local-first, git-native** |

**Key differentiator:** In every other system, the LLM is a *reader* of documents. In Compendium, the LLM is the *author* of a persistent knowledge artifact.

---

## 3. Use cases

The pattern applies to many contexts. Compendium should support all of these:

| Use case | Sources | Wiki becomes |
|---|---|---|
| **Research deep-dive** | Papers, articles, reports | Comprehensive topic wiki with evolving thesis |
| **Podcast production** | Articles, books, transcripts, notes | Per-episode knowledge bases across diverse domains |
| **Reading a book** | Chapter-by-chapter filing | Character pages, theme pages, plot threads, connections — like a personal Tolkien Gateway |
| **Personal self-tracking** | Journal entries, health data, articles, podcast notes | Structured picture of yourself over time |
| **Business/team intelligence** | Slack threads, meeting transcripts, project docs, customer calls | Living internal wiki maintained by LLM, humans review |
| **Competitive analysis** | Company filings, news, product updates | Living competitive map with contradiction alerts |
| **Course notes** | Lectures, textbooks, assignments | Study wiki with concept pages and prerequisites |
| **Due diligence** | Financial docs, legal filings, interviews | Structured assessment with flagged risks |

---

## 4. Architecture — three layers

This is the foundational architecture. Everything else builds on these three layers:

### Layer 1: Raw sources (immutable)

Your curated collection of source documents. Articles, papers, images, data files, CSVs. **These are immutable — the LLM reads from them but never modifies them.** This is your source of truth.

- Format: .md files (converted from HTML/PDF), images in `raw/assets/`, data files as-is
- Captured via: Obsidian Web Clipper (web articles), file drop (PDFs, local files), manual creation
- Images downloaded locally (Obsidian hotkey: Ctrl+Shift+D) so LLM can reference them directly
- Organized by: flat directory or light categorization — whatever fits the domain

### Layer 2: The wiki (LLM-owned)

A directory of LLM-generated markdown files. Summaries, entity pages, concept pages, comparisons, overview, synthesis. **The LLM owns this layer entirely.** It creates pages, updates them when new sources arrive, maintains cross-references, keeps everything consistent. You read it; the LLM writes it.

Page types in the wiki:
- **Entity pages** — people, organizations, tools, datasets, etc.
- **Concept pages** — ideas, theories, methodologies, frameworks
- **Source summaries** — one page per ingested source with key takeaways
- **Comparison pages** — cross-source analysis on specific dimensions
- **Overview/synthesis** — high-level narrative of what the wiki covers
- **`index.md`** — content-oriented catalog (see Section 6)
- **`log.md`** — chronological record (see Section 6)

All pages use YAML frontmatter (tags, dates, source counts) for Obsidian Dataview queries.

### Layer 3: The schema (co-evolved)

A document (e.g., `CLAUDE.md` for Claude Code, `AGENTS.md` for Codex) that tells the LLM how the wiki is structured, what the conventions are, and what workflows to follow when ingesting sources, answering questions, or maintaining the wiki.

**This is the key configuration file** — it's what makes the LLM a disciplined wiki maintainer rather than a generic chatbot. You and the LLM co-evolve this over time as you figure out what works for your domain.

The schema defines:
- Directory structure and naming conventions
- Page templates and required frontmatter fields
- Ingest workflow (what to update, in what order)
- Cross-referencing rules (when to create links, what constitutes a "related" page)
- Conflict resolution rules (how to handle contradictions)
- Quality standards (minimum page length, required sections)

---

## 5. Operations

Three core operations, documented in the schema:

### 5.1 Ingest

You drop a new source into raw/ and tell the LLM to process it.

**Flow:** LLM reads source → discusses key takeaways with you → writes summary page → updates index → updates relevant entity and concept pages → appends log entry. A single source might touch 10–15 wiki pages.

**Two modes:**
- **Human-in-the-loop (recommended for early wiki):** Ingest one source at a time. Read the summaries, check the updates, guide the LLM on what to emphasize. Stay involved.
- **Batch ingest (for mature wikis):** LLM processes many sources at once with less supervision. The schema is established enough that the LLM knows the conventions.

> "After a while, the LLM 'gets' the pattern and the marginal document is a lot easier. You just say 'file this new doc to our wiki: [path]'."

### 5.2 Query

Ask questions against the wiki. The LLM reads `index.md` first to find relevant pages, then drills into them.

**Output formats:** Markdown page, comparison table, slide deck (Marp), chart (matplotlib), interactive HTML (with JS for sorting/filtering), canvas.

**Critical insight:** Good answers should be **filed back into the wiki** as new pages. A comparison you asked for, an analysis, a connection you discovered — these are valuable and shouldn't disappear into chat history. Your explorations compound in the knowledge base just like ingested sources do.

### 5.3 Lint

Periodically health-check the wiki. Look for:
- Contradictions between pages
- Stale claims that newer sources have superseded
- Orphan pages with no inbound links
- Important concepts mentioned but lacking their own page
- Missing cross-references
- Data gaps that could be filled with a web search

The LLM is good at suggesting new questions to investigate and new sources to look for. Lint is generative, not just maintenance.

---

## 6. Indexing and logging

Two special files that help both the LLM and you navigate the wiki:

### `index.md` — content-oriented

A catalog of everything in the wiki. Each page listed with a link, a one-line summary, and optionally metadata (date, source count). Organized by category (entities, concepts, sources, etc.). The LLM updates it on every ingest.

**At query time:** the LLM reads the index first to find relevant pages, then drills into them. This works surprisingly well at moderate scale (~100 sources, ~hundreds of pages) and avoids the need for embedding-based RAG infrastructure.

### `log.md` — chronological

Append-only record of what happened and when — ingests, queries, lint passes.

**Parseable format:** Each entry starts with a consistent prefix:
```
## [2026-04-02] ingest | Article Title
## [2026-04-02] query | What are the main disagreements on X?
## [2026-04-03] lint | Health check pass #4
```

This makes the log parseable with simple unix tools: `grep "^## \[" log.md | tail -5` gives you the last 5 entries. The log gives the LLM context on what's been done recently.

---

## 7. Feature map

| Feature | Description | Priority | Success signal |
|---|---|---|---|
| **Web clipper ingestion** | Browser extension (Obsidian Web Clipper compatible) → raw/ with local images | P0 | ≥95% format fidelity |
| **File drop ingestion** | PDF/MD/CSV/images → raw/ with auto-conversion | P0 | <10s per file |
| **Compilation pipeline** | 6-step LLM chain: summarize → extract → generate → link → index → conflicts | P0 | ≥1 article per 2 sources |
| **Incremental update** | Diff-based: new source updates only affected pages. Single source → 10–15 page touches. | P0 | <30s per source |
| **Schema file** | CLAUDE.md/AGENTS.md defining wiki structure, conventions, workflows. Co-evolved. | P0 | Schema stabilizes by ~30 sources |
| **index.md** | Content-oriented catalog with links, summaries, metadata. LLM's query entry point. | P0 | Accurate after every operation |
| **log.md** | Append-only chronological log with parseable prefix format. | P0 | Every operation logged |
| **Q&A engine** | Chat + CLI. Index-first retrieval → read pages → synthesized answer with citations. | P0 | ≥80% citation accuracy |
| **Output rendering** | Markdown pages, Marp slides, matplotlib charts, interactive HTML with JS | P1 | 3+ formats used |
| **Feedback filing** | File Q&A outputs back into wiki as new pages. Explorations compound. | P0 | ≥50% of outputs filed |
| **Wiki linting** | Contradictions, stale claims, orphans, missing pages, gaps, suggested questions | P1 | ≥80% issues actionable |
| **Graph viewer** | Obsidian graph view — see wiki shape, hubs, orphans, clusters | P1 | Used by ≥60% of users |
| **Search engine** | CLI + MCP server. Consider qmd (BM25 + vector, on-device). LLM can shell out to it. | P1 | p95 <2s |
| **BYOM config** | Claude/GPT/Gemini/Ollama. Per-operation model selection. Token dashboard. | P0 | ≥40% multi-provider |
| **Dataview compatibility** | YAML frontmatter on all wiki pages for Obsidian Dataview queries | P2 | Frontmatter on 100% of pages |
| **Git integration** | Wiki is a git repo. Version history, branching, diffing for free. | P1 | All changes committed |
| **Obsidian export** | Full vault compatibility (wikilinks, folder structure, graph, Dataview) | P2 | Works as Obsidian vault |

---

## 8. Success metrics

| Objective | Metric | Target | Timeline |
|---|---|---|---|
| Compilation quality | User accuracy rating | ≥4.2 / 5.0 | 3 mo |
| Compounding loop works | % of Q&A outputs filed back | ≥50% | 3 mo |
| Retention via data gravity | 30-day retention | ≥65% | 6 mo |
| Synthesis time reduction | Time vs. manual | ≥60% reduction | 3 mo |
| BYOM adoption | % with multiple providers | ≥40% | 3 mo |
| Scale validation | Wiki size before quality degrades | ≥200 articles | 6 mo |

---

## 9. Architecture decisions

### 9.1 Local-first (non-negotiable)

All data on local disk. Zero server-side inference cost. User brings own API keys. The wiki is just a git repo of markdown files — you get version history, branching, and collaboration for free.

### 9.2 Obsidian as the IDE

Obsidian is not part of the product — it's the **viewing layer**. The LLM is the programmer; the wiki is the codebase; Obsidian is the IDE. Users can also use VS Code, Cursor, or any markdown editor. But Obsidian offers unique advantages: graph view, Marp plugin, Dataview plugin, Web Clipper, wikilink navigation.

### 9.3 Open core

Compilation engine + wiki format + CLI tools = open source (MIT). Revenue from sync, smart model routing, starter wiki templates, team features.

### 9.4 Desktop app (Tauri / Rust)

File system access critical. Tauri over Electron (~10MB vs ~150MB). Or: no custom app at all — just the LLM agent (Claude Code, Codex, OpenCode) + Obsidian. The pattern works without a dedicated UI.

### 9.5 Schema co-evolution

The schema is not static. You and the LLM co-evolve it as you learn what works for your domain. Early wikis need more human guidance; mature wikis have schemas that let the LLM operate with minimal supervision. This means the product's "onboarding" is actually the process of building your first 10–20 page wiki and shaping the schema together.

### 9.6 Wiki as flat markdown

Not a database. Directory of .md files with YAML frontmatter, wikilinks, index.md, log.md. Human-readable, git-friendly, Obsidian-compatible, trivially portable. The wiki is just files — the simplest possible data layer.

### 9.7 No RAG (at moderate scale)

At ≤200–500 articles, index.md + log.md + optional search CLI is sufficient. The LLM reads the index, follows links, reads pages. No embedding model, no vector store, no chunking strategy needed. If the wiki outgrows this, add qmd or similar as a search tool (BM25 + vector, on-device, with MCP server).

---

## 10. Target users & personas

### 10.1 Primary: The deep researcher

> **JTBD:** "When I accumulate 30+ papers on a topic, I want something to read all of them and build me a navigable knowledge structure, so I can focus on generating insights."

### 10.2 Secondary: The knowledge podcaster

> **JTBD:** "When I prep a podcast episode, I want to build a focused mini-wiki from 10–20 sources that I can query during prep and even on a run via voice mode."

### 10.3 Tertiary: The book reader

> **JTBD:** "When I read a complex novel, I want to file each chapter and have the LLM build character pages, theme pages, and plot threads — like my own personal Tolkien Gateway."

### 10.4 Tertiary: The team/business user

> **JTBD:** "When my team generates Slack threads, meeting transcripts, and project docs, I want an LLM to maintain a living internal wiki that stays current without anyone doing the maintenance."

---

## 11. Timeline & milestones

Solo founder (Ali) + 1 contract dev. 15 weeks to public beta.

| Phase | Duration | Deliverables | Exit criteria |
|---|---|---|---|
| 1 | Weeks 1–2 | Discovery: user interviews, schema v0 draft, prompt chain architecture, wiki format spec | Schema works for 5 test sources |
| 2 | Weeks 3–6 | Core: ingestion pipeline + compilation engine (6-step) + incremental updates + index.md + log.md | 30 sources → wiki, <5% errors, index accurate |
| 3 | Weeks 7–9 | Q&A + Output: query engine, output rendering (MD, Marp, charts, HTML), feedback filing loop | ≥80% citation accuracy, filing updates index |
| 4 | Weeks 10–12 | Polish: Tauri shell (or Obsidian-only mode), graph view, search (qmd integration), linting, BYOM, git integration | App launches, lint detects 3+ issue types |
| 5 | Weeks 13–14 | Closed beta: 50–100 power users | NPS ≥30, zero data-loss |
| 6 | Week 15 | Public beta: Product Hunt, HN, OSS repo | 1,000+ signups |

---

## 12. Risks & open questions

### 12.1 Risks

| Risk | Impact | Prob. | Mitigation |
|---|---|---|---|
| Context windows grow to 10M+ tokens | High | Med | Wiki is cheaper, offline, navigable, persistent, git-versioned. Raw context dump has no structure. |
| NotebookLM ships local + wiki compilation | High | Low | Open ecosystem + BYOM + community. First-mover in OSS wiki compiler. |
| Wiki entropy at scale (200+ articles) | High | High | Linting + conflict detection + quality SLAs per compile pass. |
| API cost makes heavy usage uneconomical | Med | Med | Diff-based compilation, token budgets, caching. Knowledge compiled once, not re-derived per query. |
| Users expect RAG recall at >500 articles | Med | High | Clear scale expectations. Add qmd search at threshold. |
| Schema co-evolution is too confusing for new users | Med | Med | Starter schemas per domain. Guided onboarding wizard. |

### 12.2 Open questions

| Question | Owner | Deadline |
|---|---|---|
| Optimal wiki page types per domain? (entity, concept, comparison, synthesis) | Ali | Week 2 |
| Build custom app or ship as pure LLM agent + Obsidian pattern? | Ali | Week 3 |
| Index-first retrieval ceiling: how many pages before search CLI is required? | Ali | Week 9 |
| Prompt chain: single mega-prompt vs. multi-step pipeline per ingest? | Ali | Week 2 |
| Schema templating: how much should be pre-built vs. co-evolved per user? | Ali | Week 6 |
| Revenue: freemium (open core + paid sync/team) vs. pattern-only (educational)? | Ali | Week 12 |
| qmd vs. custom search: build or adopt? | Ali | Week 10 |

---

## 13. Business model

| Stream | Price | Value | Timing |
|---|---|---|---|
| Open core (free) | — | Compilation engine, CLI tools, schema templates, Obsidian integration | Launch |
| Pro | $12/mo | Cross-device sync, smart model routing, priority linting | Month 3 |
| Starter wiki marketplace | $30–99 | Pre-built schemas + starter pages: ML Research, Legal, Investment, Book Club | Month 5 |
| Team tier | $15/seat/mo | Shared wikis, role-based access, Slack/meeting transcript ingestion | Month 9 |
| Enterprise | Custom | SSO, audit, on-prem, custom compilation pipelines | Month 12+ |

### Defensibility

- **Wiki format spec** becomes the standard for LLM-compiled knowledge bases
- **Schema ecosystem** — community-contributed schemas per domain (the "dotfiles" of knowledge work)
- **Data gravity** — switching cost grows with wiki size. 400K words + thousands of backlinks = deep lock-in.
- **Compilation quality** — proprietary prompt chains that handle incremental updates, conflicts, and quality scoring

---

## 14. Non-functional requirements

- **Performance:** Ingest <30s/source. Q&A p95 <15s. Graph renders 200+ nodes at 60fps.
- **Scale:** Up to 2M words / 500 articles without degradation. qmd search beyond that.
- **Privacy:** Zero telemetry. API keys in OS keychain. No data leaves machine except LLM API calls.
- **Reliability:** Compilation atomic via staging. Failed compiles never corrupt wiki. Git provides rollback.
- **Cost transparency:** Token usage per operation with USD estimates. Dashboard.
- **Offline:** Viewer, search, graph fully offline. LLM operations need API (unless Ollama).
- **Portability:** Plain .md on disk. Git repo. Obsidian-compatible. Zero lock-in.

---

## 15. Tooling & tips

- **Obsidian Web Clipper:** Browser extension converting web articles to markdown. Primary ingestion path.
- **Local image download:** Obsidian Settings → Files/links → fixed attachment folder. Hotkey (Ctrl+Shift+D) downloads all images locally so LLM can reference them.
- **Obsidian graph view:** Best way to see wiki shape — hubs, orphans, clusters.
- **Marp:** Markdown slide deck format. Obsidian plugin available. Generate presentations from wiki content.
- **Dataview:** Obsidian plugin for queries over page frontmatter. Dynamic tables and lists from YAML metadata.
- **qmd:** Local search engine for markdown files. BM25 + vector search, LLM re-ranking, on-device. CLI + MCP server.
- **Git:** The wiki is just a repo. Version history, branching, diffing for free. Every compilation is a commit.