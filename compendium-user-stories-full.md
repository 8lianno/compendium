# Compendium — User Stories

**Product Manager:** Ali Naserifar  
**Date:** 2026-04-04  
**Status:** Draft — Ready for Discovery

---

## Epic: SOURCE INGESTION (INGEST)

---

### US-001: Web source ingestion via clipper

#### 1) Story information

- **Title:** Web source ingestion via clipper
- **ID:** US-001
- **Author:** Product Manager — Ali Naserifar
- **Created date:** 2026-04-04
- **Priority:** P0
- **Target release:** v1.0 — Phase 2 (Weeks 3–6)
- **Status:** Draft
- **Linked epic:** INGEST

#### 2) User story

*As a* **researcher browsing the web**  
*I want* **to clip a web article into my knowledge base with one click**  
*So that* **it's captured as clean markdown with local images, ready for LLM compilation**

**JTBD:** "When I find a relevant article while browsing, I want to instantly save it to my raw/ directory without manual formatting, so I can keep researching without breaking flow."

#### 3) Business context

- **Problem:** Manual copy-paste loses formatting, images break (external URLs rot), source attribution is lost. Researchers lose 15–30 min per source on manual preprocessing.
- **Goal:** One-click web-to-markdown ingestion with zero broken references.
- **Scope (in):**
  - Browser extension (Chrome + Firefox)
  - HTML → clean markdown conversion (Mozilla Readability or equivalent)
  - All images downloaded to local `raw/images/[source-slug]/`
  - YAML frontmatter with: title, source URL, author, clip date, word count
  - Duplicate detection by URL
- **Out of scope:**
  - PDF ingestion (US-002)
  - Video/audio transcription
  - Social media scraping
  - Paywall bypass
- **Success metrics:**
  - Clip-to-raw completion in <5 seconds
  - ≥95% formatting fidelity (tables, code blocks, headings preserved)
  - Zero broken image links in output
  - <2% duplicate clips per user per month
- **Assumptions / constraints:**
  - User has Chrome or Firefox
  - Target pages have extractable article content (not SPAs with JS-only rendering)
  - Extension communicates with desktop app via local WebSocket

#### 4) Acceptance criteria (BDD)

**Scenario: Successful web clip**  
**Given** the user is viewing an article in their browser with the Compendium extension installed  
**When** the user clicks the Compendium clip button  
**Then** the article is converted to clean markdown and saved to `raw/[source-slug].md`  
**And** all referenced images are downloaded to `raw/images/[source-slug]/`  
**And** image paths in markdown are updated to local relative references  
**And** YAML frontmatter is added: title, source URL, clip date, author (if detectable), word count  
**And** a success notification appears in the extension: "Clipped: [title] (2,340 words)"

**Scenario: Article with no extractable content**  
**Given** the user is on a page with no article body (login page, SPA with JS-only rendering)  
**When** the user clicks the clip button  
**Then** the system displays "Could not extract article content from this page"  
**And** offers the option to save raw HTML as fallback with tag `format: html-raw` in frontmatter

**Scenario: Network failure during image download**  
**Given** the article is clipped but some images fail to download (CDN timeout, 403)  
**When** the clip completes  
**Then** the markdown file is saved with successfully downloaded images using local paths  
**And** failed images retain their original URLs with a `<!-- [REMOTE: download failed] -->` comment  
**And** a warning is shown: "3 of 12 images could not be downloaded locally"

**Scenario: Duplicate source URL**  
**Given** a raw file already exists with the same source URL in frontmatter  
**When** the user clips the same URL again  
**Then** the system prompts: "This article was already clipped on [date]. Overwrite, keep both, or cancel?"  
**And** if "keep both," the new file is suffixed with `-v2`

**Scenario: Desktop app not running**  
**Given** the extension is installed but the Compendium desktop app is not running  
**When** the user clicks the clip button  
**Then** the extension displays: "Compendium desktop app is not running. Please start it and try again."

#### 5) Functional requirements

- **FR-01 [Input]:** Extension sends page URL + full HTML to desktop app via local WebSocket (port 17394)
- **FR-02 [Extraction]:** Uses Readability algorithm for article body extraction. Falls back to full `<body>` if Readability confidence is below threshold.
- **FR-03 [Conversion]:** HTML → CommonMark with GFM extensions (tables, task lists, strikethrough). Code blocks preserve language hints.
- **FR-04 [Images]:** Downloaded as original format (PNG/JPG/WebP/SVG/GIF). Filenames slugified. Max 20MB per image, skip larger with warning.
- **FR-05 [Frontmatter]:** YAML block with: `title`, `source_url`, `author`, `clipped_at` (ISO 8601), `word_count`, `format: markdown`, `status: raw`
- **FR-06 [Dedup]:** Check `source_url` against all existing raw/ frontmatter. Content hash as secondary dedup for different URLs with identical content.
- **FR-07 [File naming]:** Slug generated from title, max 80 chars, lowercase, hyphens only.

#### 6) UX / UI requirements

- **Extension popup:** Minimal — clip button, status indicator (idle / clipping / success / error), link to open in desktop app
- **Success state:** Green checkmark + title + word count, auto-dismisses after 3 seconds
- **Error state:** Red icon + error message + retry button. Persistent until dismissed.
- **Desktop notification:** Optional system notification on successful clip (configurable in settings)
- **Accessibility:** Extension popup keyboard-accessible, ARIA labels on all interactive elements

#### 7) Edge cases

