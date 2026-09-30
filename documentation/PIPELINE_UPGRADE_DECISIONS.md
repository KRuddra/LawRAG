# Pipeline Upgrade — Architecture Decision Record

**Status:** Decisions 1–12 recorded and locked (2026-09-29); Decision 6 removed from scope. MVP = federal-first (US federal + Canada federal + BC).
**Date:** 2026-09-25
**Context:** Upgrading the RAG pipeline from a single-jurisdiction proof-of-concept (Wisconsin, ~5 local PDFs) into a **multi-jurisdiction legal assistant** covering every Canadian province/territory and every US state (plus both federal levels), where a user selects a **jurisdiction** and one or more **categories of law** and gets answers grounded only in the law that applies there — kept current over time.

> The **Conclusion** section near the bottom is intentionally left as a placeholder; it will be filled in once these decisions are finalized.

---

## Table of Contents

1. [Current Infrastructure](#1-current-infrastructure)
2. [Decisions](#2-decisions)
   - [Decision 1 — How we acquire the legal data](#decision-1--how-we-acquire-the-legal-data)
   - [Decision 2 — Source registry & how we discover new sources](#decision-2--source-registry--how-we-discover-new-sources)
   - [Decision 3 — Handling broken / stale sources](#decision-3--handling-broken--stale-sources)
   - [Decision 4 — Where we store raw source documents](#decision-4--where-we-store-raw-source-documents)
   - [Decision 5 — Vector + metadata database](#decision-5--vector--metadata-database)
   - [Decision 6 — Update / refresh strategy](#decision-6--update--refresh-strategy)
   - [Decision 7 — Jurisdiction scoping & isolation](#decision-7--jurisdiction-scoping--isolation)
   - [Decision 8 — Category-of-law taxonomy & classification](#decision-8--category-of-law-taxonomy--classification)
   - [Decision 9 — Currency & versioning (point-in-time)](#decision-9--currency--versioning-point-in-time)
   - [Decision 10 — Embedding cost strategy at scale](#decision-10--embedding-cost-strategy-at-scale)
   - [Decision 11 — Ingestion orchestration](#decision-11--ingestion-orchestration)
   - [Decision 12 — Compliance & licensing posture](#decision-12--compliance--licensing-posture)
3. [Proposed Future Infrastructure](#3-proposed-future-infrastructure)
4. [Build Roadmap & Stages](#build-roadmap--stages)
5. [Conclusion](#4-conclusion)
6. [FAQ — Where we get our data (with links)](#5-faq--where-we-get-our-data-with-links)

---

## 1. Current Infrastructure

Today the system is a single-machine proof-of-concept. A user opens the web UI, asks a question, and the backend embeds the query, runs hybrid search over a **local** ChromaDB, then calls OpenAI to generate a cited answer. Documents are ingested manually from a handful of PDFs in `data/raw/`.

```
┌──────────────┐
│   Officer    │  (browser)
│  (Customer)  │
└──────┬───────┘
       │ 1. Types a legal question
       ▼
┌──────────────────────┐
│  Next.js Frontend    │  http://localhost:3000
│  (chat UI)           │
└──────┬───────────────┘
       │ 2. POST /api/chat  { message }
       ▼
┌───────────────────────────────────────────────┐
│  FastAPI Backend   (http://localhost:8000)     │
│                                                │
│   hybrid search ─► build context ─► generate   │
└───┬───────────────────────┬───────────────┬───┘
    │ 3. embed query +       │ 5. LLM call   │
    │    similarity search   │               │
    ▼                        ▼               │
┌──────────────┐   ┌──────────────────┐      │
│  ChromaDB    │   │  OpenAI API      │◄─────┘
│  (local,     │   │  • embeddings    │
│   on disk)   │   │  • gpt-3.5-turbo │
└──────────────┘   └──────────────────┘

Ingestion (offline, manual, one-off):
  data/raw/*.pdf ─► parse ─► chunk ─► embed (OpenAI) ─► ChromaDB
```

**Limitations that motivate this upgrade:**
- Single jurisdiction, tiny static corpus; no notion of "which law applies where."
- ChromaDB is embedded/local — weak filtering, concurrency, and horizontal scale.
- Ingestion is manual and PDF-only; no freshness, no versioning, no update signal.
- Every embedding call hits a paid API with no caching.
- No concept of category-of-law, currency (in-force vs repealed), or provenance at scale.

---

## 2. Decisions

Each decision below states **why** we're making it and how it will be used, then lists options. **The first option in every list is the recommended one.**

> **One product input we need from you up front:** several data sources price/permit differently for **commercial vs non-commercial** use (Open States/Plural, CourtListener membership, Caselaw Access Project, and especially CanLII). This affects Decisions 1, 2, and 12. The recommendations below assume a **commercial** product and therefore bias hard toward official/public-domain sources.

| # | Decision | Decision made (locked 2026-09-29) |
|---|----------|--------------------|
| 1 | How we acquire data | Official bulk data & APIs first — MVP = US federal (govinfo) + Canada federal (Justice Laws) + BC (BC Laws) |
| 2 | Source discovery | Hybrid — curated registry + AI-suggested links + **human approval** (lightweight; runs rarely) |
| 3 | Broken/stale sources | Option A — flag-for-review + backoff (never silent delete) |
| 4 | Raw document storage | **Option B — store originals in the repo** (avoid cloud cost; watch GitHub file-size limits) |
| 5 | Vector + metadata DB | **Option C — keep ChromaDB** for now |
| 6 | ~~Refresh strategy~~ | ❌ **REMOVED from scope** — no automated refresh for the MVP |
| 7 | Jurisdiction isolation | Option A — hard metadata filter at query time |
| 8 | Category taxonomy | Option A — controlled vocabulary + hybrid classification |
| 9 | Currency/versioning | **Option B — latest-only** for now |
| 10 | Embedding cost | Option A — content-hash cache + batching; provider swappable |
| 11 | Orchestration | Option A — decoupled ingestion pipeline (MVP: simple script) |
| 12 | Compliance | ⚠️ **Option B — scrape reachable sources** (hard exception: never CanLII; flagged for reconsideration) |

---

### Decision 1 — How we acquire the legal data

**Why / how it's used:** This is the foundation everything else sits on. We need statutes, regulations, and case law for 60+ jurisdictions, kept current. The acquisition method drives cost, freshness, parse quality, legal risk, and engineering effort.

**Option A — Official bulk data & APIs first, per-jurisdiction adapters _(Recommended)_**
Pull from government/open publishers that already release machine-readable law (US: govinfo USLM XML, CourtListener/CAP, Open States; Canada: Justice Laws XML, BC Laws API, provincial e-laws). One adapter per source. Fall back to structured HTML scraping only where no bulk source exists, and PDF parsing only as a last resort.
- **Pros:** authoritative and citable; machine-readable (XML/JSON) → clean parsing and metadata; legally safe (public domain / open licence); efficient incremental updates via ETags/API; isolates each source behind a small adapter.
- **Cons:** heterogeneous formats mean many adapters; genuine coverage gaps (US state *codified* statutes and most Canadian *case law* — see FAQ) need fallbacks; upfront adapter engineering.

**Option B — Mass PDF corpus (download & store all PDFs)**
- **Pros:** simple mental model; works offline; uniform input.
- **Cons:** storage-heavy and costly; PDFs are the *worst* format to parse (layout noise, OCR); no clean update signal (must re-download and diff whole files); loses structure/metadata; does not scale to millions of documents. (This is the option you already flagged as inefficient.)

**Option C — Generic web scraping of legal sites**
- **Pros:** flexible; can reach anything with a URL; fills gaps where no API exists.
- **Cons:** brittle (HTML changes break parsers); legal/ToS risk (CanLII bulk scraping is *prohibited and litigated* — see FAQ); rate-limiting/blocking; noisy extraction; high maintenance.

#### ✅ Decision — LOCKED (2026-09-29): adopt Option A, starting with a federal-first MVP

We are moving forward with **Option A (official bulk data & APIs first)**. The initial "minimum viable" corpus is **three fully-specced, free, open sources**, all providing *codified law* with no ingestion blockers:

| Source | Jurisdiction | What we get | Access | Format | Auth | Rate limit |
|---|---|---|---|---|---|---|
| **govinfo** (GPO) | US federal | US Code + CFR | Bulk download (`/bulkdata`) + `api.govinfo.gov` | USLM **XML** | api.data.gov key (bulk needs none) | api.data.gov standard (~1,000 req/hr, **confirmed**) |
| **Justice Laws** (Dept. of Justice Canada) | Canada federal | All consolidated Acts + regulations (EN/FR) | Bulk XML via GitHub clone / FTP (point-in-time) | **XML** (~300 MB) | None | None |
| **BC Laws** (CiviX API) | British Columbia | BC statutes + regulations | REST API (Content / Document / Search) | **XML** | None apparent | Not published — throttle politely |

**How we read them (tech):** stream-download the bulk XML (`httpx` / `git clone`) and parse with `lxml`; for BC, `httpx` GET the Content endpoint to list documents and the Document endpoint to fetch each, then parse with `lxml`. All three are **pre-ingested** — no live external calls at query time. Existing dependencies (`httpx`, `requests`, `lxml`, stdlib `zipfile`) already cover this.

**Why these three:** each is authoritative, machine-readable, free, and legally clean (US federal is public domain; Justice Laws and BC Laws are under the Open Government Licence). Acquisition is fast — the full Canadian federal XML is ~300 MB (seconds to a few minutes to download); parsing structured XML is minutes. Query-time latency (~1.5–3.5 s, LLM-dominated) is unaffected by the source choice.

**Explicitly deferred (out of MVP scope):**
- **US state codified statutes** — no clean pan-state source; each state publishes differently and needs a per-state adapter, added one state at a time later.
- **Open States / Plural** — evaluated and **excluded from the corpus**: its API (`/jurisdictions`, `/people`, `/bills`, `/committees`, `/events`) exposes *legislative activity* (bills, sponsors, events), **not codified statutes**, so it does not serve the "what law applies" feature. It may return later for a separate "track pending legislation" feature.
- **US case law** — available via CourtListener **bulk downloads** (its REST API is capped at 50 req/hr, too slow for ingest); deferred to a later tier.
- **Canadian case law** — remains a gap; CanLII prohibits bulk access, so this needs per-court official feeds or a licence, not scraping.
- **Other Canadian provinces / territories** — added per-province after BC, coverage permitting.

---

### Decision 2 — Source registry & how we discover new sources

**Why / how it's used:** Directly answers your "constant list of links vs. an AI finding links" question. For a legal product, provenance and authority are non-negotiable — we must know, per jurisdiction × category, exactly which authoritative source each document came from, and how that list grows without drifting to unofficial sites.

**Option A — Curated official-source registry, human-approved (AI only assists) _(Recommended)_**
A versioned registry (a Postgres table) mapping `jurisdiction × category × source → endpoint + adapter + licence + fetch-state`. New sources can be *proposed* by an AI/crawler, but only within **already-approved official domains**, and a human approves before anything goes live.
- **Pros:** authoritative and auditable; no risk of pulling from wrong/unofficial sources; the set is finite and knowable (~63 jurisdictions × a few official publishers); stable; supports per-source licence tracking.
- **Cons:** manual onboarding per source; slower expansion; needs a review process.

**Option B — AI-discovered links as the backbone (auto-add sources)**
- **Pros:** scales discovery fast; low human effort; can surface sources you didn't know about.
- **Cons:** hallucinated/incorrect URLs; may pull from unofficial or copyright-restricted sites → legal-accuracy and ToS risk; no authority guarantee; hard to audit. Dangerous as the *primary* mechanism for a legal product.

**Option C — Hybrid, no human gate (AI proposes and auto-promotes)**
- **Pros:** faster than fully manual; broader reach.
- **Cons:** removes the accuracy safeguard that makes Option A safe; same authority/audit risks as B, just slower to surface.

#### ✅ Decision — DECIDED (2026-09-29): hybrid registry + AI-suggested links + human approval (lightweight)

We will combine a **curated official-source registry** with **AI-discovered candidate links**, gated by a **human approval** step before anything is ingested. Because this pipeline runs infrequently, the implementation stays lightweight — a simple registry (a small config file or table) plus a manual approve step, not a heavy review workflow. This keeps Option A's core safeguard (a human confirms every source) while giving AI a genuine role in *proposing* new links, not merely assisting within pre-approved domains.

---

### Decision 3 — Handling broken / stale sources

**Why / how it's used:** You asked "if links don't work we can remove them." How we treat failures decides whether coverage silently rots. In a legal tool, invisible gaps are worse than visible errors.

**Option A — Flag-for-review + retry/backoff; keep last-good content _(Recommended)_**
On repeated failures, mark the source `degraded`/`stale`, keep the last successfully-fetched version, and raise an alert for human review.
- **Pros:** no silent coverage loss; full audit trail; tolerates temporary outages and site restructures; the user is never served a jurisdiction that quietly went empty.
- **Cons:** requires a monitoring/alerting path and someone to triage.

**Option B — Silent auto-removal of dead links**
- **Pros:** self-cleaning; zero maintenance.
- **Cons:** a 404 is often a temporary outage or a moved page, not a dead source; silent removal invisibly degrades legal completeness with no record — unacceptable for this product.

#### ✅ Decision — DECIDED (2026-09-29): Option A (flag-for-review + backoff)

On repeated failures we flag the source for review and keep the last-good content rather than silently dropping it.

---

### Decision 4 — Where we store raw source documents

**Why / how it's used:** Even with API/bulk ingestion, we must keep the *original* authoritative document for citations, provenance, and re-processing. Where these live affects cost and pipeline design.

**Option A — Object storage for originals; derived text/vectors in the serving layer _(Recommended)_**
Originals (XML/HTML/PDF) go to S3 / Cloudflare R2 / GCS, keyed by `source + version + content-hash`. The queryable layer holds only parsed, normalized, chunked text + embeddings + metadata.
- **Pros:** cheap at scale; decouples archive from serving; lets us re-chunk/re-embed without re-fetching; versioned provenance; keeps originals out of the hot path.
- **Cons:** one more infra component; needs a lifecycle/versioning policy.

**Option B — Store files in a server folder (or the repo)**
- **Pros:** dead simple; no external dependency; fine for a POC.
- **Cons:** doesn't scale; no versioning/dedup; bloats backups; couples storage to one host. (This is the "folder on a server" idea — good enough to start, not to grow into.)

#### ✅ Decision — DECIDED (2026-09-29): Option B (store originals in the repo)

To avoid paying for cloud object storage, originals live in the repo (e.g. under `data/raw/`). ⚠️ **Caveat to watch:** GitHub enforces a **100 MB hard limit per file** and gets unwieldy past ~1 GB per repo; the Canada federal XML alone is ~300 MB and the US Code XML is ~1 GB+, so if any single file approaches 100 MB or the repo balloons, move those paths to **Git LFS** — or `.gitignore` the raw bulk, keep a fetch script, and commit only the parsed/chunked text. Fine for the MVP as long as we watch file sizes.

---

### Decision 5 — Vector + metadata database

**Why / how it's used:** Multi-jurisdiction + category + currency means retrieval must combine semantic search with **strict metadata filters** over potentially millions of chunks. Current ChromaDB won't filter richly or scale for this.

**Option A — Postgres + pgvector (one store for vectors *and* relational metadata) _(Recommended)_**
- **Pros:** unified store → strict SQL filtering (jurisdiction, category, in-force, dates) alongside ANN search; transactional; mature ops/backup; we need Postgres anyway for the source registry and job state; cost-effective.
- **Cons:** pgvector ANN is not as specialized as dedicated engines at extreme scale; needs index tuning (HNSW).

**Option B — Dedicated vector DB (Qdrant / Weaviate / Milvus)**
- **Pros:** purpose-built ANN performance; rich payload filtering; scales to very large corpora.
- **Cons:** a second datastore to run and sync alongside a relational metadata store; more ops; metadata duplication.

**Option C — Keep ChromaDB**
- **Pros:** zero migration; already integrated; fine for POC.
- **Cons:** embedded/local; weak concurrency and horizontal scale; limited filtering; not production-grade at this scale.

> Keep a thin storage abstraction so we can move A → B later without touching business logic.

#### ✅ Decision — DECIDED (2026-09-29): Option C (keep ChromaDB for now)

Keep the existing local ChromaDB. At MVP scale (US federal + Canada federal + BC) it is sufficient, and it pairs with the local-first, no-cloud choices in Decisions 4 and 6. We retain a thin storage abstraction so we can migrate to Postgres + pgvector (Option A) later without rewriting business logic.

---

### Decision 6 — Update / refresh strategy

> ❌ **REMOVED from scope (2026-09-29).** The MVP has **no automated refresh** — the corpus is ingested once and only re-ingested manually / on-demand if we choose to. The incremental-delta and tiered-cadence machinery is therefore out of scope until we decide we need updates. (The decision number is kept as a stable identifier so later references don't shift; revisit if/when refresh is added.)

---

### Decision 7 — Jurisdiction scoping & isolation

**Why / how it's used:** The core feature: pick a province/state (and category) and get only the law that applies there. A Wisconsin statute must **never** surface for an Ontario query.

**Option A — Hard metadata filter at query time _(Recommended)_**
Jurisdiction is a required, indexed field, modeled as `country → region (province/state) → level (federal / provincial / state / municipal)`. Retrieval filters on it before/along with ANN. A query in a region returns that region **plus** the co-applicable federal layer, clearly labeled.
- **Pros:** correctness guarantee (no cross-jurisdiction leakage); efficient (smaller candidate set); maps cleanly to the UX selector.
- **Cons:** requires complete, clean jurisdiction tagging at ingestion; must explicitly model federal-plus-regional overlap.

**Option B — Soft ranking (jurisdiction as a ranking signal, not a filter)**
- **Pros:** simpler; tolerant of missing tags.
- **Cons:** cross-jurisdiction leakage → wrong legal answers. Unacceptable for this product.

#### ✅ Decision — DECIDED (2026-09-29): Option A (hard metadata filter)

Jurisdiction is a required, indexed field; retrieval filters on it so a region's query returns only that region's law plus the co-applicable federal layer. No cross-jurisdiction leakage.

---

### Decision 8 — Category-of-law taxonomy & classification

**Why / how it's used:** Users will choose categories of law. Categories differ across the US and Canada, so we need one consistent, filterable scheme mapped from each source's native categories.

**Option A — Controlled cross-jurisdiction taxonomy + hybrid classification _(Recommended)_**
A fixed vocabulary (e.g. criminal, traffic/motor-vehicle, family, property, employment/labour, tax, administrative, …), multi-label. Classify using source/structural signals + rules first, LLM-assisted for ambiguous cases, stored as metadata.
- **Pros:** consistent UX across all jurisdictions; filterable; explainable; source-native categories map into the shared vocabulary.
- **Cons:** taxonomy design + mapping effort; some documents span multiple categories (hence multi-label).

**Option B — Use each source's native categories as-is**
- **Pros:** no mapping effort; matches the source exactly.
- **Cons:** inconsistent across 60+ jurisdictions; poor cross-jurisdiction UX; can't filter uniformly.

**Option C — Pure-LLM classification with no fixed taxonomy**
- **Pros:** flexible; minimal upfront design.
- **Cons:** inconsistent, non-deterministic labels; hard to audit; ongoing LLM cost.

#### ✅ Decision — DECIDED (2026-09-29): Option A (controlled taxonomy + hybrid classification)

A fixed, multi-label category vocabulary, populated by rules / structural signals first and LLM-assisted for ambiguous cases, stored as filterable metadata.

---

### Decision 9 — Currency & versioning (point-in-time)

**Why / how it's used:** Legal answers must reflect the law **in force**. Amended/repealed provisions must be marked, and ideally we can answer "as of" a date. This is a correctness and liability issue, not a nicety.

**Option A — Point-in-time versioning with in-force/repealed status + effective dates _(Recommended)_**
Effective/repeal dates and in-force status are first-class metadata; default to current in-force, retain history. Sources like Justice Laws' point-in-time XML and govinfo support this directly.
- **Pros:** accurate answers; supports "as of a date"; auditable; can show what changed.
- **Cons:** more storage and schema complexity; must track dates per provision.

**Option B — Latest-only (store current version, overwrite on update)**
- **Pros:** simplest; smallest storage.
- **Cons:** no history; can't answer "as of"; risky if an update is wrong; can't surface repealed-vs-current distinctions.

#### ✅ Decision — DECIDED (2026-09-29): Option B (latest-only, for now)

Store only the current version of each provision and overwrite on any re-ingest. This pairs with the no-refresh choice (Decision 6): a simple snapshot of current law. ⚠️ **Known tradeoff:** we cannot answer "as of a date" or distinguish repealed-vs-current text — acceptable for the MVP; revisit if the product needs historical / point-in-time accuracy.

---

### Decision 10 — Embedding cost strategy at scale

**Why / how it's used:** Embedding 60+ jurisdictions of law through a paid API on every refresh is a major recurring cost. This decision controls that spend.

**Option A — Content-hash embedding cache + batching; provider swappable _(Recommended)_**
Embed a chunk only when its content hash changes (pairs with Decision 6); batch requests; keep the embedding provider behind an interface; plan an optional self-hosted open model (e.g. BGE/E5) as volume grows.
- **Pros:** only pays to embed what changed (large savings); batching cuts cost/latency; self-hosting removes per-token cost at scale; avoids lock-in.
- **Cons:** self-hosting adds GPU/infra ops; changing embedding model forces a re-embed; abstraction layer effort.

**Option B — Naive per-run API embedding (re-embed corpus each refresh)**
- **Pros:** simplest; no caching logic.
- **Cons:** cost scales with corpus × refresh frequency → expensive fast; mostly redundant work.

> Keep `text-embedding-3-small` for the POC, but add the hash-cache immediately; evaluate self-hosting once the corpus is large.

#### ✅ Decision — DECIDED (2026-09-29): Option A (content-hash cache + batching, swappable)

Embed via batched calls, cache by content hash so unchanged chunks are never re-embedded, and keep the embedding provider behind an interface. Keep `text-embedding-3-small` for now. (With no scheduled refresh, the cache mainly saves cost on manual re-ingests.)

---

### Decision 11 — Ingestion orchestration

**Why / how it's used:** Continuous multi-source updates need reliable scheduling, retries, and state — not an ad-hoc script. This decides how the pipeline is run and observed.

**Option A — Decoupled ingestion service with a scheduler/queue + state DB _(Recommended)_**
Pipeline: `registry → fetch(delta) → parse → normalize → classify → chunk → embed(cache) → upsert`. Start simple (cron + a job/state table), graduate to Temporal/Airflow if needed. Runs separately from the serving API.
- **Pros:** reliable, observable, retryable, idempotent; ingestion load never touches query latency; scales per source.
- **Cons:** more infra than a script; needs monitoring.

**Option B — Cron script writing into a folder on the app server**
- **Pros:** trivial to start; fine for a POC.
- **Cons:** no retries/observability/state; couples ingestion to the app host; fragile across 60+ sources. (This is the "folder refreshed on a server" idea — a fine seed, not the destination.)

#### ✅ Decision — DECIDED (2026-09-29): Option A (decoupled ingestion pipeline)

Run ingestion as a decoupled pipeline (`registry → fetch → parse → normalize → classify → chunk → embed → upsert`), separate from the serving API. For the MVP this is its simplest form — a runnable ingest script / CLI, not a full scheduler — consistent with running infrequently.

---

### Decision 12 — Compliance & licensing posture

**Why / how it's used:** Legal data carries real ToS and copyright constraints; getting this wrong risks litigation (CanLII is actively enforcing against bulk scraping). This sets the rule everything else must obey.

**Option A — Official-source-first, licence-aware, respect robots.txt/ToS/rate limits _(Recommended)_**
Track each source's licence in the registry; never bulk-scrape prohibited sources (e.g. CanLII).
- **Pros:** legally safe; sustainable; authoritative; full audit trail.
- **Cons:** coverage gaps where only restricted aggregators exist (especially Canadian case law) → may require per-court official feeds or a commercial licence rather than scraping.

**Option B — Scrape whatever is reachable**
- **Pros:** maximum coverage, fast.
- **Cons:** legal/ToS/copyright liability; blocking; reputational and legal risk. Unacceptable.

#### ⚠️ Decision — DECIDED (2026-09-29): Option B (scrape reachable sources) — with a hard exception

Chosen posture: we may scrape reachable sources to fill coverage. ⚠️ **This carries real legal / ToS risk and partially conflicts with Decision 1 (official-source-first).** Non-negotiable exception: **never bulk-scrape CanLII** — it explicitly prohibits this and is actively litigating it (see FAQ). Guardrails we should keep even under Option B: respect `robots.txt`, throttle politely, and prefer an official source whenever one exists. **Flagged for reconsideration** — Option A (official-first) remains the safer long-term posture.

---

## 3. Proposed Future Infrastructure

Two planes: a **serving plane** (what customers touch) and an **ingestion plane** (how we pull from official sources). They share the datastores but scale and fail independently.

### 3a. Serving / query path — what the customer does

```
┌──────────────┐
│   Customer   │  Officer / legal user (web or mobile)
└──────┬───────┘
       │ 1. Selects Country ▸ Province/State ▸ Category(s), then asks a question
       ▼
┌────────────────────────┐
│   Frontend (Next.js)   │
└──────┬─────────────────┘
       │ 2. POST /api/chat { message, jurisdiction, categories }
       ▼
┌──────────────────────────────────────────────────────────────────┐
│                    Backend API  (FastAPI)                          │
│                                                                    │
│  ┌───────────────┐   ┌─────────────────────┐   ┌───────────────┐  │
│  │ Query enhance │─► │ Retrieval           │─► │ LLM generate  │  │
│  │ + classify    │   │ (hybrid + HARD      │   │ + citations   │  │
│  └───────────────┘   │  jurisdiction/cat.  │   └──────┬────────┘  │
│                      │  metadata filter)   │          │           │
│                      └─────────┬───────────┘          │           │
└─────────┬──────────────────────┼──────────────────────┼───────────┘
          │ 3. embed query        │ 4. ANN + filter       │ 5. LLM call
          ▼                       ▼                       ▼
 ┌──────────────────┐  ┌────────────────────────────┐  ┌──────────────┐
 │ Embedding svc    │  │ Postgres + pgvector         │  │ LLM provider │
 │ (API or          │  │ chunks + metadata:          │  │ (swappable)  │
 │  self-hosted)    │  │ jurisdiction, category,     │  └──────────────┘
 └──────────────────┘  │ in-force, effective dates   │
                       └──────────────┬──────────────┘
                                      │ 6. resolve citation → original doc
                                      ▼
                            ┌────────────────────┐
                            │ Object storage     │
                            │ (original sources) │
                            └────────────────────┘
```

### 3b. Ingestion / data pipeline — how we call the official APIs

```
┌────────────────────────────────────────────────────────────────────────┐
│              Ingestion Service  (scheduled, decoupled from serving)      │
│                                                                          │
│  ┌────────────────┐   pick sources that are "due" (tiered cadence)       │
│  │ Source Registry│──────────────────┐                                   │
│  │ (Postgres):    │                  ▼                                   │
│  │ jurisdiction × │        ┌────────────────────┐                        │
│  │ category ×     │        │ Scheduler / Queue  │                        │
│  │ source +       │        └─────────┬──────────┘                        │
│  │ adapter +      │                  │  delta fetch (ETag / content-hash) │
│  │ licence +      │      ┌───────────┼─────────────┬──────────────┐      │
│  │ fetch-state    │      ▼           ▼             ▼              ▼      │
│  └────────────────┘  ┌─────────┐ ┌─────────┐ ┌──────────┐  ┌─────────┐  │
│   Per-jurisdiction   │ Adapter │ │ Adapter │ │ Adapter  │  │  ...    │  │
│   adapters call ────►│ US fed  │ │ CA fed  │ │ US states│  │         │  │
│   official sources   └────┬────┘ └────┬────┘ └────┬─────┘  └────┬────┘  │
└───────────────────────────┼───────────┼───────────┼─────────────┼───────┘
                            ▼           ▼           ▼             ▼
              ┌───────────────────────────────────────────────────────────┐
              │        External official sources (APIs / bulk XML)         │
              │  • govinfo — US Code, CFR, Public Laws (USLM XML)          │
              │  • CourtListener / Caselaw Access Project — US case law    │
              │  • Open States / Plural — US state legislation             │
              │  • Justice Laws — Canadian federal Acts & regs (bulk XML)  │
              │  • BC Laws API, Ontario e-Laws, other provinces …          │
              └───────────────────────────┬───────────────────────────────┘
                                          │ raw documents
                                          ▼
   parse ─► normalize ─► classify (category) ─► chunk ─► embed (hash-cached)
                    │                                          │
                    ▼ store originals                          ▼ upsert vectors + metadata
          ┌────────────────────┐                   ┌────────────────────────────┐
          │ Object storage     │                   │ Postgres + pgvector         │
          └────────────────────┘                   └────────────────────────────┘
```

---

## Build Roadmap & Stages

The decisions above are delivered in verifiable stages. Status as of 2026-09-29.

| Stage | Scope | Decisions | Status |
|-------|-------|-----------|--------|
| 1. Domain foundation | Jurisdiction taxonomy, category taxonomy + classifier, source registry | D2, D3, D7, D8 | ✅ Done |
| 2. Environment | Modernize dependencies for Python 3.14 | — | ✅ Done |
| 3. Retrieval filtering | Chunk metadata, jurisdiction/category filters, hard jurisdiction isolation | D7, D8 | ✅ Done |
| 4. Source adapters | `govinfo` (US fed), `justice_laws` (CA fed), `bc_laws` (BC) → tagged Documents | D1, D12 | ✅ Done |
| 5. Ingestion CLI | Decoupled download → parse → classify → chunk → embed(cache) → upsert; in-repo storage; latest-only | D4, D9, D10, D11 | ⏳ Pending |
| **6. UI / UX** | **Jurisdiction + category selection and scoped results in the frontend (see below)** | **D7, D8** | ⏳ **Pending** |
| 7. End-to-end verification | Download → embed → index MVP corpus, verify a jurisdiction-scoped chat answer | — | ⏳ Pending (needs `OPENAI_API_KEY`) |

### Stage 6 — UI / UX (detail)

The frontend must let a user pick where they are and what they're asking about, then make the applied scope obvious in the answer.

- **Jurisdiction selector:** Country → Province/State (MVP: US federal, Canada federal, British Columbia). A sub-national choice makes clear that the co-applicable federal layer is included (Decision 7).
- **Category selector:** multi-select from the controlled vocabulary (Decision 8); optional (no selection = all categories).
- **Wiring:** send `jurisdiction` + `categories` on the existing `POST /api/chat` contract (already supported by the backend).
- **Scope transparency:** show the active scope (e.g. "British Columbia + Canada federal · Criminal, Traffic") above the answer, and group the sources panel by jurisdiction so it's clear which layer each citation came from.
- **UX quality:** responsive (mobile-first), keyboard-accessible selectors, sensible defaults, and a clear empty/loading state.
- **Workflow:** per `agents.md`, this stage runs ui-designer → frontend-developer → test-writer before review.

---

## 4. Conclusion

> _Placeholder — to be filled in once the decisions above are finalized. This section will summarize, in one or two sentences each, the decision we landed on for items 1–12 (acquisition method, source registry, dead-link handling, storage, database, refresh, jurisdiction isolation, taxonomy, versioning, embedding cost, orchestration, compliance)._

---

## 5. FAQ — Where we get our data (with links)

**Q: Where do we get US federal statutes and regulations?**
GovInfo (GPO) publishes the US Code, Statute Compilations, Public Laws, and the CFR as machine-readable **USLM XML** (a derivative of the Akoma Ntoso / LegalDocML standard), via search, bulk download, and an API. US government works are public domain.
- [GovInfo Bulk Data repository](https://www.govinfo.gov/bulkdata)
- [USLM XML schema — readme](https://www.govinfo.gov/bulkdata/PLAW/resources/readme.html)
- [Statute Compilations in USLM XML (feature page)](https://www.govinfo.gov/features/statute-compilations-uslm-xml)

**Q: Where do we get US case law?**
The **Free Law Project's CourtListener** offers a REST API and bulk data across thousands of jurisdictions, integrated with Harvard's **Caselaw Access Project**. As of May 2026, full API access is included with a CourtListener membership.
- [CourtListener bulk legal data (FLP wiki)](https://wiki.free.law/c/courtlistener/help/api/bulk-data/bulk-legal-data)
- [Full API access now included with membership (2026-05-07)](https://free.law/2026/05/07/api-included-in-memberships/)
- [Caselaw Access Project API & bulk service (Harvard Law)](https://hls.harvard.edu/today/caselaw-access-project-launches-api-and-bulk-data-service/)

**Q: Where do we get US state legislation?**
**Open States** (now under Plural) aggregates legislative data for all 50 states, DC, and Puerto Rico, available via API v3 and bulk download (API key required). Note this is primarily legislative activity/bills; fully **codified state statutes** are published unevenly per state and may need per-state adapters.
- [Open States / Plural bulk data portal](https://open.pluralpolicy.com/data/)
- [Open States documentation](https://docs.openstates.org/)
- [Open States API v3 overview](https://docs.openstates.org/api-v3/)

**Q: Where do we get Canadian federal statutes and regulations?**
The **Justice Laws Website** publishes all consolidated federal Acts and regulations as bilingual **bulk XML** (standard, web, and point-in-time variants), updated roughly every two weeks, and mirrored on GitHub and the Open Government Portal.
- [Justice Laws XML index](https://laws-lois.justice.gc.ca/eng/XML/index.html)
- [justicecanada/laws-lois-xml on GitHub](https://github.com/justicecanada/laws-lois-xml)
- [Consolidated federal Acts & regulations — Bulk XML (Open Canada)](https://open.canada.ca/data/en/dataset/ff56de85-f8b9-4719-8dff-ecf362adf0af)

**Q: Where do we get Canadian provincial/territorial legislation?**
Per-province, and coverage varies. British Columbia offers a strong open **BC Laws API** (CiviX server, raw XML, open licence). Ontario publishes through e-Laws and its open data catalogue. Other provinces run their own King's Printer sites with uneven programmatic access.
- [BC Laws API](https://www.bclaws.gov.bc.ca/bclawsapi.html)
- [BC CiviX API docs](https://www.bclaws.gov.bc.ca/civix/template/complete/api/index.html)
- [Ontario open data catalogue](https://data.ontario.ca/)
- [Georgetown Law — Canadian provincial statutes guide](https://guides.ll.georgetown.edu/CanadianLegalResearch/provincial-statutes)

**Q: Can we bulk-download Canadian case law from CanLII?**
**No.** CanLII's Terms of Use expressly prohibit bulk downloading and web scraping, and CanLII has actively enforced this (a Notice of Claim was filed in Nov 2024 against an AI company for alleged violations). CanLII's official API is read-only and provides **metadata only**, not bulk document content, and requires an approved key. Canadian case law is our hardest coverage gap — plan for per-court official feeds and/or a commercial licence rather than scraping.
- [CanLII Terms of Use](https://www.canlii.org/info/terms.html)
- [CanLII API documentation](https://github.com/canlii/API_documentation/blob/master/EN.md)
- [On the legality of AI data scraping in Canada (Torkin Manes)](https://www.torkin.com/insights/publication/legality-of-data-scraping-using-ai-revisiting-in-canada)

**Q: What formats will we be parsing?**
Mostly **USLM XML** (US federal), **Justice Laws XML** (Canadian federal), and **JSON** from REST APIs (CourtListener, Open States, BC Laws). HTML scraping and PDF parsing are fallbacks only, used where no structured source exists.

**Q: Does commercial use change any of this?**
Yes — verify per source before launch. Open States/Plural, CourtListener membership, and the Caselaw Access Project each have their own licensing/terms, and CanLII restricts commercial bulk use most tightly. This is the main open input feeding Decisions 1, 2, and 12.
