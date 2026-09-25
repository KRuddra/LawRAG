# Pipeline Upgrade — Architecture Decision Record

**Status:** Draft — decisions proposed, pending sign-off
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
4. [Conclusion](#4-conclusion)
5. [FAQ — Where we get our data (with links)](#5-faq--where-we-get-our-data-with-links)

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

| # | Decision | Recommended option |
|---|----------|--------------------|
| 1 | How we acquire data | Official bulk data & APIs first (per-jurisdiction adapters) |
| 2 | Source discovery | Curated official-source registry (human-approved; AI only assists) |
| 3 | Broken/stale sources | Flag-for-review + backoff (never silent delete) |
| 4 | Raw document storage | Object storage for originals; derived text/vectors in serving layer |
| 5 | Vector + metadata DB | Postgres + pgvector |
| 6 | Refresh strategy | Incremental delta + tiered cadence |
| 7 | Jurisdiction isolation | Hard metadata filter at query time |
| 8 | Category taxonomy | Controlled cross-jurisdiction vocabulary + hybrid classification |
| 9 | Currency/versioning | Point-in-time with in-force/repealed status |
| 10 | Embedding cost | Content-hash cache + batching; provider swappable |
| 11 | Orchestration | Decoupled ingestion service + scheduler + state DB |
| 12 | Compliance | Official-source-first, licence-aware, respect ToS |

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

---

### Decision 6 — Update / refresh strategy

**Why / how it's used:** Directly addresses "constant refresh." Law changes at very different rates (statutes: slow; case law: daily). Re-fetching and re-embedding everything on a timer is wasteful and expensive.

**Option A — Incremental delta updates + tiered cadence _(Recommended)_**
Use HTTP conditional requests (ETag/Last-Modified) and content hashing to fetch only what changed; re-embed only changed chunks; schedule per source type (e.g. statutes every ~2 weeks to match Justice Laws' cycle, case law daily).
- **Pros:** minimal bandwidth/compute/embedding cost; fast; scales; matches each source's real publish cadence; gentle on sources (ToS-friendly).
- **Cons:** needs per-source change detection and fetch-state tracking; more adapter logic.

**Option B — Constant full refresh (re-fetch & re-embed everything on a fixed timer)**
- **Pros:** simple; guarantees freshness; no diff logic.
- **Cons:** expensive (embedding + bandwidth) and slow at scale; hammers sources (rate-limit/ToS risk); almost all of the work is redundant.

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
