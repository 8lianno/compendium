# Compendium — LLM-Native Knowledge Compiler

## Product Requirements Document

| Field | Value |
|---|---|
| **Version** | 2.0 |
| **Date** | 2026-04-04 |
| **Product Manager** | Ali Naserifar |
| **Status** | Draft |
| **Confidentiality** | Personal Project |

---

## 1. Executive summary

> **One-liner:** A local-first desktop app where AI compiles your research sources into a living, queryable knowledge wiki that grows smarter with every interaction.

Knowledge workers today juggle hundreds of sources across papers, articles, repos, and datasets. They read, highlight, and forget. Existing tools like Notion AI and NotebookLM treat sources as static inputs for Q&A, but never synthesize them into persistent, interconnected knowledge structures. The result: every research session starts from scratch.

Compendium changes this. An LLM reads your raw sources and compiles them into an interlinked markdown wiki with concept articles, backlinks, indexes, and summaries. When you ask questions, answers are grounded in your wiki. When you file outputs back, the wiki grows. When the system runs health checks, it self-heals. Your knowledge compounds.

### The core insight

**The compilation step is the entire product.** Nobody else does LLM-as-author synthesis into a navigable, growing knowledge graph. NotebookLM comes closest but is cloud-only, Google-locked, and treats sources as read-only. Compendium's wiki is a living artifact that the LLM writes, maintains, and operates on.

---

## 2. Problem definition

### 2.1 The research fragmentation problem

Researchers, analysts, and content creators face a compounding fragmentation problem:

- **Volume:** A typical PhD researcher reads 200+ papers per year. An analyst covering a sector tracks 50+ sources weekly. A podcaster with diverse interests (like Nakh) may accumulate 500+ reference documents across psychology, philosophy, behavioral economics, and systems thinking.
- **Isolation:** Each source lives in its own silo. Cross-referencing requires manual effort. The insight that connects Paper A's methodology to Dataset B's findings goes undiscovered.
- **Decay:** Knowledge extracted in one session is lost by the next. Notes become stale. Summaries are never updated. There is no persistent, queryable representation of accumulated learning.
- **No synthesis:** Existing AI tools answer questions against sources, but never produce new knowledge artifacts. The output is ephemeral chat messages, not durable research infrastructure.

### 2.2 Why existing solutions fail

| Tool | Sources | Synthesis | Compounding | Ownership |
|---|---|---|---|---|
| **NotebookLM** | Upload-based | Q&A + Audio. No wiki output | None — sessions are stateless | Cloud-only, Google-locked |
| **Notion AI** | In-page content | Shallow — per-page summaries | None — no feedback loop | Cloud SaaS, vendor-owned |
| **Obsidian + AI plugins** | Local vault | Plugin-dependent, fragmented | Manual only | Local files, user-owned |
| **Mem.ai** | Auto-captured | Memory-based recall | Partial — memory grows | Cloud SaaS |
| **RAG pipelines** | Any document | Retrieval only, no generation | None — infrastructure layer | Self-hosted, requires engineering |
| **Compendium** | **Any source (web clip + drop)** | **Full wiki compilation** | **Feedback loop + self-healing lint** | **Local-first, user-owned** |

**Key differentiator:** Compendium is the only system where the LLM is the *author* of a persistent, interlinked knowledge artifact — not just a reader/answerer of source documents.

---

## 3. Target users & personas

### 3.1 Primary: The deep researcher

**Profile:** PhD students, independent researchers, think-tank analysts managing 50–500+ sources on a focused domain. They spend 40%+ of their time on literature synthesis rather than original analysis.

> **JTBD:** "When I accumulate 30+ papers on a topic, I want something to read all of them and build me a navigable knowledge structure, so I can focus on generating insights instead of organizing information."

### 3.2 Secondary: The knowledge podcaster / content creator

**Profile:** Content creators covering diverse topics who need to rapidly synthesize multi-domain research into original content. Research breadth is wide, depth is variable.

> **JTBD:** "When I'm preparing a podcast episode on a new topic, I want to build a focused knowledge base from 10–20 sources that I can interactively query during preparation and even on a run via voice mode."

### 3.3 Tertiary: The competitive intelligence analyst

**Profile:** Analysts at investment firms, consulting shops, or strategy teams who continuously track a market and need a living competitive map.

