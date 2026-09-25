# Wisconsin Law Enforcement Legal Chat RAG System - Complete Explanation

This document consolidates all implementation details, architecture, and development information for the Wisconsin Law Enforcement Legal Chat RAG System.

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [Architecture & Design](#architecture--design)
3. [Implementation Details](#implementation-details)
4. [Frontend Integration](#frontend-integration)
5. [Setup & Development](#setup--development)

---

## Project Overview

A proof-of-concept Retrieval-Augmented Generation (RAG) system that enables Wisconsin law enforcement officers to quickly query state statutes, case law, and department policies through a conversational interface.

### Core Capabilities

1. **Data Ingestion**: Multi-format support (PDF, HTML, DOCX) for statutes, case law, policies, and training materials
2. **Intelligent Chunking**: Preserves legal context, handles hierarchical structures, maintains metadata
3. **Vector Database**: ChromaDB with legal-domain optimized embeddings
4. **Hybrid Search**: Semantic + keyword matching with relevance scoring
5. **Context Management**: Handles cross-references and citation chains
6. **Query Enhancement**: Legal synonym expansion, abbreviation handling, spell correction
7. **Response Generation**: LLM-powered with mandatory source citations
8. **Safety & Accuracy**: Confidence scoring, flags, disclaimers, use-of-force caution
9. **Chat Interface**: Next.js frontend with sources panel and confidence display
10. **Officer Features**: Quick action buttons, export functionality, mobile responsive

---

## Architecture & Design

### System Architecture

```
┌─────────────┐
│   Frontend  │  Next.js 14 + TypeScript + Tailwind CSS
│  (Next.js)  │
└──────┬──────┘
       │ HTTP/REST
       │
┌──────▼──────────────────────────────────────┐
│          FastAPI Backend                    │
├─────────────────────────────────────────────┤
│  ┌────────────┐  ┌────────────┐            │
│  │  /ingest   │  │   /chat    │            │
│  └────────────┘  └────────────┘            │
│                                             │
│  ┌──────────────────────────────────────┐  │
│  │  Ingestion Pipeline                  │  │
│  │  - Parsers (PDF, DOCX, HTML, TXT)    │  │
│  │  - Normalizer                        │  │
│  │  - Metadata Extractor                │  │
│  │  - Chunking Strategy                 │  │
│  └──────────────────────────────────────┘  │
│                                             │
│  ┌──────────────────────────────────────┐  │
│  │  Retrieval System                    │  │
│  │  - Vector Store (ChromaDB)           │  │
│  │  - Hybrid Search                     │  │
│  │  - Query Enhancement                 │  │
│  │  - Cross-reference Resolution        │  │
│  │  - Context Management                │  │
│  └──────────────────────────────────────┘  │
│                                             │
│  ┌──────────────────────────────────────┐  │
│  │  Generation & Safety                 │  │
│  │  - LLM Client (OpenAI)               │  │
│  │  - Response Formatter                │  │
│  │  - Confidence Scoring                │  │
│  │  - Flag Generation                   │  │
│  └──────────────────────────────────────┘  │
└─────────────────────────────────────────────┘
       │
       │
┌──────▼──────────────────────────────────────┐
│          Data Layer                         │
│  - ChromaDB (Vector Store)                  │
│  - Document Storage (data/raw/)             │
└─────────────────────────────────────────────┘
```

### Technology Stack

**Backend:**
- Python 3.10+
- FastAPI (web framework)
- ChromaDB (vector database)
- OpenAI API (embeddings: text-embedding-3-small, LLM: gpt-3.5-turbo)
- Pydantic (data validation)
- pdfplumber, python-docx, BeautifulSoup4 (document parsing)

**Frontend:**
- Next.js 14 (App Router)
- TypeScript
- React 18
- Tailwind CSS
- Dark theme by default

---

## Implementation Details

### 1. Data Ingestion Pipeline

**Location:** `backend/ingestion/`

#### Parsers (`parsers.py`)
- `parse_pdf(path)` - Uses pdfplumber for PDF text extraction
- `parse_docx(path)` - Uses python-docx, includes table handling
- `parse_html(path_or_url)` - Uses BeautifulSoup4 for HTML parsing
- `parse_text(path)` - Plain text with encoding fallback (UTF-8 → latin-1 → cp1252)
- `parse_file(path)` - Auto-detects file type and routes to appropriate parser

#### Normalizer (`normalizer.py`)
- `normalize_whitespace(text)` - Collapses multiple spaces, normalizes line breaks
- `remove_repeated_headers_footers(text, threshold=3)` - Frequency-based removal
- `preserve_section_markers(text)` - Ensures "§ 940.01" formatting consistency
- `normalize_text(text)` - Main function applying all normalization steps

#### Metadata Extractor (`metadata.py`)
Extracts:
- Title (from HTML `<title>` or first non-empty line)
- Jurisdiction (defaults to "WI", detects "US" for federal)
- Dates (regex patterns for various date formats)
- Department (from path: `.../policies/<dept>/...`)
- Statute numbers (patterns like "§ 940.01", "Section 940.01")
- Case citations ("State v. Smith" patterns)
- Document type (statute, case_law, policy, training)

#### API Endpoint: `/api/ingest`
- Recursively scans `data/raw/**`
- Parses, normalizes, extracts metadata
- Returns `IngestResponse` with counts and failures
- Optional `reindex` parameter to also chunk, embed, and index

---

### 2. Document Chunking Strategy

**Location:** `backend/ingestion/chunking.py`

#### Chunk Model
- `chunk_id`: Unique hash-based identifier
- `doc_id`: Source document identifier
- `doc_type`: statute, case_law, policy, training
- `text`: Chunk content (~1200 tokens target)
- `hierarchy_path`: "Chapter 940 > Section 940.01 > Subsection (1)"
- `statute_number`: Extracted statute number
- `case_citation`: Case citation if applicable
- Metadata fields: date, jurisdiction, title, source_uri

#### Chunking Heuristics

**Statutes:**
- Splits at section boundaries: `§ 940.01`, `Section 940.01`
- Handles subsections: `939.50(3)(a)`, `(1)`, `(2)(a)`
- Subchunks to ~1200 tokens with overlap if needed
- Preserves hierarchy in `hierarchy_path`

**Case Law:**
- Splits at section headings: FACTS, HOLDING, REASONING, ANALYSIS
- Captures "State v. Smith" patterns
- Extracts case citations and statute references
- Creates hierarchy based on section headings

**Policies/Training:**
- Splits at numbered headings: `1.0`, `2.1.3`, `3.2.1(a)`
- Splits at ALL CAPS headings
- Subchunks with overlap when needed

#### Size Management
- Target: ~1200 tokens per chunk
- Overlap: ~100 tokens between chunks
- Prefers sentence boundaries when subchunking

---

### 3. Vector Database Setup

**Location:** `backend/retrieval/vector_store.py`

#### ChromaDB Configuration
- Persistent storage: `data/embeddings/`
- Embedding model: `text-embedding-3-small` (OpenAI)
- Collection name: "legal_documents"
- Metadata filtering: doc_type, jurisdiction, date, statute_number, case_citation, department, is_current

#### Operations
- `upsert_chunks(chunks)` - Adds/updates chunks with embeddings
- `semantic_query(query_text, filters, top_k)` - Vector similarity search
- `get_all_chunks()` - Retrieves all chunks for BM25 indexing
- `get_collection_stats()` - Returns chunk count
- `reset_collection()` - Deletes and recreates collection

#### Indexing Flow
1. Parse documents → normalize → extract metadata
2. Chunk documents
3. Generate embeddings for each chunk
4. Store in ChromaDB with metadata

---

### 4. Hybrid Search Implementation

**Location:** `backend/retrieval/hybrid_search.py`

#### Components

**Exact Pattern Detection:**
- Detects statute numbers: `§ 939.50(3)(a)`, `940.01`
- Detects case citations: `State v. Smith, 2023 WI 45`
- Provides exact match bonus in scoring

**Semantic Search:**
- Uses ChromaDB vector similarity
- TopK=20 results
- Weight: 0.65

**BM25 Keyword Search:**
- In-memory BM25 index (rank-bm25)
- Tokenizes and searches keywords
- TopK=20 results
- Weight: 0.35

**Score Merging:**
```
final_score = (semantic_score * 0.65) + (bm25_score * 0.35) + exact_match_bonus
```

**Relevance Boosts** (`relevance.py`):
- WI jurisdiction: +0.05
- Current documents (`is_current=true` or recent dates): +0.03
- Department policy matches: +0.05
- Non-WI jurisdiction: -0.03
- Outdated documents: -0.05

---

### 5. Context Window Management

**Location:** `backend/retrieval/context.py` and `crossref.py`

#### Cross-Reference Resolution

**Detection** (`crossref.py`):
- Regex patterns: "see also § ...", "see § ...", "refer to § ..."
- Extracts statute numbers from references

**Resolution:**
- Queries vector store with statute number metadata filter
- Max depth: 1 (no recursive following)
- Max refs: 5 per context
- Avoids duplicates

#### Context Building (`context.py`)

**ContextPacket Model:**
- `sources`: Ordered list of `ContextSource` objects
- `total_tokens`: Token count tracking
- Provides stable `source_id`s for citations

**Build Process:**
1. Select top-ranked chunks from hybrid search
2. Apply budget constraints (max chunks, max tokens)
3. Enforce diversity (include statute + case + policy if available)
4. Expand cross-references (if enabled)
5. Build `ContextPacket` with ordered sources

**Budget Management:**
- Default: max 10 chunks or 4000 tokens
- Prioritizes higher-scored chunks
- Ensures diversity across document types

---

### 6. Query Enhancement

**Location:** `backend/retrieval/query_enhancer.py`

#### Features

**Abbreviation Expansion** (`utils/abbreviations.py`):
- OWI ↔ DUI
- Law enforcement abbreviations database
- Multi-word abbreviation support

**Synonym Expansion** (`utils/legal_terms.py`):
- Terry stop ↔ investigatory detention
- Legal term synonyms database

**Light Spell Correction:**
- Only for known legal terms
- Avoids overcorrecting statute numbers
- Preserves "§ 939.50(3)(a)" formatting

**Statute Number Protection:**
- Replaces statute numbers with placeholders before processing
- Restores original formatting after enhancement

#### Integration
- Enhanced queries used in hybrid search with lower weight
- Primary query: full weight
- Enhanced variants: 0.7x weight
- Results merged and deduplicated

---

### 7. Response Generation

**Location:** `backend/generation/`

#### LLM Client (`llm_client.py`)
- OpenAI API integration
- Model: `gpt-3.5-turbo` (configurable)
- Temperature: 0.0 (deterministic)
- System prompt: Legal assistant guidelines

#### Prompts (`prompts.py`)

**System Prompt:**
- Legal information assistant role
- Answer only from context
- Write in clean paragraph format (no JSON, no citation markers)
- Include statute numbers and case citations naturally
- State if information is insufficient

**User Prompt:**
- Includes user query
- Includes context documents
- Instructions for clean paragraph format

#### Response Formatter (`formatter.py`)

**Process:**
1. Parse LLM response (handles JSON if present, extracts clean text)
2. Remove citation markers `[Source src_XXX]` from answer
3. Clean JSON artifacts
4. Extract cited source IDs
5. Build `SourceDocument` list from context packet
6. Always include top 3 closest matches by score
7. Format as `ChatResponse` with clean answer, sources, confidence, flags

**Answer Text Formatting:**
- Clean paragraph (no JSON, no brackets, no citation markers)
- Proper capitalization and punctuation
- Natural, flowing text

---

### 8. Safety & Accuracy Features

**Location:** `backend/generation/safety.py`

#### Confidence Scoring

**Base Confidence:** 0.4 (allows more variation)

**Boost Factors:**
- Exact match: +0.35
- Top score > 0.9: +0.25
- Top score > 0.8: +0.2
- Top score > 0.7: +0.15
- Top score > 0.6: +0.1
- Top score > 0.5: +0.05
- Top score < 0.4: -0.15
- Top score < 0.3: -0.25
- 5+ sources: +0.15
- 3+ sources: +0.1
- 2+ sources: +0.05
- 3+ citations: +0.1
- 2+ citations: +0.05
- 1 citation: +0.02
- Very consistent scores (variance < 0.05): +0.08
- Consistent scores (variance < 0.1): +0.05
- Inconsistent scores (variance > 0.5): -0.1

**Confidence Range:**
- 90-100%: Excellent match with exact citations
- 70-89%: Good match with strong sources
- 50-69%: Moderate match
- 30-49%: Low confidence
- 10-29%: Very low confidence
- 10%: No sources found

#### Flags

**LOW_CONFIDENCE:**
- Triggered when confidence < 0.5
- Warns user about reliability

**OUTDATED_POSSIBLE:**
- Triggered when sources have old dates or unknown currency
- Notes potential staleness

**JURISDICTION_NOTE:**
- Triggered when query implies WI but sources are federal
- Alerts user to jurisdiction mismatch

**USE_OF_FORCE_CAUTION:**
- Triggered when use-of-force keywords detected
- Requires explicit policy/statute in sources
- If insufficient sources, returns caution message instead of answer
- Special handling in response generation

#### Disclaimers
- Every response includes: "⚠️ DISCLAIMER: This information is for informational purposes only and does not constitute legal advice."
- Use-of-force queries include additional caution message

---

## Frontend Integration

**Location:** `frontend/`

### Architecture

Next.js 14 App Router with TypeScript, using client components for interactivity.

### Components

**ChatInterface** (`components/ChatInterface.tsx`):
- Main chat container
- Displays messages, sources, confidence, flags
- Integrates InputDock and ExportButton

**MessageBubble** (`components/MessageBubble.tsx`):
- Renders user and AI messages
- Separates answer, confidence, citations, flags, disclaimers into sections
- Clean paragraph format for answers

**SourceCard** (`components/SourceCard.tsx`):
- Displays source metadata
- Shows statute numbers, case citations
- Highlights search terms
- Shows relevance score

**QuickActions** (`components/QuickActions.tsx`):
- 6 demo query buttons:
  1. OWI 3rd offense elements
  2. Vehicle search during traffic stop
  3. Misdemeanor theft statute of limitations
  4. Recent Terry stop cases
  5. Department pursuit policy
  6. Miranda warnings for juveniles

**ConfidenceBadge** (`components/ConfidenceBadge.tsx`):
- Color-coded confidence display
- Green (≥70%), Yellow (40-69%), Red (<40%)

**ExportButton** (`components/ExportButton.tsx`):
- Copies conversation to clipboard
- Markdown format with answer + citations
- Report-friendly formatting

**InputDock** (`components/InputDock.tsx`):
- Message input field
- Send button
- Quick actions integration
- Enter key to send

### API Integration (`lib/api.ts`)

- Base URL: `http://localhost:8000` (configurable via `NEXT_PUBLIC_API_URL`)
- `POST /api/chat` - Send chat message
- `GET /health` - Health check
- TypeScript interfaces for all requests/responses

### Styling (`app/globals.css`)

- Dark theme by default
- CSS variables for colors, fonts, spacing
- Mobile responsive design
- Sources panel collapses on small screens
- Quick actions scrollable row

### State Management (`hooks/useChat.ts`)

- Manages messages, loading state, conversation ID
- Handles API calls
- Error handling
- Conversation persistence (local state + conversation_id)

---

## Setup & Development

### Prerequisites

- Python 3.10+
- Node.js 18+
- npm or yarn

### Backend Setup

1. Create virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Create `.env` file:
```bash
cp env.example .env
# Edit .env and add your API keys:
# OPENAI_API_KEY=your_key_here
```

4. Run backend:
```bash
cd backend
uvicorn main:app --reload
```

API available at `http://localhost:8000`

### Frontend Setup

1. Navigate to frontend:
```bash
cd frontend
```

2. Install dependencies:
```bash
npm install
```

3. (Optional) Create `.env.local`:
```bash
NEXT_PUBLIC_API_URL=http://localhost:8000
```

4. Run frontend:
```bash
npm run dev
```

Frontend available at `http://localhost:3000`

### Data Directory

Place documents in:
- `data/raw/statutes/` - State statutes (PDF/HTML)
- `data/raw/case_law/` - Case law summaries (PDF)
- `data/raw/policies/` - Department policies (DOCX/PDF)
- `data/raw/training/` - Training materials

### Ingesting Documents

1. Place documents in `data/raw/` subdirectories
2. Call ingestion endpoint:
```bash
curl -X POST "http://localhost:8000/api/ingest?reindex=true"
```

Or use the interactive API docs at `http://localhost:8000/docs`

The `reindex=true` parameter will:
- Parse documents
- Normalize text
- Extract metadata
- Chunk documents
- Generate embeddings
- Index in ChromaDB

### Testing

Run backend tests:
```bash
cd backend
pytest
```

### API Documentation

Once backend is running:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

---

## Project Structure

```
codefourrag/
├── backend/                    # FastAPI backend
│   ├── api/                   # API routes and models
│   │   ├── models.py         # Pydantic models
│   │   └── routes.py         # API endpoints
│   ├── generation/           # LLM integration
│   │   ├── llm_client.py    # OpenAI client
│   │   ├── prompts.py       # System/user prompts
│   │   ├── formatter.py     # Response formatting
│   │   └── safety.py        # Confidence & flags
│   ├── ingestion/            # Document processing
│   │   ├── parsers.py       # Document parsers
│   │   ├── normalizer.py    # Text normalization
│   │   ├── metadata.py      # Metadata extraction
│   │   └── chunking.py      # Document chunking
│   ├── retrieval/            # Search & retrieval
│   │   ├── vector_store.py  # ChromaDB integration
│   │   ├── hybrid_search.py # Hybrid search
│   │   ├── query_enhancer.py # Query enhancement
│   │   ├── crossref.py      # Cross-reference resolution
│   │   ├── context.py       # Context building
│   │   └── relevance.py     # Relevance scoring
│   ├── utils/                # Utilities
│   │   ├── abbreviations.py # Abbreviation mappings
│   │   └── legal_terms.py   # Legal term synonyms
│   ├── tests/                # Test suite
│   ├── config.py            # Configuration
│   └── main.py              # FastAPI app
│
├── frontend/                  # Next.js frontend
│   ├── app/                  # Next.js app router
│   │   ├── page.tsx         # Main page
│   │   ├── layout.tsx       # Root layout
│   │   └── globals.css      # Global styles
│   ├── components/           # React components
│   │   ├── ChatInterface.tsx
│   │   ├── MessageBubble.tsx
│   │   ├── SourceCard.tsx
│   │   ├── QuickActions.tsx
│   │   ├── ConfidenceBadge.tsx
│   │   ├── ExportButton.tsx
│   │   └── ...
│   ├── lib/                  # Frontend utilities
│   │   ├── api.ts           # API client
│   │   └── types.ts         # TypeScript types
│   └── hooks/                # React hooks
│       └── useChat.ts       # Chat state management
│
├── data/                      # Data directories
│   ├── raw/                  # Input documents
│   ├── processed/            # Processed chunks (optional)
│   └── embeddings/           # ChromaDB storage
│
├── docs/                      # Documentation
│   └── ARCHITECTURE.md       # Architecture details
│
├── scripts/                   # Utility scripts
│
├── requirements.txt           # Python dependencies
├── env.example               # Environment variable template
├── README.md                 # Main README
├── EXPLANATION.md            # This file
└── .gitignore               # Git ignore rules
```

---

## Development Workflow

This project was built incrementally, one component at a time:

1. **Data Ingestion Pipeline** - Parse, normalize, extract metadata
2. **Document Chunking Strategy** - Legal-aware chunking with hierarchy
3. **Vector Database Setup** - ChromaDB indexing and embeddings
4. **Hybrid Search Implementation** - Semantic + keyword search
5. **Context Window Management** - Cross-reference expansion
6. **Query Enhancement** - Abbreviations, synonyms, spell correction
7. **Response Generation** - LLM integration with citations
8. **Safety & Accuracy Features** - Confidence scoring and flags
9. **Chat Interface** - Next.js frontend with sources panel
10. **Officer-Specific Features** - Quick actions and export

Each component was implemented and tested independently before moving on to the next.

---

## Key Design Decisions

1. **ChromaDB over Pinecone**: Local-first approach, easier for demo, no external dependencies
2. **Hybrid Search**: Combines semantic (0.65) and keyword (0.35) for best recall and precision
3. **Legal-Aware Chunking**: Preserves section boundaries, maintains hierarchy, extracts citations
4. **Clean Paragraph Format**: LLM writes natural paragraphs, not JSON, for better readability
5. **Top 3 Sources Always**: Always shows top 3 closest matches, even if not explicitly cited
6. **Confidence Variation**: Granular confidence scoring (0.4-1.0 range) based on multiple signals
7. **Use-of-Force Caution**: Special handling requiring explicit policy/statute sources
8. **Dark Theme**: Professional dark theme suitable for law enforcement use

---

## License

This is a personal project.

