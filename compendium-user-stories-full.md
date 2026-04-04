# Compendium — User Stories v3

**Product Manager:** Ali Naserifar  
**Date:** 2026-04-04  
**Status:** Draft  
**Source:** Updated from Andrej Karpathy's "LLM Wiki" pattern document

---

## Epic: SOURCE INGESTION (INGEST)

---

### US-001: Web source ingestion via Obsidian Web Clipper

#### 1) Story information

- **Title:** Web source ingestion via clipper
- **ID:** US-001
- **Priority:** P0
- **Target release:** v1.0 — Phase 2 (Weeks 3–6)
- **Status:** Draft
- **Linked epic:** INGEST

#### 2) User story

*As a* **researcher browsing the web**  
*I want* **to clip a web article into my raw/ collection with one click**  
*So that* **it's captured as clean immutable markdown with local images, ready for LLM compilation**

**JTBD:** "When I find a relevant article, I want to instantly save it to raw/ without manual formatting, so I can keep researching without breaking flow."

#### 3) Business context

- **Problem:** Manual copy-paste loses formatting, images break (URL rot), source attribution is lost
- **Scope (in):** Obsidian Web Clipper integration (or custom extension), HTML→markdown, image download to `raw/assets/`, YAML frontmatter, duplicate detection by URL
- **Out of scope:** PDF ingestion (US-002), video/audio, paywall bypass, social media scraping
- **Success metrics:** Clip-to-raw <5 seconds, ≥95% formatting fidelity, zero broken image links
- **Constraints:** Raw sources are **immutable** — the LLM reads from them but never modifies them. This is the source of truth.

#### 4) Acceptance criteria (BDD)