> **JTBD:** "When I track 15 competitors across 100+ data points, I want a system that maintains an up-to-date competitive wiki and alerts me to contradictions or gaps when new data arrives."

---

## 4. Product vision & positioning

> **Positioning statement:** For researchers and knowledge workers who drown in fragmented sources, Compendium is a local-first knowledge compiler that uses AI to build and maintain a living wiki from your raw materials. Unlike NotebookLM which treats sources as read-only, Compendium's wiki grows with every interaction.

### 4.1 Product principles

- **Local-first, always.** Your research stays on your disk. No telemetry, no cloud dependency for core workflows. API calls are your choice (BYOM).
- **LLM writes, human directs.** You never manually edit the wiki. The LLM is the author; you are the editor-in-chief.
- **Every interaction compounds.** Q&A outputs file back into the wiki. Linting discovers new connections. Positive feedback loops by design.
- **Bring your own model.** No vendor lock-in. Support Claude, GPT, Gemini, and local Ollama.
- **Transparent costs.** Token usage displayed per operation. Users control their inference budget explicitly.

---

## 5. Success metrics

| Objective | Key metric | Baseline | Target | Timeline |
|---|---|---|---|---|
| Validate compilation quality | User rating of wiki accuracy | N/A | ≥4.2 / 5.0 | 3 mo |
| Prove compounding loop | % of Q&A outputs filed back | 0% | ≥50% | 3 mo |
| Demonstrate retention | 30-day user retention | N/A | ≥65% | 6 mo |
| Reduce synthesis time | Time to produce summary vs. manual | ~4 hrs | ≤1.5 hrs | 3 mo |
| Validate BYOM model | % users with non-default LLM | 100% default | ≥40% multi | 3 mo |
| Control cost perception | % rating cost "acceptable" | N/A | ≥75% | 3 mo |

---

## 6. Key features & functionality

### 6.1 Feature map

| Feature | Description | User benefit | Pri. | Success signal |
|---|---|---|---|---|
| Source ingestion | Web clipper + file drop. HTML→MD with local images | One-click capture | P0 | ≥95% fidelity |
| Wiki compilation engine | 6-step LLM pipeline: summarize → extract → generate → link → index → conflicts | Raw → knowledge graph | P0 | ≥1 article/2 sources |
| Incremental compilation | Diff-based updates via dependency graph | Fast, cheap updates | P0 | <30s per source |
| Q&A engine | Chat + CLI. Index-first retrieval within token budget | Multi-hop answers | P0 | ≥80% citation accuracy |
| Feedback filing | One-click output → wiki article with auto-backlinks | Compounding KB | P0 | ≥50% outputs filed |
| Output rendering | MD reports, Marp slides, matplotlib charts | Rich deliverables | P1 | 3+ types used |
| Wiki linting | Health checks: contradictions, broken links, gaps, stale content | Self-healing KB | P1 | ≥80% actionable |
| Graph viewer | Interactive node-edge visualization | Knowledge shape | P1 | 60%+ users |
| Search engine | Full-text + semantic. Web UI + CLI for LLM | Fast retrieval | P1 | p95 <2s |
| BYOM config | Claude/GPT/Gemini/Ollama. Per-operation model selection | No lock-in | P0 | ≥40% multi |
| Obsidian export | Vault-compatible wikilinks and folder structure | Existing tools | P2 | 30%+ export |
| Starter wikis | Domain scaffolds: ML, legal, investment | Fast onboarding | P2 | 25%+ adoption |

### 6.2 The compilation pipeline — core differentiator

- **Step 1 — Summarize:** Structured summary per source (claims, methodology, findings, limitations)
- **Step 2 — Extract concepts:** NER + taxonomy → CONCEPTS.md topic tree
- **Step 3 — Generate articles:** Per-concept synthesis across all sources, each claim traceable
- **Step 4 — Create backlinks:** Bidirectional `[[wikilinks]]`, Obsidian-compatible
- **Step 5 — Build index:** INDEX.md with one-line summaries, organized by category
- **Step 6 — Conflict detection:** Contradictions flagged in CONFLICTS.md for human judgment

> **Why not RAG?** At ≤500 articles, LLM-maintained index files provide sufficient retrieval without vector databases. RAG adds unnecessary complexity at this scale.

---

## 7. Out of scope (v1.0)