- Paywalled content: clip whatever is visible; add `partial: true` in frontmatter
- Very long articles (>20K words): clip fully, no truncation
- Non-English content: preserve original language, set `language: [detected]` in frontmatter
- Tables: convert to markdown tables; complex nested tables fall back to HTML `<table>` blocks
- Math notation (LaTeX in HTML): preserve as-is in markdown code blocks with `math` tag
- Redirecting URLs: follow redirects, store final URL in frontmatter, original in `original_url`
- SVG images: download and reference locally; inline SVGs embedded directly in markdown

#### 8) Non-functional requirements

- **Performance:** Clip-to-saved <5 seconds for articles <5,000 words with <20 images
- **Capacity:** Handle articles up to 50K words without timeout
- **Security:** Extension requests minimal permissions (activeTab only). No external analytics.
- **Audit:** Each clip logged in `raw/.clip-log.json` with timestamp, URL, outcome, file path

#### 9) Definition of done

- All acceptance criteria met and demonstrated
- Extension published in Chrome Web Store and Firefox Add-ons (or sideloadable for beta)
- Unit tests cover Readability extraction for 10+ diverse page layouts
- Integration test: clip → file exists in raw/ → frontmatter valid → images present
- Documentation updated in README

---

### US-002: Local file drop ingestion

#### 1) Story information

- **Title:** Local file drop ingestion
- **ID:** US-002
- **Author:** Product Manager — Ali Naserifar
- **Created date:** 2026-04-04
- **Priority:** P0
- **Target release:** v1.0 — Phase 2
- **Status:** Draft
- **Linked epic:** INGEST

#### 2) User story

*As a* **researcher with local files**  
*I want* **to drag and drop PDFs, markdown files, CSVs, and images into my knowledge base**  
*So that* **any local research material is captured in raw/ for compilation**

**JTBD:** "When I download a paper or dataset, I want to drop it into Compendium and have it auto-converted to the right format, so I don't need to manually preprocess anything."

#### 3) Business context

- **Problem:** Researchers accumulate files in scattered directories; manual conversion is friction that prevents systematic knowledge capture
- **Scope (in):** PDF→markdown (with OCR fallback), .txt/.md passthrough, .csv/.tsv preservation, image cataloging, batch drop (up to 50 files)
- **Out of scope:** .docx conversion (P2), audio/video transcription, cloud storage integration
- **Success metrics:**
  - File ingestion in <10s for files <50MB
  - ≥90% text extraction accuracy from PDFs
  - Zero data loss on batch drops of ≤50 files

#### 4) Acceptance criteria (BDD)

**Scenario: PDF file drop**  
**Given** the user drags a PDF file into the Compendium drop zone  
**When** the file is processed  
**Then** text is extracted and saved as `raw/[filename].md` with YAML frontmatter  
**And** embedded images are extracted to `raw/images/[filename]/`  
**And** original PDF is preserved in `raw/originals/[filename].pdf`  
**And** frontmatter includes: title (from PDF metadata or first heading), source: `local`, format: `pdf-extracted`, page_count, word_count

**Scenario: Scanned PDF (image-only pages)**  
**Given** the user drops a PDF with no extractable text (scanned document)  
**When** the system detects zero text in extraction  
**Then** OCR (Tesseract) is applied automatically  
**And** the output markdown is tagged `ocr: true` in frontmatter  
**And** a confidence score is included: `ocr_confidence: 0.87`

**Scenario: Markdown file drop**  
**Given** the user drags an existing .md file  
**When** the file is processed  
**Then** it is copied to raw/ with frontmatter prepended (source: `local`, date, filename)  
**And** any relative image paths are resolved and images copied to `raw/images/`

**Scenario: Batch drop of 30 files**  
**Given** the user drops 30 mixed files (PDFs + MDs + CSVs)  
**When** processing begins  
**Then** a progress bar shows: "Processing 14 of 30..."  
**And** errors on individual files do not block the rest  
**And** a summary appears: "28 files ingested, 2 failed (see error log)"

**Scenario: Unsupported file type**  
**Given** the user drops a .mp4 or .zip file  
**When** the system detects unsupported format  
**Then** it displays "Unsupported file type: .mp4. Supported: PDF, MD, TXT, CSV, TSV, PNG, JPG, SVG"

**Scenario: Duplicate content hash**  
**Given** a file with identical content hash already exists in raw/  
**When** the user drops the duplicate  
**Then** the system prompts: "This file has identical content to [existing-file]. Skip or keep both?"

#### 5) Functional requirements

- **FR-01:** Drop zone in desktop app accepts drag-and-drop and file picker dialog
- **FR-02:** PDF extraction uses `pdf-parse` + Tesseract OCR fallback for image-only pages
- **FR-03:** CSV/TSV files copied as-is with frontmatter prepended describing columns and row count
- **FR-04:** Image files (PNG/JPG/SVG) cataloged in `raw/images/standalone/` with metadata frontmatter
- **FR-05:** Batch processing: parallel up to 5 files, sequential beyond. Error isolation per file.
- **FR-06:** Content hash (SHA-256) computed for deduplication
- **FR-07:** Original files preserved in `raw/originals/` (never modified)

#### 6) UX / UI requirements

- **Drop zone:** Full-width area in ingestion tab, dashed border, "Drop files here or click to browse" label
- **Progress:** Individual file progress + overall batch progress bar
- **Error detail:** Expandable error log per failed file with specific reason
- **States:** idle → processing (spinner + progress) → complete (green summary) → error (red per-file)

#### 7) Edge cases

- Password-protected PDFs: prompt for password or skip with error
- Corrupted files: detect and skip with "File could not be read" error
- Very large PDFs (>100 pages): process with chunked extraction, show estimated time
- Files with identical names but different content: auto-suffix with `-2`, `-3`
- Non-UTF-8 text files: detect encoding, convert to UTF-8