**Scenario: Successful web clip**  
**Given** the user is viewing an article with the clipper extension installed  
**When** the user clicks the clip button  
**Then** the article is converted to markdown and saved to `raw/[slug].md`  
**And** all images are downloaded to `raw/assets/[slug]/` (or via Obsidian's Ctrl+Shift+D hotkey)  
**And** image paths in markdown updated to local references  
**And** YAML frontmatter added: `title`, `source_url`, `clipped_at`, `author`, `word_count`, `status: raw`  
**And** the file is **immutable** — never modified by the LLM after creation

**Scenario: Article with no extractable content**  
**Given** the page has no article body (login page, JS-only SPA)  
**When** the user clips  
**Then** display: "Could not extract content from this page"  
**And** offer raw HTML fallback with `format: html-raw` in frontmatter

**Scenario: Network failure during image download**  
**Given** some images fail to download  
**When** clip completes  
**Then** markdown saved with working local images  
**And** failed images retain original URLs with `<!-- [REMOTE: download failed] -->` comment  
**And** warning: "3 of 12 images not downloaded locally"

**Scenario: Duplicate source URL**  
**Given** a raw file with the same source URL exists  
**When** user clips the same URL  
**Then** prompt: "Already clipped on [date]. Overwrite, keep both, or cancel?"

**Scenario: Image download via Obsidian hotkey**  
**Given** user clipped an article and images are still remote URLs  
**When** user presses Ctrl+Shift+D in Obsidian  
**Then** all images download to the configured `raw/assets/` directory  
**And** markdown image references auto-update to local paths

#### 5) Functional requirements

- **FR-01:** Compatible with Obsidian Web Clipper extension (preferred) or custom extension
- **FR-02:** HTML → CommonMark with GFM (tables, code blocks, task lists)
- **FR-03:** Images saved as original format, max 20MB each
- **FR-04:** Frontmatter: `title`, `source_url`, `author`, `clipped_at` (ISO 8601), `word_count`, `format`, `status: raw`
- **FR-05:** URL-based dedup + content hash as secondary check
- **FR-06:** File slug from title, max 80 chars, lowercase, hyphens
- **FR-07:** Raw files are immutable post-creation — no LLM writes to raw/

#### 6) UX / UI requirements

- Extension popup: clip button, status indicator, link to open in Obsidian
- Success: green checkmark + title + word count, auto-dismiss 3s
- Error: persistent red message + retry button

#### 7) Edge cases

- Paywalled content: clip visible portion, `partial: true` in frontmatter
- Very long articles (>20K words): clip fully, no truncation
- Non-English: preserve language, set `language: [detected]`
- Tables: markdown tables; complex nested → HTML `<table>` blocks
- Math (LaTeX): preserve in code blocks with `math` tag
- LLM image reading: LLM reads markdown text first, then views referenced images separately (can't do both in one pass)

#### 8) Non-functional requirements

- **Performance:** <5s for articles <5,000 words with <20 images
- **Security:** Extension requires minimal permissions (activeTab only)
- **Audit:** Clips logged in `raw/.clip-log.json`

#### 9) Definition of done

- Extension works in Chrome and Firefox (or Obsidian Web Clipper workflow documented)
- Tested on 10+ diverse page layouts
- Frontmatter consistent across all clipped sources
- Image download hotkey workflow documented

---

### US-002: Local file drop ingestion

#### 1) Story information

- **Title:** Local file drop ingestion
- **ID:** US-002
- **Priority:** P0
- **Target release:** v1.0 — Phase 2
- **Status:** Draft
- **Linked epic:** INGEST

#### 2) User story

*As a* **researcher with local files**  
*I want* **to drag-drop PDFs, markdown, CSVs, and images into raw/**  
*So that* **any local material is captured as immutable source documents for compilation**

#### 3) Business context

- **Scope (in):** PDF→markdown (OCR fallback), .txt/.md passthrough, .csv/.tsv preservation, image cataloging, batch drop (up to 50 files). Original files preserved in `raw/originals/`.
- **Out of scope:** .docx conversion (P2), audio/video transcription
- **Constraint:** All raw files are immutable after ingestion.

#### 4) Acceptance criteria (BDD)

**Scenario: PDF file drop**  
**Given** user drags a PDF into the drop zone  
**When** processed  
**Then** text extracted as `raw/[filename].md` with frontmatter  
**And** images extracted to `raw/assets/[filename]/`  
**And** original PDF preserved in `raw/originals/`  
**And** file is immutable after creation

**Scenario: Scanned PDF (image-only)**  
**Given** PDF has no extractable text  
**When** system detects zero text  
**Then** OCR (Tesseract) applied automatically  
**And** frontmatter tagged `ocr: true`, `ocr_confidence: 0.87`

**Scenario: Batch drop of 30 files**  
**Given** user drops 30 mixed files  
**When** processing begins  
**Then** progress bar: "Processing 14 of 30..."  
**And** errors per file don't block others  
**And** summary: "28 ingested, 2 failed (see log)"

**Scenario: Unsupported file type**  
**Given** user drops .mp4 or .zip  
**Then** display: "Unsupported: .mp4. Supported: PDF, MD, TXT, CSV, TSV, PNG, JPG, SVG"

**Scenario: Duplicate content hash**  
**Given** identical content already in raw/  
**Then** prompt: "Identical content exists: [file]. Skip or keep both?"

#### 5) Functional requirements

- **FR-01:** Drop zone + file picker. Batch ≤50 files with parallel processing (5 concurrent).
- **FR-02:** PDF extraction: `pdf-parse` + Tesseract OCR fallback
- **FR-03:** Content hash (SHA-256) for deduplication
- **FR-04:** Original files always preserved in `raw/originals/`
- **FR-05:** All files immutable after ingestion

#### 7) Edge cases

- Password-protected PDFs: prompt for password or skip
- Corrupted files: skip with "File could not be read"
- >100 page PDFs: chunked extraction with estimated time
- Non-UTF-8: detect encoding, convert to UTF-8

#### 9) Definition of done

- PDF extraction tested on 20+ layouts
- Batch drop stress-tested with 50 files
- Original preservation verified

---

## Epic: WIKI COMPILATION (COMPILE)

---

### US-003: Initial wiki compilation (the core)

#### 1) Story information

- **Title:** Compile raw sources into wiki
- **ID:** US-003
- **Priority:** P0
- **Target release:** v1.0 — Phase 2
- **Status:** Draft
- **Linked epic:** COMPILE

#### 2) User story

*As a* **researcher with 10+ sources in raw/**  
*I want* **the LLM to compile them into a structured, interlinked wiki**  
*So that* **I have a navigable knowledge graph instead of disconnected documents**

**JTBD:** "When I've accumulated raw material on a topic, I want to trigger compilation and get a wiki with entity pages, concept pages, summaries, cross-references, and an evolving synthesis — without writing any of it myself."

#### 3) Business context

- **Problem:** Raw sources are isolated. The LLM re-derives knowledge from scratch on every question. Nothing accumulates.
- **Goal:** Knowledge compiled once and kept current, not re-derived per query.
- **Scope (in):** 6-step pipeline. Output as .md files with YAML frontmatter and `[[wikilinks]]`. Creates `index.md`, `log.md`, entity pages, concept pages, source summaries, synthesis overview.
- **Out of scope:** Multi-language, citation formatting (APA/MLA), diagram generation
- **Success metrics:** ≥1 article per 2 sources, ≥90% claims traceable, zero orphan articles, <2 min for 15 sources

#### 4) Acceptance criteria (BDD)

**Scenario: First compilation with 15 sources (human-in-the-loop)**  
**Given** 15 markdown files in raw/ and user triggers "Compile Wiki"  
**When** the LLM processes each source  
**Then** for each source: LLM reads it, discusses key takeaways with user, writes summary page  
**And** after all sources: generates entity pages, concept pages, comparison pages, synthesis overview  
**And** creates `index.md` (content catalog with links + summaries by category)  
**And** creates `log.md` with timestamped entries for each operation  
**And** creates `CONFLICTS.md` with cross-source contradictions  
**And** all pages have YAML frontmatter: `title`, `type` (entity/concept/summary/comparison/synthesis), `sources[]`, `created_at`, `tags[]`  
**And** all cross-references use `[[wikilinks]]`  
**And** a single source may touch 10–15 wiki pages  
**And** total token usage and cost estimate displayed

**Scenario: Batch compilation (less supervision)**  
**Given** 15 sources in raw/ and user triggers "Compile Wiki --batch"  
**When** the LLM processes all sources without pausing for discussion  
**Then** same output as human-in-the-loop but without per-source discussion  
**And** a compilation summary is generated with key decisions the LLM made

**Scenario: Conflicting information across sources**  
**Given** two sources contain contradictory claims  
**When** compilation processes both  
**Then** the generated page notes: "⚠️ Conflict: [Source A] states X while [Source B] states Y"  
**And** CONFLICTS.md updated with severity, articles, and source references

**Scenario: Compilation failure mid-process**  
**Given** LLM API returns error during compilation  
**When** error occurs  
**Then** all completed pages preserved  
**And** checkpoint saved in `wiki/.checkpoint.json`  
**And** display: "Paused at step 3/6 — 8 of 15 sources processed. Resume?"  
**And** resume continues from checkpoint

**Scenario: log.md entry format**  
**Given** compilation completes for a source  
**When** log.md is updated  
**Then** entry follows parseable format: `## [2026-04-04] ingest | Article Title`  
**And** entry includes: pages created, pages updated, conflicts found, tokens used

#### 5) Functional requirements

- **FR-01:** 6-step pipeline: summarize → extract entities/concepts → generate pages → create `[[wikilinks]]` → build index.md → detect conflicts
- **FR-02:** Schema file (CLAUDE.md / AGENTS.md) defines page templates, naming conventions, cross-referencing rules
- **FR-03:** Page types: entity, concept, source-summary, comparison, synthesis, overview
- **FR-04:** Source provenance: every claim links to `[[raw/source-name]]` with section reference
- **FR-05:** YAML frontmatter on all pages: `title`, `type`, `sources`, `created_at`, `updated_at`, `tags`, `word_count`
- **FR-06:** Frontmatter compatible with Obsidian Dataview plugin
- **FR-07:** Token budget system: user sets max tokens; system optimizes within budget
- **FR-08:** Atomic output: staged in `wiki/.staging/`, promoted on success
- **FR-09:** Git commit after successful compilation (if git initialized)
- **FR-10:** Two modes: human-in-the-loop (discuss per source) and batch (minimal supervision)

#### 6) UX / UI requirements

- Progress panel: 6-step pipeline with current step, estimated time, token counter
- Completion: summary card — articles generated, concepts extracted, conflicts, tokens, cost
- Human-in-the-loop: after each source summary, pause for user feedback before proceeding

#### 7) Edge cases

- All sources on same topic: still produce sub-concept articles
- Very short sources (<500 words): summarize, may not produce standalone page
- LLM can't read markdown + inline images in one pass: read text first, then view images separately

#### 8) Non-functional requirements

- **Performance:** <2 min for 15 sources (~45K words total)
- **Cost:** <$2 USD for 15 sources (Claude Sonnet pricing)
- **Auditability:** Full prompt chain in `wiki/.compilation-log/[timestamp]/`

#### 9) Definition of done

- Tested on 5 diverse source sets
- index.md accurate, zero orphans
- Conflict detection validated on 3 known contradictory pairs
- log.md parseable: `grep "^## \[" log.md | tail -5` works
- YAML frontmatter Dataview-compatible on all pages

---

### US-004: Incremental wiki update

#### 1) Story information

- **Title:** Incremental wiki update on new source
- **ID:** US-004
- **Priority:** P0
- **Target release:** v1.0 — Phase 2
- **Status:** Draft
- **Linked epic:** COMPILE

#### 2) User story

*As a* **researcher who just added a new source**  
*I want* **to say "file this to our wiki" and have it integrated in seconds**  
*So that* **the wiki stays current without full recompilation**

**JTBD:** "After a while, the LLM 'gets' the pattern and the marginal document is a lot easier. I just say 'file this new doc to our wiki: [path]'."

#### 4) Acceptance criteria (BDD)

**Scenario: Add one source to 80-article wiki**  
**Given** wiki has 80 articles from 40 sources  
**When** user adds new source and says "file this to our wiki"  
**Then** LLM:  
1. Reads new source, discusses key takeaways (if human-in-the-loop mode)  
2. Writes source summary page  
3. Updates relevant entity and concept pages (a single source touches 10–15 pages)  
4. Creates new pages if new concepts introduced  
5. Updates index.md  
6. Appends log.md entry: `## [date] ingest | Source Title`  
7. Updates CONFLICTS.md if contradictions found  
**And** untouched pages remain byte-identical  
**And** git commit with descriptive message

**Scenario: Source adds no new information**  
**Given** source covers already-documented topics  
**When** LLM analyzes it  
**Then** source is referenced in relevant pages' source lists  
**And** no new pages generated  
**And** user informed: "Indexed but no new pages — concepts already covered"

**Scenario: New source contradicts existing wiki**  
**Given** new source conflicts with existing page  
**When** detected  
**Then** existing page updated with discrepancy noted inline  
**And** CONFLICTS.md appended

#### 5) Functional requirements

- **FR-01:** Content hashing to detect new/changed sources
- **FR-02:** Dependency graph: `wiki/.deps.json` mapping wiki pages → raw sources
- **FR-03:** Atomic updates via staging
- **FR-04:** Rollback: "Revert Last Update" from `wiki/.backup/` or git
- **FR-05:** CLI: `compendium update [path]` or `compendium update --all-new`
- **FR-06:** Log entry for every incremental update

#### 7) Edge cases

- Multiple new sources at once: batch incremental
- Source deleted from raw/: flag dependent pages as potentially stale
- Source modified: re-summarize and update affected pages
- Wiki manually edited by user: preserve edits, merge with LLM updates

#### 8) Non-functional requirements

- **Performance:** <30s per source for wikis up to 200 articles
- **Cost:** <$0.40 per incremental update
- **Idempotency:** Running update twice with no changes = identical output

---

### US-005: Schema file co-evolution

#### 1) Story information

- **Title:** Schema file creation and co-evolution
- **ID:** US-005
- **Priority:** P0
- **Target release:** v1.0 — Phase 2
- **Status:** Draft
- **Linked epic:** COMPILE

#### 2) User story

*As a* **user setting up a new wiki**  
*I want* **the LLM and I to co-create a schema file that defines wiki structure, conventions, and workflows**  
*So that* **the LLM becomes a disciplined wiki maintainer instead of a generic chatbot**

**JTBD:** "The schema is what makes this work. Without it, the LLM just generates random pages. With it, the LLM knows exactly how to structure my knowledge base for my domain."

#### 3) Business context

- **Problem:** Without a schema, the LLM has no consistent conventions — page types, naming, cross-referencing rules all vary randomly
- **Goal:** A living configuration document that the LLM follows for all operations
- **Scope (in):** Initial schema generation from domain description, co-evolution over time, starter schemas per domain, schema documentation
- **Out of scope:** Schema version control UI (git handles this)

#### 4) Acceptance criteria (BDD)

**Scenario: New wiki setup**  
**Given** user starts a new Compendium project  
**When** user describes their domain: "I'm researching reinforcement learning applied to building control"  
**Then** LLM generates a schema file (`CLAUDE.md` or `AGENTS.md`) defining:
- Directory structure (`raw/`, `wiki/`, page type subdirectories)
- Page types for this domain (e.g., algorithm, environment, paper-summary, experiment, comparison)
- YAML frontmatter template per page type
- Ingest workflow (step-by-step what to do when a new source arrives)
- Cross-referencing rules (when to create wikilinks, what constitutes "related")
- Conflict resolution approach
- Quality standards (min/max page length, required sections per page type)  
**And** user reviews and suggests changes  
**And** LLM updates schema based on feedback

**Scenario: Schema evolution after 20 sources**  
**Given** the wiki has grown to 20 sources and 40 pages  
**When** user notices pages are too long or missing a useful section  
**Then** user and LLM discuss improvements to the schema  
**And** schema is updated  
**And** LLM offers to retroactively update existing pages to match new conventions

**Scenario: Starter schema from template**  
**Given** user selects a domain template (e.g., "Research Deep-Dive", "Book Reading", "Competitive Analysis")  
**When** template is loaded  
**Then** schema is pre-populated with domain-appropriate page types, frontmatter fields, and workflows  
**And** user can customize before first compilation

#### 5) Functional requirements

- **FR-01:** Schema file named `CLAUDE.md` (Claude Code), `AGENTS.md` (Codex), or `COMPENDIUM.md` (generic)
- **FR-02:** Schema sections: Structure, Page Types, Frontmatter Templates, Ingest Workflow, Query Workflow, Lint Workflow, Cross-Referencing Rules, Quality Standards
- **FR-03:** LLM reads schema before every operation and follows its conventions
- **FR-04:** Schema changes are git-committed with descriptive messages
- **FR-05:** Starter schema templates for ≥5 domains at launch

#### 7) Edge cases

- User never customizes schema: defaults must produce good results
- Schema becomes contradictory after multiple edits: LLM should flag inconsistencies
- Multiple LLM agents working on same wiki: schema ensures consistency

#### 9) Definition of done

- Schema generation tested for 5 different domains
- LLM follows schema conventions with ≥95% compliance
- Starter templates for: research, book reading, competitive analysis, personal tracking, course notes

---

## Epic: QUERY & OUTPUT (QA)

---

### US-006: Q&A against wiki

#### 1) Story information

- **Title:** Ask complex questions against knowledge base
- **ID:** US-006
- **Priority:** P0
- **Target release:** v1.0 — Phase 3 (Weeks 7–9)
- **Status:** Draft
- **Linked epic:** QA

#### 2) User story

*As a* **researcher with a compiled wiki**  
*I want* **to ask questions and get answers grounded in my knowledge base with citations**  
*So that* **I can synthesize insights spanning multiple sources without reading everything**

#### 3) Business context

- **Key insight:** The LLM reads `index.md` first to find relevant pages, then drills into them. This works at moderate scale (~100 sources, ~hundreds of pages) without RAG.
- **Success metrics:** ≥4/5 relevance rating, ≥80% citation accuracy, p95 <15s

#### 4) Acceptance criteria (BDD)

**Scenario: Multi-hop question**  
**Given** user asks "What are the main disagreements between Source A and Source B?"  
**When** Q&A engine processes  
**Then** LLM reads `index.md` → identifies relevant pages → reads them → synthesizes answer  
**And** answer includes `[[page]]` citations  
**And** "Sources consulted" section lists all pages read

**Scenario: No relevant content**  
**Given** question is about a topic not in the wiki  
**When** index search finds no matches  
**Then** respond: "Not in your knowledge base. Add sources about this topic?"

**Scenario: Follow-up question**  
**Given** previous Q&A exchange  
**When** user asks follow-up with pronouns ("that", "those")  
**Then** context maintained, pronouns resolved correctly

**Scenario: Broad question exceeding token budget**  
**Given** question touches 50+ pages  
**When** token budget would be exceeded  
**Then** select top 10 by index-score  
**And** inform: "Focused on 10 most relevant pages. Ask more specifically for deeper coverage."

**Scenario: log.md entry**  
**Given** query is answered  
**When** log updated  
**Then** entry: `## [date] query | What are the main disagreements on X?`

#### 5) Functional requirements

- **FR-01:** Index-first retrieval: read index.md → score relevance → load top-N pages
- **FR-02:** Token budget configurable (default: 80% of model context)
- **FR-03:** Citations as `[[wikilinks]]` with expandable source section
- **FR-04:** Dual interface: chat UI + CLI `compendium ask "question"`
- **FR-05:** Search CLI fallback if index-first retrieval insufficient (qmd or custom)
- **FR-06:** Every query logged in log.md

---

### US-007: Multi-format output rendering

#### 1) Story information

- **Title:** Render answers in multiple output formats
- **ID:** US-007
- **Priority:** P1
- **Target release:** v1.0 — Phase 3
- **Status:** Draft
- **Linked epic:** QA

#### 2) User story

*As a* **researcher or content creator**  
*I want* **answers rendered as markdown pages, Marp slide decks, matplotlib charts, or interactive HTML**  
*So that* **I get polished deliverables, not just chat text**

#### 4) Acceptance criteria (BDD)

**Scenario: Markdown report**  
**Given** user asks a question with `--output report` (or "Save as Report")  
**When** answer generated  
**Then** markdown file created in `output/reports/[date]-[slug].md`  
**And** includes: title, date, query, structured answer, citations, source list  
**And** prompted: "File into wiki? [Yes / No]"

**Scenario: Marp slide deck**  
**Given** user requests "Create a 10-slide deck on [topic]"  
**When** generated  
**Then** Marp .md file in `output/slides/[date]-[slug].md`  
**And** each slide: title, 3–5 points, speaker notes  
**And** renders in Obsidian Marp plugin

**Scenario: Interactive HTML**  
**Given** user requests comparative or sortable data  
**When** generated  
**Then** HTML file with JS for sorting/filtering in `output/html/[date]-[slug].html`  
**And** opens in browser or Obsidian

**Scenario: Chart**  
**Given** user requests data visualization  
**When** generated  
**Then** matplotlib PNG in `output/charts/[date]-[slug].png`  
**And** referenced in accompanying markdown

#### 5) Functional requirements

- **FR-01:** Markdown: YAML frontmatter + structured body + citations footer
- **FR-02:** Marp: `marp: true` frontmatter, `---` separators, `<!-- notes -->` blocks
- **FR-03:** HTML: standalone file with inline JS/CSS for interactivity (sorting, filtering)
- **FR-04:** Charts: matplotlib via Python script, output as PNG
- **FR-05:** All outputs prompted for wiki filing (US-008)

---

### US-008: Feedback filing — output back to wiki

#### 1) Story information

- **Title:** File Q&A outputs back into wiki
- **ID:** US-008
- **Priority:** P0
- **Target release:** v1.0 — Phase 3
- **Status:** Draft
- **Linked epic:** QA

#### 2) User story

*As a* **researcher**  
*I want* **to file Q&A outputs back into the wiki as new pages**  
*So that* **my explorations compound in the knowledge base just like ingested sources do**

**JTBD:** "A comparison I asked for, an analysis, a connection I discovered — these are valuable and shouldn't disappear into chat history."

#### 3) Business context

- **Critical insight from source doc:** "Good answers can be filed back into the wiki as new pages. This way your explorations compound in the knowledge base just like ingested sources do."
- **Success metrics:** ≥50% of outputs filed, filed pages referenced in ≥30% of subsequent queries

#### 4) Acceptance criteria (BDD)

**Scenario: File report into wiki**  
**Given** user generated any output (report, slides, chart analysis)  
**When** user clicks "File to Wiki"  
**Then** output becomes a wiki page in appropriate category subdirectory  
**And** tagged `source: user-query`, `type: analysis`, `filed_at`  
**And** `[[wikilinks]]` inserted into related existing pages  
**And** index.md updated  
**And** log.md entry: `## [date] file | Analysis: [title]`  
**And** git commit

**Scenario: Duplicate detection**  
**Given** similar page exists  
**When** user files  
**Then** warn: "Similar page exists: [name]. Merge, replace, or keep both?"

**Scenario: Merge with existing**  
**Given** user chooses "Merge"  
**When** merge executes  
**Then** new content appended under `## Additional analysis ([date])` section  
**And** new sources added to existing page's source list

#### 5) Functional requirements

- **FR-01:** Category auto-detection from CONCEPTS.md taxonomy
- **FR-02:** Bidirectional backlink insertion
- **FR-03:** Atomic staging + commit
- **FR-04:** Filed pages marked `origin: qa-output` (distinct from `origin: compilation`)
- **FR-05:** Index.md and log.md updated atomically

---

## Epic: MAINTENANCE & INTEGRITY (LINT)

---

### US-009: Wiki linting & health checks

#### 1) Story information

- **Title:** Automated wiki health check
- **ID:** US-009
- **Priority:** P1
- **Target release:** v1.0 — Phase 4 (Weeks 10–12)
- **Status:** Draft
- **Linked epic:** LINT

#### 2) User story

*As a* **researcher with a growing wiki**  
*I want* **periodic health checks that find contradictions, stale claims, orphans, and gaps**  
*So that* **the wiki maintains integrity as it scales**

**JTBD:** "The LLM is good at suggesting new questions to investigate and new sources to look for. Lint is generative, not just maintenance."

#### 4) Acceptance criteria (BDD)

**Scenario: Full lint pass**  
**Given** user triggers "Lint Wiki" or scheduled run  
**When** lint completes  
**Then** `wiki/HEALTH_REPORT.md` generated with:
- **Critical:** Broken `[[wikilinks]]` to non-existent pages
- **Warning:** Contradictions between pages (specific passages)
- **Warning:** Stale claims superseded by newer sources
- **Warning:** Orphan pages (no inbound links)
- **Info:** Concepts mentioned but lacking own page
- **Info:** Missing cross-references between related pages
- **Info:** Data gaps fillable via web search
- **Info:** Suggested new questions to investigate
- **Info:** Suggested new sources to look for  
**And** each issue: severity, location, description, suggested fix  
**And** log.md entry: `## [date] lint | Health check pass #N`

**Scenario: Generate missing page**  
**Given** 8 pages reference "reinforcement learning" but no dedicated page exists  
**When** lint detects  
**Then** suggest: "Create page: 'Reinforcement Learning' — referenced in 8 pages"  
**And** user can click "Generate" to trigger compilation

**Scenario: Missing data imputation**  
**Given** page has `[MISSING: publication date]`  
**When** lint runs with web search enabled  
**Then** proposes: "Found: 2024-03-15 (source: doi.org/...). Accept?"

#### 5) Functional requirements

- **FR-01:** Link checker: validate all `[[wikilinks]]` resolve
- **FR-02:** Contradiction detector: LLM compares claims across related pages
- **FR-03:** Staleness tracker: compare raw/ modification dates vs. wiki page compilation dates
- **FR-04:** Orphan finder: pages with zero inbound `[[wikilinks]]`
- **FR-05:** Coverage analyzer: concepts in content without dedicated pages
- **FR-06:** Connection discoverer: suggest pages based on co-occurrence
- **FR-07:** Question generator: suggest investigative questions based on wiki gaps
- **FR-08:** Source recommender: suggest sources to look for based on gaps
- **FR-09:** Scheduled: configurable cadence (daily/weekly/manual)

---

## Epic: INDEXING & NAVIGATION (INDEX)

---

### US-010: index.md — content-oriented catalog

#### 1) Story information

- **Title:** Auto-maintained content index
- **ID:** US-010
- **Priority:** P0
- **Target release:** v1.0 — Phase 2
- **Status:** Draft
- **Linked epic:** INDEX

#### 2) User story

*As the* **Q&A engine and human reader**  
*I want* **index.md to be a complete, accurate catalog of every wiki page**  
*So that* **queries always start with an accurate map and humans can browse the full wiki**

#### 4) Acceptance criteria (BDD)

**Scenario: Index after compilation**  
**Given** compilation completes  
**When** index.md is generated  
**Then** every wiki page listed with: `[[link]]`, one-line summary, page type, source count, last updated  
**And** organized by category (entities, concepts, sources, comparisons, analyses)  
**And** sorted alphabetically within categories

**Scenario: Index after incremental update**  
**Given** one new source ingested  
**When** index.md updated  
**Then** new entries added, modified entries refreshed  
**And** untouched entries unchanged

**Scenario: Index after feedback filing**  
**Given** Q&A output filed as new page  
**When** index updated  
**Then** new entry with `type: analysis` and `origin: qa-output`

**Scenario: Consistency check**  
**Given** user runs `compendium verify-index`  
**When** system checks index vs. actual wiki/  
**Then** reports mismatches and offers to rebuild

#### 5) Functional requirements

- **FR-01:** Format: table with columns: Page, Type, Summary, Sources, Updated
- **FR-02:** Every wiki-modifying operation triggers index refresh
- **FR-03:** Rebuild command: `compendium rebuild-index`
- **FR-04:** Used by Q&A engine as first-read entry point

---

### US-011: log.md — chronological record

#### 1) Story information

- **Title:** Append-only operation log
- **ID:** US-011
- **Priority:** P0
- **Target release:** v1.0 — Phase 2
- **Status:** Draft
- **Linked epic:** INDEX

#### 2) User story

*As a* **user and LLM**  
*I want* **log.md to record every operation chronologically with a parseable format**  
*So that* **I have a timeline of the wiki's evolution and the LLM knows what's been done recently**

#### 4) Acceptance criteria (BDD)

**Scenario: Ingest logged**  
**Given** a source is ingested  
**When** log.md is appended  
**Then** entry: `## [2026-04-04] ingest | Article Title`  
**And** sub-bullets: pages created, pages updated, conflicts found, tokens used

**Scenario: Query logged**  
**Given** a query is answered  
**When** log appended  
**Then** entry: `## [2026-04-04] query | What are the main disagreements on X?`  
**And** sub-bullets: pages consulted, tokens used, output filed (yes/no)

**Scenario: Lint logged**  
**Given** lint pass completes  
**When** log appended  
**Then** entry: `## [2026-04-04] lint | Health check pass #4`  
**And** sub-bullets: issues found (by severity), pages modified

**Scenario: Parseable with unix tools**  
**Given** log has 100+ entries  
**When** user runs `grep "^## \[" log.md | tail -5`  
**Then** last 5 entries displayed correctly with dates and operation types

#### 5) Functional requirements

- **FR-01:** Append-only — never modified, only appended
- **FR-02:** Consistent prefix format: `## [YYYY-MM-DD] operation | Title`
- **FR-03:** Operations: `ingest`, `query`, `file`, `lint`, `schema-update`, `rebuild`
- **FR-04:** Every operation in the system must log to log.md
- **FR-05:** LLM reads log.md to understand recent activity context

---

## Epic: VIEWER & TOOLS (VIEW)

---

### US-012: Graph viewer (Obsidian)

#### 1) Story information

- **Title:** Knowledge graph visualization
- **ID:** US-012
- **Priority:** P1
- **Target release:** v1.0 — Phase 4
- **Status:** Draft
- **Linked epic:** VIEW

#### 2) User story

*As a* **researcher**  
*I want* **to see my wiki as an interactive graph of pages and their connections**  
*So that* **I can see hubs, orphans, and clusters — the shape of my knowledge**

#### 4) Acceptance criteria (BDD)

**Scenario: View in Obsidian**  
**Given** wiki is opened as Obsidian vault  
**When** user opens Graph View  
**Then** pages appear as nodes, `[[wikilinks]]` as edges  
**And** nodes colored by page type (entity, concept, summary, analysis)  
**And** node size proportional to inbound links  
**And** orphan nodes visually distinct (faded)  
**And** clicking a node opens the page

**Scenario: Custom app graph**  
**Given** user opens Compendium desktop app  
**When** Graph View tab opened  
**Then** equivalent graph rendered with D3.js force-directed layout  
**And** filter by category, search by name

#### 5) Functional requirements

- **FR-01:** Primary: Obsidian's native graph view (zero implementation cost)
- **FR-02:** Secondary: custom D3.js graph in Tauri app
- **FR-03:** 200+ nodes at 60fps
- **FR-04:** Export as SVG or PNG

---

### US-013: Search engine (qmd or custom)

#### 1) Story information

- **Title:** Wiki search engine
- **ID:** US-013
- **Priority:** P1
- **Target release:** v1.0 — Phase 4
- **Status:** Draft
- **Linked epic:** VIEW

#### 2) User story

*As a* **researcher or LLM agent**  
*I want* **full-text and semantic search over the wiki**  
*So that* **I can find specific content quickly, especially as the wiki outgrows index-first retrieval**

**Context from source doc:** "At small scale the index file is enough, but as the wiki grows you want proper search. qmd is a good option: local, BM25 + vector, LLM re-ranking, on-device. CLI + MCP server."

#### 4) Acceptance criteria (BDD)

**Scenario: LLM searches via CLI**  
**Given** LLM agent processing a complex query needs more than index  
**When** it shells out to `qmd search "attention mechanisms"`  
**Then** top 5 results with: title, score, snippet  
**And** response in <2s

**Scenario: LLM searches via MCP**  
**Given** LLM agent has qmd configured as MCP server  
**When** it uses the search tool natively  
**Then** same results without shelling out

**Scenario: User searches in UI**  
**Given** user types in search panel  
**When** query entered  
**Then** results as-you-type with highlighted matches  
**And** clicking opens the page

**Scenario: Index is sufficient**  
**Given** wiki has <100 pages  
**When** user/LLM queries  
**Then** index-first retrieval works fine, search engine is optional convenience

#### 5) Functional requirements

- **FR-01:** Recommended: qmd (BM25 + vector, on-device, CLI + MCP server)
- **FR-02:** Alternative: custom naive search (vibe-coded as needed)
- **FR-03:** CLI: `compendium search "query"` or `qmd search "query"`
- **FR-04:** MCP server: LLM uses search as native tool
- **FR-05:** Index auto-updates on wiki changes

---

### US-014: Git integration

#### 1) Story information

- **Title:** Wiki as git repository
- **ID:** US-014
- **Priority:** P1
- **Target release:** v1.0 — Phase 4
- **Status:** Draft
- **Linked epic:** VIEW

#### 2) User story

*As a* **user**  
*I want* **the wiki to be a git repo with automatic commits on every operation**  
*So that* **I get version history, rollback, branching, and diffing for free**

**Context:** "The wiki is just a git repo of markdown files. You get version history, branching, and collaboration for free."

#### 4) Acceptance criteria (BDD)

**Scenario: Auto-commit on compilation**  
**Given** wiki compilation completes  
**When** pages are written  
**Then** git commit with message: `compile: ingested [source-name], updated 12 pages`

**Scenario: Auto-commit on filing**  
**Given** Q&A output filed to wiki  
**When** page created + index updated  
**Then** git commit: `file: added analysis — [title]`

**Scenario: Rollback via git**  
**Given** last compilation introduced errors  
**When** user runs `git revert HEAD` or uses "Revert" in UI  
**Then** wiki returns to previous state cleanly

**Scenario: Diff review**  
**Given** incremental update touched 10 pages  
**When** user runs `git diff HEAD~1`  
**Then** all changes visible: new pages, modified sections, updated index

#### 5) Functional requirements

- **FR-01:** `git init` on wiki creation if not already a repo
- **FR-02:** Auto-commit after every operation (ingest, file, lint-fix, schema update)
- **FR-03:** Commit messages follow convention: `[operation]: [description]`
- **FR-04:** `.gitignore` for: `.staging/`, `.checkpoint.json`, `.compilation-log/`
- **FR-05:** Branch support for experimental compilations

---

## Epic: CONFIGURATION (CONFIG)

---

### US-015: BYOM — Bring your own model

#### 1) Story information

- **Title:** LLM provider configuration
- **ID:** US-015
- **Priority:** P0
- **Target release:** v1.0 — Phase 4
- **Status:** Draft
- **Linked epic:** CONFIG

#### 2) User story

*As a* **user**  
*I want* **to configure which LLM provider and model Compendium uses**  
*So that* **I control my cost, privacy, and quality tradeoff**

#### 4) Acceptance criteria (BDD)

**Scenario: Configure Anthropic**  
**Given** user opens Settings → LLM Provider  
**When** selects Anthropic, enters API key  
**Then** key stored in OS keychain, models listed, test query validates, cost displayed

**Scenario: Local Ollama**  
**Given** Ollama running locally  
**When** configured  
**Then** cost shows "$0.00 / query (local)"  
**And** warning if context <32K

**Scenario: Per-operation model assignment**  
**Given** multiple providers configured  
**When** user opens Model Assignment  
**Then** can set: Compilation → Opus (quality), Q&A → Sonnet (speed), Linting → Ollama (free)

**Scenario: Works with any LLM agent**  
**Given** user prefers Claude Code, Codex, or OpenCode as their agent  
**When** they start the agent in the wiki directory  
**Then** the agent reads the schema file and operates the wiki following its conventions  
**And** no custom app needed — the pattern works with any capable LLM agent

#### 5) Functional requirements

- **FR-01:** Supported: Anthropic, OpenAI, Google Gemini, Ollama, any OpenAI-compatible endpoint
- **FR-02:** API keys in OS keychain
- **FR-03:** Per-operation model selection
- **FR-04:** Token dashboard: cumulative tokens, cost, breakdown by operation
- **FR-05:** Rate limiting with exponential backoff
- **FR-06:** Also works as pure pattern: user can run any LLM agent (Claude Code, Codex, OpenCode/Pi) in the wiki directory with the schema file — no custom app required

---

## Appendix: Story dependency map

```
US-001 (Web clip) ──┐
                     ├──→ US-005 (Schema) ──→ US-003 (Compile) ──→ US-010 (index.md)
US-002 (File drop) ──┘         │                    │                  US-011 (log.md)
                               │                    │                       │
                               │              US-004 (Incremental)          │
                               │                                            │
                               │                              US-006 (Q&A) ←┘
                               │                                   │
                               │                    ┌──────────────┼──────────────┐
                               │                    │              │              │
                               │              US-007 (Output)  US-008 (Filing) → loops back
                               │                                            
                               │              US-009 (Linting) ── depends on US-003 + US-010
                               │              US-012 (Graph)   ── depends on US-003
                               │              US-013 (Search)  ── depends on US-003
                               │              US-014 (Git)     ── independent, wired into all
                               │
                         US-015 (BYOM) ── independent, required by US-003, US-006, US-009
```

### New stories in v3 (vs. v2)

| Story | What's new | Source |
|---|---|---|
| **US-005** | Schema file as first-class architecture layer, co-evolved with LLM | "The schema — a document that tells the LLM how the wiki is structured" |
| **US-011** | log.md as distinct from index.md — append-only, parseable format | "log.md is chronological... parseable with simple unix tools" |
| **US-014** | Git integration — wiki as repo with auto-commits | "The wiki is just a git repo of markdown files" |

### Updated stories in v3

| Story | What changed | Source |
|---|---|---|
| US-001 | Raw sources explicitly immutable. Image download via Obsidian hotkey. | "These are immutable — the LLM reads from them but never modifies them" |
| US-003 | Two ingest modes (human-in-the-loop vs batch). log.md entries. 10–15 page touches per source. Page types (entity, concept, comparison, synthesis). Dataview-compatible frontmatter. | Multiple sections |
| US-004 | "File this to our wiki" natural language trigger. Git commits. | "I just say 'file this new doc to our wiki'" |
| US-007 | Added interactive HTML with JS output format | "dynamic html with js for sorting/filtering" |
| US-008 | Stronger framing: "explorations compound just like ingested sources" | Core doc insight |
| US-009 | Added: suggested questions, suggested sources, generative lint | "The LLM is good at suggesting new questions to investigate" |
| US-013 | qmd as recommended tool with MCP server support | "qmd is a good option" |