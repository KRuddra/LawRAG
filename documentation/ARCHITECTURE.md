# System Architecture Document
## Wisconsin Law Enforcement Legal Chat RAG System

---

## Table of Contents

1. [System Overview](#system-overview)
2. [Architecture Diagram](#architecture-diagram)
3. [RAG Pipeline Flow](#rag-pipeline-flow)
4. [Component Design](#component-design)
5. [Design Decisions](#design-decisions)
6. [Scalability Considerations](#scalability-considerations)
7. [Security and Privacy Measures](#security-and-privacy-measures)
8. [Data Flow](#data-flow)

---

## System Overview

The Wisconsin Law Enforcement Legal Chat RAG System is a Retrieval-Augmented Generation (RAG) system designed to help law enforcement officers quickly access and understand legal information through a conversational interface. The system combines document processing, vector search, and large language models to provide accurate, cited responses to legal queries.

### Key Capabilities

- **Multi-format Document Processing**: Handles PDF, DOCX, HTML, and plain text documents
- **Intelligent Chunking**: Preserves legal context and hierarchical structures
- **Hybrid Search**: Combines semantic vector search with keyword/BM25 matching
- **Legal-Aware Features**: Statute number extraction, case citation handling, cross-reference resolution
- **Safety & Accuracy**: Confidence scoring, source verification, use-of-force caution handling
- **Responsive UI**: Dark theme, mobile-friendly interface with quick action buttons

---

## Architecture Diagram

### High-Level System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Frontend Layer                           │
│                    (Next.js 14 + TypeScript)                     │
├─────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │ ChatInterface│  │ MessageBubble│  │ SourceCard   │         │
│  │              │  │              │  │              │         │
│  │ - Input      │  │ - Display    │  │ - Metadata   │         │
│  │ - QuickActions│ │ - Confidence │  │ - Citations  │         │
│  │ - Export     │  │ - Flags      │  │ - Highlighting│        │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘         │
│         │                 │                  │                  │
│         └─────────────────┴──────────────────┘                  │
│                            │                                     │
│                   HTTP/REST API                                  │
└────────────────────────────┼─────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Backend API Layer                           │
│                         (FastAPI)                                │
├─────────────────────────────────────────────────────────────────┤
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                   API Endpoints                           │  │
│  │  POST /api/ingest  │  POST /api/chat  │  GET /health    │  │
│  └──────────────────────────────────────────────────────────┘  │
│                            │                                     │
│         ┌──────────────────┼──────────────────┐                 │
│         ▼                  ▼                  ▼                 │
└─────────────────────────────────────────────────────────────────┘
         │                  │                  │
         ▼                  ▼                  ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│  Ingestion      │ │   Retrieval     │ │   Generation    │
│  Pipeline       │ │   System        │ │   System        │
└─────────────────┘ └─────────────────┘ └─────────────────┘
```

### Detailed RAG Pipeline Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        Document Ingestion                         │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  Documents (PDF/DOCX/HTML)                                       │
│        │                                                          │
│        ▼                                                          │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐          │
│  │   Parser    │──▶│ Normalizer  │──▶│  Metadata   │          │
│  │             │   │             │   │  Extractor  │          │
│  │ - pdfplumber│   │ - Whitespace│   │ - Title     │          │
│  │ - docx      │   │ - Headers   │   │ - Statute#  │          │
│  │ - HTML      │   │ - Sections  │   │ - Case Cite │          │
│  └─────────────┘   └─────────────┘   └─────────────┘          │
│        │                                                          │
│        ▼                                                          │
│  ┌─────────────┐                                                │
│  │   Chunking  │                                                │
│  │             │                                                │
│  │ - Legal-aware│                                               │
│  │ - Hierarchy │                                                │
│  │ - ~1200 tokens│                                              │
│  └──────┬───────┘                                                │
│         │                                                         │
│         ▼                                                         │
│  ┌─────────────┐   ┌─────────────┐                             │
│  │ Embedding   │──▶│   ChromaDB  │                             │
│  │ Generation  │   │   Storage   │                             │
│  │ (OpenAI)    │   │             │                             │
│  └─────────────┘   └─────────────┘                             │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│                         Query Processing                          │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  User Query                                                      │
│     │                                                             │
│     ▼                                                             │
│  ┌─────────────┐                                                │
│  │   Query     │                                                │
│  │ Enhancement │                                                │
│  │             │                                                │
│  │ - Abbrev    │                                                │
│  │ - Synonyms  │                                                │
│  │ - Spell     │                                                │
│  └──────┬──────┘                                                │
│         │                                                         │
│         ├──────────────────┬──────────────────┐                  │
│         ▼                  ▼                  ▼                  │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐          │
│  │  Semantic   │   │    BM25     │   │   Exact     │          │
│  │   Search    │   │   Keyword   │   │   Match     │          │
│  │  (Vector)   │   │   Search    │   │ Detection   │          │
│  │             │   │             │   │             │          │
│  │ Weight: 0.65│   │ Weight: 0.35│   │ Bonus: +0.1│          │
│  └──────┬──────┘   └──────┬──────┘   └──────┬──────┘          │
│         │                  │                  │                  │
│         └──────────────────┴──────────────────┘                  │
│                          │                                        │
│                          ▼                                        │
│  ┌─────────────┐                                                │
│  │   Score     │                                                │
│  │   Merging   │                                                │
│  │             │                                                │
│  │ + Relevance │                                                │
│  │   Boosts    │                                                │
│  └──────┬──────┘                                                │
│         │                                                         │
│         ▼                                                         │
│  ┌─────────────┐                                                │
│  │   Context   │                                                │
│  │   Building  │                                                │
│  │             │                                                │
│  │ - Budget    │                                                │
│  │ - Diversity │                                                │
│  │ - Cross-ref │                                                │
│  └──────┬──────┘                                                │
│         │                                                         │
│         ▼                                                         │
│  ┌─────────────┐                                                │
│  │     LLM     │                                                │
│  │ Generation  │                                                │
│  │             │                                                │
│  │ - Prompt    │                                                │
│  │ - Context   │                                                │
│  │ - Response  │                                                │
│  └──────┬──────┘                                                │
│         │                                                         │
│         ▼                                                         │
│  ┌─────────────┐                                                │
│  │  Formatting │                                                │
│  │             │                                                │
│  │ - Citations │                                                │
│  │ - Confidence│                                                │
│  │ - Flags     │                                                │
│  └──────┬──────┘                                                │
│         │                                                         │
│         ▼                                                         │
│  Response to User                                                │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

---

## RAG Pipeline Flow

### 1. Document Ingestion Flow

```
Raw Documents
    │
    ├─▶ Parser (PDF/DOCX/HTML/TXT)
    │       │
    │       ├─▶ Extract Text
    │       └─▶ Detect Type
    │
    ├─▶ Normalizer
    │       │
    │       ├─▶ Remove Headers/Footers
    │       ├─▶ Normalize Whitespace
    │       └─▶ Preserve Section Markers
    │
    ├─▶ Metadata Extractor
    │       │
    │       ├─▶ Title
    │       ├─▶ Jurisdiction
    │       ├─▶ Statute Numbers
    │       ├─▶ Case Citations
    │       └─▶ Dates
    │
    ├─▶ Chunker
    │       │
    │       ├─▶ Detect Boundaries (sections/subsections)
    │       ├─▶ Split into ~1200 token chunks
    │       ├─▶ Preserve Hierarchy
    │       └─▶ Extract Citations
    │
    ├─▶ Embedding Generator
    │       │
    │       └─▶ OpenAI text-embedding-3-small
    │
    └─▶ Vector Store (ChromaDB)
            │
            └─▶ Store with Metadata for Filtering
```

### 2. Query Processing Flow

```
User Query
    │
    ├─▶ Query Enhancement
    │       │
    │       ├─▶ Expand Abbreviations (OWI → DUI)
    │       ├─▶ Expand Synonyms (Terry stop → investigatory detention)
    │       ├─▶ Light Spell Correction
    │       └─▶ Protect Statute Numbers
    │
    ├─▶ Hybrid Search
    │       │
    │       ├─▶ Semantic Search (Vector Similarity)
    │       │       └─▶ TopK=20, Weight=0.65
    │       │
    │       ├─▶ BM25 Keyword Search
    │       │       └─▶ TopK=20, Weight=0.35
    │       │
    │       └─▶ Exact Match Detection
    │               └─▶ Bonus for exact statute/case matches
    │
    ├─▶ Relevance Boosting
    │       │
    │       ├─▶ WI Jurisdiction (+0.05)
    │       ├─▶ Current Documents (+0.03)
    │       ├─▶ Department Policy Match (+0.05)
    │       └─▶ Penalties for outdated/non-WI (-0.03 to -0.05)
    │
    ├─▶ Context Building
    │       │
    │       ├─▶ Select Top Chunks (budget: 10 chunks, 4000 tokens)
    │       ├─▶ Enforce Diversity (statute + case + policy)
    │       └─▶ Expand Cross-References
    │               └─▶ Follow "see also §..." links (max depth 1, max 5 refs)
    │
    ├─▶ LLM Generation
    │       │
    │       ├─▶ Build Prompt (system + user + context)
    │       ├─▶ Generate Response (GPT-3.5-turbo, temp=0)
    │       └─▶ Extract Clean Answer Text
    │
    ├─▶ Response Formatting
    │       │
    │       ├─▶ Remove Citation Markers
    │       ├─▶ Build Source List (top 3 + cited)
    │       └─▶ Add Disclaimers
    │
    ├─▶ Confidence & Flags
    │       │
    │       ├─▶ Compute Confidence Score
    │       │       └─▶ Based on: exact match, top score, num sources, citations, variance
    │       └─▶ Generate Flags
    │               ├─▶ LOW_CONFIDENCE
    │               ├─▶ OUTDATED_POSSIBLE
    │               ├─▶ JURISDICTION_NOTE
    │               └─▶ USE_OF_FORCE_CAUTION
    │
    └─▶ Return Response
            │
            └─▶ Answer + Sources + Confidence + Flags
```

---

## Component Design

### Backend Components

#### 1. Ingestion Module (`backend/ingestion/`)

**Purpose**: Process and prepare documents for indexing

**Components**:
- **parsers.py**: Multi-format document parsing (PDF, DOCX, HTML, TXT)
- **normalizer.py**: Text cleaning and standardization
- **metadata.py**: Extract legal metadata (statute numbers, citations, dates)
- **chunking.py**: Legal-aware document chunking with hierarchy preservation

**Key Design Patterns**:
- Strategy pattern for different document types
- Pipeline pattern for processing steps
- Factory pattern for parser selection

#### 2. Retrieval Module (`backend/retrieval/`)

**Purpose**: Search and retrieve relevant document chunks

**Components**:
- **vector_store.py**: ChromaDB integration and vector operations
- **hybrid_search.py**: Semantic + keyword search orchestration
- **query_enhancer.py**: Query expansion and improvement
- **crossref.py**: Cross-reference detection and resolution
- **context.py**: Context window management and budget constraints
- **relevance.py**: Relevance scoring and boosting logic

**Key Design Patterns**:
- Facade pattern for vector store abstraction
- Strategy pattern for different search methods
- Chain of responsibility for query enhancement

#### 3. Generation Module (`backend/generation/`)

**Purpose**: Generate responses using LLM

**Components**:
- **llm_client.py**: OpenAI API client wrapper
- **prompts.py**: System and user prompt templates
- **formatter.py**: Response formatting and citation extraction
- **safety.py**: Confidence scoring and flag generation

**Key Design Patterns**:
- Template method for prompt building
- Builder pattern for response construction
- Strategy pattern for confidence calculation

#### 4. API Module (`backend/api/`)

**Purpose**: REST API endpoints and request/response handling

**Components**:
- **routes.py**: FastAPI route handlers
- **models.py**: Pydantic models for validation
- **middleware.py**: CORS and request middleware

**Key Design Patterns**:
- Repository pattern for data access
- DTO pattern for request/response models

### Frontend Components

#### Architecture: Next.js 14 App Router

**Structure**:
```
frontend/
├── app/              # Next.js App Router
│   ├── page.tsx     # Main chat page
│   ├── layout.tsx   # Root layout
│   └── globals.css  # Global styles
├── components/       # React components
├── lib/             # Utilities and API client
└── hooks/           # Custom React hooks
```

**Key Components**:
- **ChatInterface**: Main container component
- **MessageBubble**: Message display with sections
- **SourceCard**: Source document display
- **QuickActions**: Pre-defined query buttons
- **ConfidenceBadge**: Confidence score display
- **ExportButton**: Markdown export functionality

---

## Design Decisions

### 1. ChromaDB over Pinecone

**Decision**: Use ChromaDB for vector storage

**Rationale**:
- **Local-first**: No external dependencies during development
- **Ease of demo**: Works offline, no API keys needed for vector DB
- **Metadata filtering**: Native support for complex metadata queries
- **Cost**: No per-query costs
- **Deployment flexibility**: Can run locally or migrate to cloud later

**Trade-offs**:
- Less scalable than cloud solutions for very large datasets
- Requires local storage management

### 2. Hybrid Search Approach

**Decision**: Combine semantic (0.65) and keyword (0.35) search

**Rationale**:
- **Semantic search**: Handles natural language queries, synonyms, context
- **Keyword search**: Precise matching for statute numbers (§ 940.01), case names
- **Weighted combination**: Balances recall (semantic) with precision (keyword)
- **Exact match bonus**: Prioritizes perfect matches for statute/case queries

**Trade-offs**:
- More complex than pure semantic search
- Requires maintaining both vector and keyword indices

### 3. Legal-Aware Chunking

**Decision**: Preserve legal structure and boundaries

**Rationale**:
- **Legal accuracy**: Statutes and cases must not be split mid-clause
- **Hierarchy preservation**: Maintains chapter/section/subsection relationships
- **Citation extraction**: Enables cross-reference following
- **Context preservation**: Keeps related legal concepts together

**Trade-offs**:
- More complex than simple token-based chunking
- Requires domain knowledge in chunking logic

### 4. Clean Paragraph Format

**Decision**: LLM outputs clean paragraphs, not JSON

**Rationale**:
- **Readability**: Natural language is easier to read for officers
- **Professional appearance**: Cleaner UI presentation
- **Simpler parsing**: No complex JSON parsing needed
- **Citation separation**: Citations shown separately in UI

**Trade-offs**:
- Less structured than JSON output
- Requires more careful prompt engineering

### 5. Always Show Top 3 Sources

**Decision**: Always include top 3 closest matches, even if not cited

**Rationale**:
- **Transparency**: Users see what documents influenced the answer
- **Verification**: Officers can check multiple sources
- **Context**: Provides additional relevant information
- **Trust**: Builds confidence through source visibility

**Trade-offs**:
- May include slightly less relevant sources
- Requires more UI space

### 6. Confidence Scoring Granularity

**Decision**: Detailed confidence calculation with multiple factors

**Rationale**:
- **Accuracy**: More granular scoring provides better reliability signals
- **Variation**: Prevents all queries showing same confidence (e.g., 80%)
- **Trust**: Officers can make informed decisions based on confidence
- **Transparency**: Shows system's assessment of answer quality

**Factors Considered**:
- Exact match detection
- Top retrieval score (granular thresholds)
- Number of sources
- Citation count
- Score consistency (variance)

---

## Scalability Considerations

### Current Limitations

1. **In-Memory BM25 Index**: Loads all chunks into memory
   - **Impact**: Limited by available RAM
   - **Mitigation**: Can move to disk-based index (e.g., Elasticsearch) for large datasets

2. **ChromaDB Local Storage**: Single-node deployment
   - **Impact**: Limited by single machine's resources
   - **Mitigation**: Can migrate to ChromaDB cloud or distributed setup

3. **Sequential Processing**: Some operations are sequential
   - **Impact**: Slower for large batches
   - **Mitigation**: Can parallelize document processing and embedding generation

### Scalability Improvements

#### Horizontal Scaling

**Backend**:
- Deploy multiple FastAPI instances behind a load balancer
- Stateless API design enables easy scaling
- Use Redis for shared state if needed

**Vector Store**:
- Migrate to ChromaDB cloud or distributed ChromaDB
- Shard by document type or jurisdiction
- Use read replicas for query load

**Embedding Generation**:
- Batch embedding generation
- Use async/concurrent processing
- Cache embeddings for duplicate chunks

#### Vertical Scaling

**Optimizations**:
- Use faster embedding models (e.g., quantized models)
- Optimize chunk sizes for better performance
- Implement response caching for common queries

#### Database Optimizations

**ChromaDB**:
- Optimize collection indexing
- Use metadata filtering to reduce search space
- Implement query result caching

**BM25 Index**:
- Move to disk-based index (e.g., Elasticsearch, Meilisearch)
- Index only frequently accessed fields
- Implement incremental indexing

### Expected Performance

**Current Capacity** (estimated):
- **Documents**: ~10,000-50,000 documents comfortably
- **Chunks**: ~100,000-500,000 chunks
- **Queries**: ~100-1000 queries per minute (single instance)

**Scaled Capacity** (with optimizations):
- **Documents**: 100,000+ documents
- **Chunks**: 1,000,000+ chunks
- **Queries**: 10,000+ queries per minute (distributed)

---

## Security and Privacy Measures

### Data Security

#### 1. API Key Management

**Implementation**:
- All API keys stored in `.env` file (not in code)
- `.env` file excluded from version control (`.gitignore`)
- Environment variables loaded via Pydantic-settings
- No hardcoded credentials in codebase

**Best Practices**:
- Use separate keys for development/production
- Rotate keys regularly
- Monitor API key usage

#### 2. Input Validation

**Implementation**:
- Pydantic models for all API requests/responses
- Type validation and sanitization
- File type validation for document uploads
- Query length limits (prevent DoS)

**Protection**:
- SQL injection: Not applicable (no SQL queries)
- XSS: React automatically escapes output
- Path traversal: Validates file paths

#### 3. Document Access Control

**Implementation**:
- Documents stored locally in `data/raw/`
- No public document endpoint
- Documents only accessible through ingestion pipeline
- Source URIs don't expose full file paths in API responses

**Recommendations for Production**:
- Implement authentication/authorization
- Role-based access control (e.g., department-specific policies)
- Audit logging for document access
- Encryption at rest for sensitive documents

### Privacy Measures

#### 1. Data Minimization

**Implementation**:
- Only stores document text and metadata (no PII unless in documents)
- Chunks store only relevant text snippets
- No user query logging (unless explicitly enabled)

#### 2. Response Filtering

**Implementation**:
- Can filter by jurisdiction (state vs federal)
- Can filter by department (for department-specific queries)
- Metadata filtering prevents information leakage

#### 3. Use-of-Force Caution

**Implementation**:
- Special handling for use-of-force queries
- Requires explicit policy/statute sources
- Returns caution if insufficient sources
- Prevents uninformed responses about sensitive topics

#### 4. Disclaimers

**Implementation**:
- Every response includes legal disclaimer
- States information is for informational purposes only
- Notes it does not constitute legal advice

### Recommendations for Production

1. **Authentication & Authorization**:
   - Implement user authentication (OAuth, JWT)
   - Role-based access control
   - Department-based data filtering

2. **Audit Logging**:
   - Log all queries and responses
   - Track document access
   - Monitor for unusual patterns

3. **Data Encryption**:
   - Encrypt documents at rest
   - Use HTTPS for all API communication
   - Encrypt database/vector store

4. **Rate Limiting**:
   - Implement per-user rate limits
   - Prevent abuse and DoS attacks

5. **Data Retention**:
   - Define data retention policies
   - Implement document versioning
   - Handle document expiration

6. **Compliance**:
   - Ensure compliance with relevant regulations
   - Implement data deletion mechanisms
   - Provide data export capabilities

---

## Data Flow

### Ingestion Flow

```
1. Documents placed in data/raw/
2. POST /api/ingest called
3. For each document:
   a. Detect file type
   b. Parse text content
   c. Normalize text
   d. Extract metadata
   e. Chunk document
   f. Generate embeddings
   g. Store in ChromaDB
4. Return ingestion summary
```

### Query Flow

```
1. User submits query via frontend
2. POST /api/chat called
3. Enhance query (abbreviations, synonyms)
4. Run hybrid search:
   a. Semantic search (vector similarity)
   b. BM25 keyword search
   c. Exact match detection
5. Apply relevance boosts
6. Build context packet:
   a. Select top chunks (budget constraints)
   b. Enforce diversity
   c. Expand cross-references
7. Generate LLM response
8. Format response:
   a. Clean answer text
   b. Build source list
   c. Compute confidence
   d. Generate flags
9. Return formatted response
10. Frontend displays answer, sources, confidence, flags
```

---

## Technology Stack Summary

### Backend
- **Framework**: FastAPI (Python 3.10+)
- **Vector DB**: ChromaDB
- **Embeddings**: OpenAI text-embedding-3-small
- **LLM**: OpenAI GPT-3.5-turbo
- **Search**: rank-bm25 (keyword), ChromaDB (semantic)
- **Validation**: Pydantic
- **Document Parsing**: pdfplumber, python-docx, BeautifulSoup4

### Frontend
- **Framework**: Next.js 14 (App Router)
- **Language**: TypeScript
- **UI Library**: React 18
- **Styling**: Tailwind CSS
- **HTTP Client**: Fetch API

### Infrastructure
- **Deployment**: Can run locally or deploy to cloud
- **Database**: ChromaDB (file-based SQLite)
- **Storage**: Local file system

---

## Conclusion

This architecture provides a robust, scalable foundation for a legal information RAG system. The design prioritizes accuracy, transparency, and user trust through careful document processing, hybrid search, and safety features. The system can scale from prototype to production with appropriate infrastructure improvements.