#### 8) Non-functional requirements

- **Performance:** <10s for files <50MB; <60s for PDFs >100 pages
- **Capacity:** Handle batch of 50 files without memory pressure
- **Security:** Files never leave local disk. No temporary cloud upload.
- **Audit:** All ingestion events logged in `raw/.ingest-log.json`

#### 9) Definition of done

- All acceptance criteria demonstrated
- PDF extraction tested on 20+ diverse layouts (academic papers, reports, slides)
- OCR accuracy validated against 5 scanned documents
- Batch drop stress-tested with 50 files
- Error handling covers all scenarios without crashes

---

## Epic: WIKI COMPILATION (COMPILE)

---

### US-003: Initial wiki compilation

#### 1) Story information

- **Title:** Compile raw sources into wiki
- **ID:** US-003
- **Author:** Product Manager — Ali Naserifar
- **Created date:** 2026-04-04
- **Priority:** P0
- **Target release:** v1.0 — Phase 2
- **Status:** Draft
- **Linked epic:** COMPILE

#### 2) User story

*As a* **researcher with 10+ sources in raw/**  
*I want* **the LLM to compile them into a structured, interlinked wiki**  
*So that* **I have a navigable knowledge graph instead of a pile of disconnected documents**

**JTBD:** "When I've accumulated enough raw material on a topic, I want to trigger compilation and get a wiki with concept articles, summaries, categories, and backlinks — without writing any of it myself."

#### 3) Business context

- **Problem:** Raw sources are isolated; no cross-referencing, no concept extraction, no synthesis. The researcher must hold the entire structure in their head.
- **Scope (in):** 6-step pipeline (summarize → extract concepts → generate articles → create backlinks → build index → detect conflicts). Wiki output as .md files with YAML frontmatter.
- **Out of scope:** Multi-language compilation, citation formatting (APA/MLA), visual diagram generation
- **Success metrics:**
  - ≥1 wiki article per 2 raw sources
  - ≥90% of factual claims traceable to source
  - Zero orphan articles (every article has ≥1 backlink)
  - Compilation time: <2 min for 15 sources

#### 4) Acceptance criteria (BDD)

**Scenario: First compilation with 15 sources**  
**Given** the user has 15 markdown files in raw/  
**When** the user triggers "Compile Wiki"  
**Then** the system creates `wiki/` directory with:
- `INDEX.md` — master index with one-line summary per article, organized by category
- `CONCEPTS.md` — extracted concept taxonomy (hierarchical)
- `CONFLICTS.md` — any detected cross-source contradictions
- `SCHEMA.md` — wiki format documentation (auto-generated)
- `CHANGELOG.md` — timestamped compilation log
- Individual article .md files in category subdirectories  
**And** each article includes: title, summary, key points, source references (`[[raw/source-name]]`), related articles (`[[wiki/article]]`)  
**And** compilation progress is shown with step labels and estimated time  
**And** total token usage and estimated cost are displayed on completion

**Scenario: Conflicting information across sources**  
**Given** two sources in raw/ contain contradictory claims  
**When** compilation processes both sources  
**Then** the generated article notes the discrepancy inline: "⚠️ Conflict: [Source A] states X while [Source B] states Y"  
**And** the conflict is logged in `CONFLICTS.md` with severity, article, and source references

**Scenario: Compilation failure mid-process**  
**Given** compilation is running and the LLM API returns a rate limit or error  
**When** the error occurs  
**Then** all successfully compiled articles are preserved  
**And** a checkpoint is saved in `wiki/.checkpoint.json`  
**And** the system displays "Compilation paused at step 3/6 — 8 of 15 sources processed. Resume?"  
**And** resuming continues from the checkpoint, not from scratch

**Scenario: Empty or corrupt source in raw/**  
**Given** one file in raw/ is empty or has corrupt markdown  
**When** compilation encounters it  
**Then** the file is skipped with a warning in the compilation log  
**And** remaining sources compile normally  
**And** the skipped file is listed in CHANGELOG.md

#### 5) Functional requirements

- **FR-01:** Pipeline orchestrated as 6 sequential steps, each producing intermediate artifacts
- **FR-02:** Each step's prompt chain is configurable via `AGENTS.md` schema file in project root
- **FR-03:** Source provenance: every claim in wiki articles links back to `raw/[source].md` with section reference
- **FR-04:** Concept extraction identifies: entities, relationships, hierarchies, and cross-source frequencies
- **FR-05:** Article generation groups related concepts; minimum article length 200 words, maximum 3,000
- **FR-06:** Backlinks are bidirectional: if Article A links to Article B, Article B's "Referenced by" section includes Article A
- **FR-07:** Token budget system: user sets max tokens per compilation; system optimizes within budget (e.g., shorter summaries when budget is tight)
- **FR-08:** Atomic output: compiled wiki is staged in `wiki/.staging/` and promoted to `wiki/` only on full success

#### 6) UX / UI requirements

- **Progress panel:** 6-step pipeline with current step highlighted, estimated time remaining, token counter
- **Completion screen:** Summary card with: articles generated, concepts extracted, conflicts detected, tokens used, estimated cost
- **Preview:** User can browse compiled wiki immediately in the viewer tab
- **Abort:** "Cancel compilation" button available at any step; preserves checkpoint

#### 7) Edge cases

- All sources on same topic: compilation should still produce multiple articles for sub-concepts
- Sources with very different quality (academic paper vs. blog post): weight academic sources higher in conflict resolution
- Very short sources (<500 words): still summarize, but may not produce standalone article
- Unicode-heavy content (math, CJK): preserve in markdown without corruption

#### 8) Non-functional requirements

- **Performance:** <2 min for 15 sources (assuming ~3K words avg per source, ~45K total)
- **Cost:** <$2 USD for 15-source compilation (at Claude Sonnet pricing)
- **Reliability:** Zero data loss on failure; checkpoint + atomic staging
- **Auditability:** Full prompt chain logged in `wiki/.compilation-log/[timestamp]/` for debugging

#### 9) Definition of done

- Compilation tested on 5 diverse source sets (academic, journalistic, technical, mixed, adversarial)
- INDEX.md accurately reflects all generated articles
- Zero orphan articles in output
- Conflict detection validated against 3 known-contradictory source pairs
- Token usage within 10% of budget estimate
- Documentation: AGENTS.md schema documented with examples

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

*As a* **researcher who just added a new source to raw/**  
*I want* **the wiki to update incrementally without re-processing existing content**  
*So that* **I don't waste tokens or time every time I add one document**

**JTBD:** "When I clip a new paper, I want to say 'file this to our wiki' and have it integrated in seconds."

#### 3) Business context

- **Problem:** Full recompilation is expensive ($2+ per run) and slow; doesn't scale beyond ~50 sources
- **Scope (in):** Diff detection, affected-article identification via dependency graph, targeted article updates, index refresh, new backlink insertion
- **Out of scope:** Auto-detection of raw/ file system changes (user triggers manually), real-time streaming compilation
- **Success metrics:**
  - Incremental compile for 1 new source: <30s
  - Token usage: <20% of full compile
  - Zero regression in existing article quality
  - CHANGELOG.md updated with diff summary

#### 4) Acceptance criteria (BDD)

**Scenario: Add one new source to 80-article wiki**  
**Given** the wiki has 80 articles compiled from 40 sources  
**When** the user adds a new raw source and triggers "Update Wiki"  
**Then** the system:
1. Summarizes the new source
2. Identifies which existing concepts/articles are affected (via concept overlap)
3. Updates affected articles with new information and backlinks
4. Creates new article(s) if new concepts are introduced
5. Updates INDEX.md, CONCEPTS.md, and CHANGELOG.md  
**And** untouched articles remain byte-identical  
**And** CHANGELOG.md entry shows: added articles, modified articles, new backlinks, tokens used

**Scenario: New source contradicts existing wiki content**  
**Given** the new source conflicts with content in an existing article  
**When** incremental compilation detects the conflict  
**Then** the existing article is updated with the discrepancy noted inline  
**And** CONFLICTS.md is appended with the new conflict

**Scenario: New source adds no new information**  
**Given** the new source covers topics already thoroughly documented in the wiki  
**When** incremental compilation analyzes it  
**Then** the source is referenced in relevant articles' source lists  
**And** no new articles are generated  
**And** the user is informed: "Source indexed but no new articles generated — concepts already covered"

#### 5) Functional requirements

- **FR-01:** Content hashing to detect which raw sources have changed since last compile
- **FR-02:** Dependency graph: `wiki/.deps.json` maps which wiki articles depend on which raw sources
- **FR-03:** Affected-article detection: compare new source concepts against existing CONCEPTS.md
- **FR-04:** Atomic updates via `wiki/.staging/` — committed only on success
- **FR-05:** Rollback: "Revert Last Update" restores from `wiki/.backup/[timestamp]/`
- **FR-06:** CLI support: `compendium update [path-to-new-source]` or `compendium update --all-new`

#### 6) Edge cases

- Multiple new sources added at once: batch incremental compile
- Source deleted from raw/: flag dependent wiki articles as potentially stale (don't auto-delete)
- Source modified (not new): re-summarize and update affected articles
- Wiki manually edited by user (despite "LLM writes" principle): preserve user edits, merge with LLM updates

#### 7) Non-functional requirements

- **Performance:** <30s per new source for wikis up to 200 articles
- **Cost:** <$0.40 per incremental update (at Claude Sonnet pricing)
- **Idempotency:** Running "Update Wiki" twice with no changes produces identical output

#### 9) Definition of done

- Incremental update tested on wikis of 20, 50, 100, 200 articles
- Byte-identical verification for untouched articles
- Rollback tested and verified
- Cost tracking accurate within 10%

---

## Epic: QUERY & OUTPUT (QA)

---

### US-005: Q&A against wiki

#### 1) Story information

- **Title:** Ask complex questions against knowledge base
- **ID:** US-005
- **Priority:** P0
- **Target release:** v1.0 — Phase 3 (Weeks 7–9)
- **Status:** Draft
- **Linked epic:** QA

#### 2) User story

*As a* **researcher with a 100-article wiki**  
*I want* **to ask complex, multi-hop questions and get answers grounded in my knowledge base**  
*So that* **I can extract insights spanning multiple sources without reading everything**

**JTBD:** "When I need to compare findings across 20 papers, I want to ask a question and get a synthesized answer with source citations."

#### 3) Business context

- **Problem:** Reading 400K words to find an answer is impractical; existing tools lack source-grounded Q&A with persistent knowledge
- **Scope (in):** Chat UI, CLI interface, index-first retrieval, multi-article context assembly, cited answers, conversation history within session
- **Out of scope:** Voice interaction, external web search augmentation, cross-wiki queries
- **Success metrics:**
  - Answer relevance rated ≥4/5 by users
  - ≥80% of cited sources are correct (verified by user)
  - p95 response time <15 seconds
  - Users ask ≥5 questions per session on average

#### 4) Acceptance criteria (BDD)

**Scenario: Multi-hop question**  
**Given** the user asks "What are the main disagreements between Source A and Source B on topic X?"  
**When** the Q&A engine processes the query  
**Then** the system reads INDEX.md to identify relevant articles  
**And** loads the relevant wiki articles into context (within token budget)  
**And** returns a synthesized answer with inline citations `[[Article Name]]`  
**And** displays which articles were consulted in a collapsible "Sources used" section

**Scenario: Question with no relevant wiki content**  
**Given** the user asks about a topic not covered in the wiki  
**When** the system searches the index and finds no matches  
**Then** it responds: "I don't have information about this in your knowledge base. Would you like to add sources about this topic?"

**Scenario: Follow-up question**  
**Given** the user asked a question and received an answer  
**When** the user asks a follow-up referencing "that" or "those results"  
**Then** the system maintains conversation context and resolves pronouns correctly  
**And** can reference previously loaded articles without re-reading them

**Scenario: Very broad question exceeding token budget**  
**Given** the user asks a question that touches 50+ articles  
**When** the system detects token budget would be exceeded  
**Then** it selects the top 10 most relevant articles by index-score  
**And** informs the user: "This question spans many topics. I've focused on the 10 most relevant articles. Ask a more specific question for deeper coverage."

#### 5) Functional requirements

- **FR-01:** Index-first retrieval: always reads INDEX.md → scores relevance → loads top-N articles
- **FR-02:** Token budget: configurable per query (default: 80% of model's context window)
- **FR-03:** Citation format: `[[Article Title]]` inline, with expandable source list showing article + relevant section
- **FR-04:** Conversation history: maintained per session, clearable, max 20 turns
- **FR-05:** Dual interface: chat UI in desktop app + CLI `compendium ask "question"`
- **FR-06:** Search engine as fallback: if index-first retrieval is insufficient, fall back to full-text search via CLI tool

#### 6) UX / UI requirements

- **Chat panel:** Left sidebar with conversation list, main panel with messages, input at bottom
- **Citations:** Inline wikilinks are clickable → opens article in viewer pane
- **Sources used:** Collapsible section at bottom of each answer listing articles consulted
- **Token counter:** Small indicator showing tokens used / budget for current query
- **Loading:** "Researching..." with spinner + "Reading 4 articles..." status text

#### 7) Edge cases

- Very short wiki (<5 articles): still functional, but inform user that coverage is limited
- Question in different language than wiki content: attempt to answer, note language mismatch
- Ambiguous question: ask one clarifying question before answering
- Question about wiki structure ("how many articles do I have?"): answer from INDEX.md metadata directly

#### 8) Non-functional requirements

- **Performance:** p95 response <15 seconds including article retrieval + LLM generation
- **Context efficiency:** Compress article content (summaries + key points) when budget is tight
- **Conversation:** Session state persisted locally; survives app restart within same day

#### 9) Definition of done

- Tested on 20 diverse questions across 3 different wiki domains
- Citation accuracy validated: ≥80% correct
- CLI and chat UI both functional with identical answer quality
- Follow-up questions resolve correctly in 3-turn conversations
- Token budget respected without truncating answers mid-sentence

---

### US-006: Output rendering — markdown reports

#### 1) Story information

- **Title:** Generate markdown report from Q&A
- **ID:** US-006
- **Priority:** P1
- **Target release:** v1.0 — Phase 3
- **Status:** Draft
- **Linked epic:** QA

#### 2) User story

*As a* **researcher**  
*I want* **Q&A answers rendered as structured markdown report files**  
*So that* **I have polished deliverables I can share, reference, or file back into the wiki**

#### 4) Acceptance criteria (BDD)

**Scenario: Generate report from query**  
**Given** the user asks a question and clicks "Save as Report" (or uses `--output report` flag)  
**When** the answer is generated  
**Then** a markdown file is created in `output/reports/[date]-[slug].md`  
**And** it includes: title, date, query text, structured answer with headings, citations section, source list  
**And** the user is prompted: "File this report into wiki? [Yes / No]"

**Scenario: Report with visual data**  
**Given** the user asks a question involving numerical data  
**When** the answer contains comparative data  
**Then** the report includes a markdown table summarizing the data  
**And** optionally generates a matplotlib chart saved as PNG in `output/charts/`

#### 5) Functional requirements

- **FR-01:** Report format: YAML frontmatter + structured body with H2 sections + citations footer
- **FR-02:** Frontmatter includes: `type: report`, `query`, `generated_at`, `sources_used`, `tokens_used`
- **FR-03:** Filing integration: "File to wiki" triggers US-008 flow
- **FR-04:** CLI: `compendium ask "question" --output report`

#### 9) Definition of done

- Reports render correctly in Obsidian, VS Code, and Compendium viewer
- ≥70% of test reports require zero manual editing before filing

---

### US-007: Output rendering — slide decks

#### 1) Story information

- **Title:** Generate Marp slide deck from Q&A
- **ID:** US-007
- **Priority:** P1
- **Target release:** v1.0 — Phase 3
- **Status:** Draft
- **Linked epic:** QA

#### 2) User story

*As a* **content creator preparing a presentation**  
*I want* **to generate a Marp-format slide deck from my wiki on a given topic**  
*So that* **I can quickly produce presentation material grounded in my research**

#### 4) Acceptance criteria (BDD)

**Scenario: Generate 10-slide deck**  
**Given** the user queries "Create a 10-slide deck on [topic] from my wiki"  
**When** the system processes the request  
**Then** a Marp .md file is created in `output/slides/[date]-[slug].md`  
**And** each slide has: title, 3–5 bullet points, speaker notes  
**And** the deck includes a title slide and a sources slide  
**And** it renders in Compendium viewer's Marp plugin

**Scenario: Insufficient wiki content for requested slide count**  
**Given** the wiki has limited content on the requested topic  
**When** the system detects it can't fill 10 slides  
**Then** it generates fewer slides and informs: "Generated 6 slides. Wiki content on this topic is limited."

#### 5) Functional requirements

- **FR-01:** Output follows Marp markdown syntax with `---` slide separators and `marp: true` frontmatter
- **FR-02:** Speaker notes use `<!-- notes -->` blocks
- **FR-03:** CLI: `compendium ask "create deck on X" --output slides --count 10`

#### 9) Definition of done

- Slides render correctly in Marp CLI and Obsidian Marp plugin
- Tested on 3 different topics with 5, 10, and 15 slide requests

---

### US-008: Feedback filing — output back to wiki

#### 1) Story information

- **Title:** File Q&A output back into wiki
- **ID:** US-008
- **Priority:** P0
- **Target release:** v1.0 — Phase 3
- **Status:** Draft
- **Linked epic:** QA

#### 2) User story

*As a* **researcher**  
*I want* **to file my Q&A outputs back into the wiki with one click**  
*So that* **every exploration compounds the knowledge base for future queries**

**JTBD:** "When I generate a synthesis comparing three theories, that report should become a wiki article that future queries can reference."

#### 3) Business context

- **Problem:** Without feedback filing, the wiki is static after compilation; Q&A outputs are ephemeral
- **Goal:** Close the compounding loop — every query can enrich the knowledge base
- **Success metrics:**
  - ≥50% of Q&A outputs are filed back
  - Filed articles are referenced in ≥30% of subsequent queries
  - Filing + index update <5 seconds

#### 4) Acceptance criteria (BDD)

**Scenario: File report into wiki**  
**Given** the user generated a report (US-006) or slide deck (US-007)  
**When** the user clicks "File to Wiki"  
**Then** the output is:
1. Moved to appropriate `wiki/[category]/` subdirectory (auto-detected from content)
2. Tagged with `source: user-query`, `filed_at: [ISO date]` in frontmatter
3. Backlinks inserted into related existing wiki articles
4. INDEX.md updated with new entry  
**And** confirmation shown: "Filed as wiki/concepts/[name].md — 3 articles updated with backlinks"

**Scenario: Filing would create duplicate**  
**Given** a wiki article with similar content already exists  
**When** the user clicks "File to Wiki"  
**Then** the system warns: "Similar article exists: [name]. Merge content, replace, or keep both?"

**Scenario: Merge with existing article**  
**Given** the user chose "Merge" on duplicate detection  
**When** the merge executes  
**Then** the new content is appended under a "## Additional analysis ([date])" section  
**And** new source references are added to the existing article's source list

#### 5) Functional requirements

- **FR-01:** Category auto-detection by comparing output concepts against CONCEPTS.md taxonomy
- **FR-02:** Backlink insertion: find all wiki articles mentioning concepts in the filed output
- **FR-03:** Atomic: staging → commit. Rollback available.
- **FR-04:** Filed articles marked with `origin: qa-output` vs. `origin: compilation` for tracking
- **FR-05:** INDEX.md update is atomic with the article filing

#### 7) Edge cases

- User files the same output twice: detect by content hash, warn
- Filed output references raw/ sources that have been deleted: preserve references but mark as `[source removed]`
- Filing during an active compilation: queue and apply after compilation completes

#### 9) Definition of done

- Filing tested with reports, slide decks, and raw chat answers
- Backlink insertion verified: new article appears in related articles' "Referenced by" sections
- INDEX.md consistency verified after 10 sequential filings
- Duplicate detection works for exact and near-duplicate content

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
*I want* **the system to detect inconsistencies, gaps, broken links, and contradictions**  
*So that* **my knowledge base maintains integrity as it scales**

**JTBD:** "When my wiki grows past 100 articles, I need confidence that the content is consistent — like a test suite for knowledge."

#### 3) Business context

- **Problem:** Wiki entropy increases with scale: contradictions appear, links break, coverage gaps emerge
- **Success metrics:** ≥80% of detected issues are actionable; false positive rate <15%

#### 4) Acceptance criteria (BDD)

**Scenario: Run full health check**  
**Given** the user triggers "Lint Wiki" or it runs on schedule (daily)  
**When** the linting engine completes  
**Then** `wiki/HEALTH_REPORT.md` is generated with:
- **Critical:** Broken internal links (references to non-existent articles)
- **Warning:** Contradictions between articles (specific passages cited)
- **Warning:** Orphan articles (no inbound backlinks)
- **Info:** Coverage gaps (concepts mentioned but no dedicated article)
- **Info:** Stale articles (source updated but wiki not recompiled)
- **Info:** Suggested new articles based on connection analysis  
**And** each issue has: severity, location (article + line), description, suggested fix

**Scenario: Linting suggests new article**  
**Given** 8 articles reference "reinforcement learning" but no dedicated article exists  
**When** linting detects this pattern  
**Then** it suggests: "Create article: 'Reinforcement Learning' — referenced in 8 articles"  
**And** the user can click "Generate" to trigger compilation for that concept

**Scenario: Missing data imputation**  
**Given** an article contains `[MISSING: publication date]`  
**When** linting runs with web search enabled  
**Then** the system searches for the missing datum  
**And** proposes: "Found: published 2024-03-15 (source: doi.org/...). Accept?"

#### 5) Functional requirements

- **FR-01:** Link checker: validate all `[[wikilinks]]` resolve to existing articles
- **FR-02:** Contradiction detector: LLM compares claims across related articles
- **FR-03:** Coverage analyzer: concepts in CONCEPTS.md without dedicated articles
- **FR-04:** Staleness tracker: compare raw/ modification dates against wiki article compilation dates
- **FR-05:** Orphan finder: articles with zero inbound backlinks
- **FR-06:** Connection discoverer: suggest articles based on co-occurrence patterns in existing content
- **FR-07:** Scheduled runs: configurable cadence (daily/weekly/manual)

#### 9) Definition of done

- Linting tested on wikis with 50, 100, 200 articles
- Broken link detection catches 100% of actual broken links
- Contradiction detection validated against 5 known contradictory pairs
- False positive rate measured and <15%

---

## Epic: VIEWER & TOOLS (VIEW)

---

### US-010: Interactive wiki graph viewer

#### 1) Story information

- **Title:** Knowledge graph visualization
- **ID:** US-010
- **Priority:** P1
- **Target release:** v1.0 — Phase 4
- **Status:** Draft
- **Linked epic:** VIEW

#### 2) User story

*As a* **researcher**  
*I want* **to see my wiki as an interactive graph of interconnected articles**  
*So that* **I can visually discover patterns, identify gaps, and navigate large wikis**

#### 4) Acceptance criteria (BDD)

**Scenario: View 100-article graph**  
**Given** the wiki has 100+ articles with backlinks  
**When** the user opens Graph View  
**Then** articles appear as nodes, backlinks as edges  
**And** nodes colored by category (from CONCEPTS.md taxonomy)  
**And** node size proportional to inbound link count  
**And** clicking a node opens the article in the reader pane  
**And** orphan nodes visually distinct (faded outline, no fill)

**Scenario: Filter graph by category**  
**Given** the graph is displayed  
**When** the user selects a category filter  
**Then** only nodes in that category (and their cross-category edges) are shown

**Scenario: Search within graph**  
**Given** the graph is displayed  
**When** the user types in the graph search box  
**Then** matching nodes are highlighted and the view centers on them

#### 5) Functional requirements

- **FR-01:** Graph rendered with D3.js force-directed layout or equivalent
- **FR-02:** Performance: 200+ nodes at 60fps with smooth pan/zoom
- **FR-03:** Node metadata on hover: title, category, word count, source count, last updated
- **FR-04:** Edge labels optional (toggle): show relationship type from backlink context
- **FR-05:** Export graph as SVG or PNG

#### 9) Definition of done

- Graph renders 200 nodes at 60fps on M1 MacBook Air
- Click-to-article navigation works for all node types
- Category coloring matches CONCEPTS.md taxonomy
- Pan, zoom, filter, and search all functional

---

### US-011: Wiki search engine

#### 1) Story information

- **Title:** Full-text and semantic search
- **ID:** US-011
- **Priority:** P1
- **Target release:** v1.0 — Phase 4
- **Status:** Draft
- **Linked epic:** VIEW

#### 2) User story

*As a* **researcher or LLM agent**  
*I want* **to search the wiki using full-text and semantic queries**  
*So that* **I can quickly find specific content for Q&A or manual reading**

#### 4) Acceptance criteria (BDD)

**Scenario: CLI search by LLM agent**  
**Given** the LLM agent processes a complex query  
**When** it invokes `compendium search "attention mechanism transformers"`  
**Then** top 5 results returned with: title, relevance score, 100-word snippet  
**And** results in <2 seconds

**Scenario: Web UI search by user**  
**Given** the user opens the search panel  
**When** typing a query  
**Then** results appear as-you-type (debounced 200ms)  
**And** matched terms highlighted in snippets  
**And** clicking a result opens the article

**Scenario: No results**  
**Given** the user searches for a term not in the wiki  
**When** zero results are found  
**Then** display: "No articles match '[query]'. Try broader terms or add sources about this topic."

#### 5) Functional requirements

- **FR-01:** Full-text index built on wiki compilation (inverted index over article content)
- **FR-02:** Semantic search via lightweight embedding model (optional, configurable)
- **FR-03:** Dual interface: web UI panel in desktop app + CLI `compendium search "query"`
- **FR-04:** Results ranked by relevance (TF-IDF or BM25)
- **FR-05:** Index auto-updates on wiki changes (compilation, filing, linting)

#### 9) Definition of done

- Search tested on 100-article wiki with 50 diverse queries
- p95 response <2s for full-text, <5s for semantic
- CLI output parseable by LLM (structured JSON)

---

### US-012: Auto-maintained wiki index

#### 1) Story information

- **Title:** Self-maintaining wiki index
- **ID:** US-012
- **Priority:** P0
- **Target release:** v1.0 — Phase 2
- **Status:** Draft
- **Linked epic:** COMPILE

#### 2) User story

*As the* **Q&A engine (system)**  
*I want* **INDEX.md and CONCEPTS.md to always reflect the current wiki state**  
*So that* **every query starts with an accurate knowledge map**

#### 4) Acceptance criteria (BDD)

**Scenario: Index sync after incremental compile**  
**Given** a new article is added (compilation or filing)  
**When** the article is committed to wiki/  
**Then** INDEX.md is atomically updated with the new entry and refreshed summaries  
**And** CONCEPTS.md taxonomy updated if new concepts introduced  
**And** INDEX.md sorted by category, then alphabetically

**Scenario: Article deleted by user**  
**Given** the user manually deletes a wiki article  
**When** the system detects the deletion  
**Then** INDEX.md entry is removed  
**And** backlinks in other articles are flagged as broken (for linting)

**Scenario: Index consistency check**  
**Given** the user runs `compendium verify-index`  
**When** the system checks INDEX.md against actual wiki/ contents  
**Then** it reports any mismatches and offers to rebuild the index

#### 5) Functional requirements

- **FR-01:** INDEX.md format: `| Article | Category | Summary (1 line) | Sources | Last updated |`
- **FR-02:** CONCEPTS.md format: hierarchical bullet list with article counts per concept
- **FR-03:** Every wiki-modifying operation (compile, file, lint-fix) triggers index refresh
- **FR-04:** Index rebuild command: `compendium rebuild-index` (full regeneration from wiki/ scan)
- **FR-05:** File system watcher (optional): detect external changes to wiki/ directory

#### 9) Definition of done

- Index consistent after 20 sequential operations (mix of compile, file, delete)
- Rebuild produces byte-identical index to incremental updates
- `verify-index` detects all synthetically introduced mismatches

---

## Epic: CONFIGURATION (CONFIG)

---

### US-013: BYOM — Bring your own model

#### 1) Story information

- **Title:** LLM provider configuration
- **ID:** US-013
- **Priority:** P0
- **Target release:** v1.0 — Phase 4
- **Status:** Draft
- **Linked epic:** CONFIG

#### 2) User story

*As a* **user**  
*I want* **to configure which LLM provider and model Compendium uses**  
*So that* **I control my cost, privacy, and quality tradeoff**

**JTBD:** "When I'm doing sensitive research, I want to use local Ollama. When I need max quality, I switch to Claude Opus. I never want to be locked to one provider."

#### 3) Business context

- **Problem:** Vendor lock-in reduces trust and limits adoption; users have different cost/privacy/quality needs
- **Scope (in):** Multi-provider support, per-operation model selection, API key management, token usage dashboard
- **Out of scope:** Model fine-tuning, custom model hosting, automatic model switching based on query complexity
- **Success metrics:** ≥40% of users configure multiple providers within 3 months

#### 4) Acceptance criteria (BDD)

**Scenario: Configure Anthropic Claude**  
**Given** the user opens Settings → LLM Provider  
**When** the user selects "Anthropic" and enters their API key  
**Then** the key is stored in the OS keychain (not plain text on disk)  
**And** available models are listed (sonnet, opus, haiku)  
**And** a test query validates the key  
**And** estimated cost per 1K tokens is displayed

**Scenario: Switch to local Ollama**  
**Given** the user has Ollama running locally  
**When** the user selects "Ollama" and enters endpoint (default: localhost:11434)  
**Then** available models are auto-detected  
**And** cost indicator shows "$0.00 / query (local)"  
**And** a warning if context window <32K: "This model may struggle with large wiki queries"

**Scenario: Per-operation model assignment**  
**Given** the user has multiple providers configured  
**When** they open "Model Assignment"  
**Then** they can set: Compilation → Claude Opus (quality), Q&A → Claude Sonnet (speed+cost), Linting → Ollama Llama (free)

**Scenario: Invalid API key**  
**Given** the user enters an invalid key  
**When** the test query fails  
**Then** error: "Could not connect. Check your API key."  
**And** previous working config is preserved

#### 5) Functional requirements

- **FR-01:** Supported: Anthropic, OpenAI, Google Gemini, Ollama, any OpenAI-compatible endpoint
- **FR-02:** API keys in OS keychain (macOS Keychain, Windows Credential Manager, Linux Secret Service)
- **FR-03:** Per-operation model: compile, qa, lint each independently configurable
- **FR-04:** Token dashboard: cumulative tokens, estimated cost, breakdown by operation type, daily/weekly/monthly views
- **FR-05:** Rate limiting: respect provider limits with exponential backoff + retry
- **FR-06:** Model context window validation: warn if selected model's context < required for operation

#### 6) UX / UI requirements

- **Settings panel:** Provider list with status indicators (green = connected, red = error, gray = unconfigured)
- **Model assignment:** 3 dropdowns (Compilation model, Q&A model, Linting model)
- **Token dashboard:** Card with current month's usage, cost estimate, sparkline chart
- **Test connection:** Button per provider with inline result

#### 7) Edge cases

- Provider goes down mid-compilation: save checkpoint, retry with backoff, offer provider switch
- User removes API key for currently active provider: warn before removal, require alternative
- Ollama model requires download: show download progress, don't block other operations

#### 8) Non-functional requirements

- **Security:** API keys never written to disk in plain text. Never logged. Never sent to Compendium servers.
- **Resilience:** Graceful fallback if primary provider fails (configurable secondary provider)
- **Audit:** Token usage logged locally in `~/.compendium/usage/[month].json`

#### 9) Definition of done

- All 4 providers tested (Anthropic, OpenAI, Gemini, Ollama)
- Per-operation model assignment functional
- Token dashboard accurate within 5% of actual API billing
- API key storage verified in OS keychain (not file system)
- Provider failure + retry tested

---

## Appendix: Story dependency map

```
US-001 (Web clip) ──┐
                     ├──→ US-003 (Initial compile) ──→ US-012 (Index) ──→ US-005 (Q&A)
US-002 (File drop) ──┘          │                                              │
                                │                                              ├──→ US-006 (Reports)
                          US-004 (Incremental)                                 ├──→ US-007 (Slides)
                                                                               │
                                                                         US-008 (Filing) ──→ loops back to US-005
                                                                               
US-009 (Linting) ── depends on US-003 + US-012
US-010 (Graph)   ── depends on US-003 + US-012
US-011 (Search)  ── depends on US-003 + US-012
US-013 (BYOM)    ── independent, but required by US-003, US-005, US-009
```