- **Team collaboration / shared wikis** — v2
- **Cloud sync / backup** — v2
- **Mobile app** — future
- **Fine-tuning / weight-baking** — premature
- **Voice-mode Q&A** — compelling but deferred
- **Third-party integrations** (Zotero, Mendeley) — file import is sufficient
- **Multi-language compilation** — v1 is English-only
- **Real-time co-editing** — separate product

---

## 8. Architecture decisions

### 8.1 Local-first (non-negotiable)
All data on local disk. Zero inference-cost server calls. User brings own API keys. Near-zero marginal cost per user.

### 8.2 Open core
Engine + wiki format + CLI = open source (MIT). Revenue from sync, model routing, starter wikis, team features.

### 8.3 Desktop app (Tauri / Rust)
File system access critical. Tauri over Electron (~10MB vs ~150MB). Web companion for read-only.

### 8.4 Wiki as flat markdown
Not a database. Directory of .md files with YAML frontmatter, wikilinks, INDEX.md. Human-readable, git-friendly, Obsidian-compatible, portable.

---

## 9. Timeline & milestones

| Phase | Duration | Deliverables | Exit criteria | Key risk |
|---|---|---|---|---|
| 1 | Weeks 1–2 | Discovery, architecture, schema, prompt chain design | Schema approved | Scope creep |
| 2 | Weeks 3–6 | Ingestion + compilation + incremental updates | 30 sources → wiki, <5% errors | Quality at scale |
| 3 | Weeks 7–9 | Q&A engine, output rendering, feedback filing | ≥80% citation accuracy | Token budgets |
| 4 | Weeks 10–12 | Tauri app, graph viewer, search, linting, BYOM | App launches, 100+ node graph | Performance |
| 5 | Weeks 13–14 | Closed beta (50–100 users) | NPS ≥30, zero data-loss | Onboarding |
| 6 | Week 15 | Public beta (PH, HN, OSS repo) | 1,000+ signups | Timing |

---

## 10. Risks & open questions

| Risk | Impact | Prob. | Mitigation |
|---|---|---|---|
| Context windows grow to 10M+ tokens | High | Med | Wiki is cheaper, offline, navigable, persistent |
| NotebookLM ships local + compilation | High | Low | Open ecosystem + BYOM + plugins = switching cost |
| Wiki entropy at 200+ articles | High | High | Linting + conflict detection + quality SLAs |
| API cost uneconomical | Med | Med | Diff-based compilation, token budgets, caching |
| Users expect RAG recall at >2M words | Med | High | Expectations in onboarding, hybrid search bridge |

| Open question | Owner | Deadline |
|---|---|---|
| Flat vs. nested wiki directory schema? | Ali | Week 3 |
| Build or fork web clipper? | Ali | Week 3 |
| RAG threshold wiki size? | Ali | Week 9 |
| Prompt chain: mega-prompt vs. multi-step? | Ali | Week 2 |
| Revenue: freemium vs. paid license? | Ali | Week 12 |

---

## 11. Business model

| Stream | Price | Value | Timing |
|---|---|---|---|
| Open core (free) | — | Full engine, CLI, viewer, single LLM | Launch |
| Pro | $12/mo | Sync, smart routing, priority linting | Month 3 |
| Starter wiki marketplace | $30–99 | Domain scaffolds | Month 5 |
| Team tier | $15/seat/mo | Shared wikis, roles, merge | Month 9 |
| Enterprise | Custom | SSO, audit, on-prem | Month 12+ |

### Defensibility

- **Wiki format spec** becomes the standard
- **Plugin ecosystem** creates network effects
- **Data gravity** — switching cost grows with wiki size (the Obsidian playbook)
- **Compilation quality** — proprietary prompt chains improve with usage

---

## 12. Non-functional requirements

- **Performance:** Compilation <30s per source. Q&A p95 <15s. Graph 200+ nodes at 60fps.
- **Scale:** Up to 2M words / 500 articles without degradation.
- **Privacy:** Zero telemetry on content. API keys in OS keychain.
- **Reliability:** Atomic compilation via staging. Failed compiles never corrupt state.
- **Cost transparency:** Per-operation token usage with USD estimates.
- **Offline:** Viewer + search + graph fully offline. LLM ops need API (unless Ollama).
- **Portability:** Plain .md on disk. Git-friendly. Obsidian-compatible. Zero lock-in.
