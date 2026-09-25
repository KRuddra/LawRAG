# Wisconsin Law Enforcement Legal Chat RAG System

A proof-of-concept Retrieval-Augmented Generation (RAG) system that enables Wisconsin law enforcement officers to quickly query state statutes, case law, and department policies through a conversational interface.

## Project Structure

```
codefourrag/
├── backend/          # FastAPI backend application
├── frontend/         # Next.js frontend application
├── data/            # Documents and embeddings
├── documentation/   # Project documentation
└── scripts/         # Utility scripts
```

## Setup Instructions

### Prerequisites

- Python 3.10+
- Node.js 18+ (for frontend)
- npm or yarn

### Backend Setup

1. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Copy environment variables:
```bash
cp .env.example .env
# Edit .env and add your API keys
```

4. Run the backend:
```bash
cd backend
uvicorn main:app --reload
```

The API will be available at `http://localhost:8000`

### Frontend Setup

1. Navigate to frontend directory:
```bash
cd frontend
```

2. Install dependencies:
```bash
npm install
```

3. Run the development server:
```bash
npm run dev
```

The frontend will be available at `http://localhost:3000`

## Development Workflow

This project was built incrementally, one component at a time. Each component was implemented and tested independently before moving on to the next.

## API Documentation

Once the backend is running, visit:
- API Docs: `http://localhost:8000/docs`
- Alternative Docs: `http://localhost:8000/redoc`

## Testing

Run backend tests:
```bash
cd backend
pytest
```

## Data Directory

Place your Wisconsin legal documents in the following directories:

- `data/raw/statutes/` - State statutes (PDF/HTML)
- `data/raw/case_law/` - Case law summaries (PDF)
- `data/raw/policies/` - Department policies (DOCX/PDF)
- `data/raw/training/` - Training materials

You can organize files within subdirectories as needed. The system will recursively scan all subdirectories within `data/raw/`.

### Supported File Formats

- **PDF** (`.pdf`) - Uses pdfplumber
- **Word Documents** (`.docx`, `.doc`) - Uses python-docx
- **HTML** (`.html`, `.htm`) - Uses BeautifulSoup4
- **Text Files** (`.txt`, `.md`) - Plain text parsing

## Document Ingestion

### Using the API Endpoint

Once the backend is running, you can ingest documents by calling the `/api/ingest` endpoint:

```bash
# Ingest all documents from data/raw/
curl -X POST "http://localhost:8000/api/ingest"

# Or use the interactive API docs at http://localhost:8000/docs
```

The ingestion process will:
1. Recursively scan `data/raw/` and all subdirectories
2. Parse supported file formats (PDF, DOCX, HTML, TXT)
3. Normalize text (remove headers/footers, preserve section markers)
4. Extract metadata (title, jurisdiction, dates, statute numbers, department)
5. Return a list of normalized Document objects

**Note**: This step does NOT chunk or index documents yet. That will be handled in subsequent steps.

### Response Format

The `/api/ingest` endpoint returns:
- `status`: "success", "partial", or "failed"
- `documents_processed`: Number of successfully processed documents
- `documents_failed`: Number of documents that failed to process
- `total_documents`: Total number of documents found
- `documents`: List of Document objects with text and metadata
- `failures`: List of failed files with error messages
- `processing_time_seconds`: Time taken to process

### Example

```json
{
  "status": "success",
  "documents_processed": 5,
  "documents_failed": 0,
  "total_documents": 5,
  "documents": [
    {
      "text": "Normalized document text...",
      "metadata": {
        "title": "Wisconsin Statute 940.01",
        "jurisdiction": "WI",
        "document_type": "statute",
        "statute_numbers": ["940.01"],
        "dates": ["2023"],
        "source_path": "data/raw/statutes/940.01.pdf"
      },
      "source_path": "data/raw/statutes/940.01.pdf"
    }
  ],
  "failures": [],
  "processing_time_seconds": 2.34
}
```

## Performance Evaluation

To evaluate system performance (retrieval accuracy, response time, relevance scoring):

```bash
# Make sure backend is running first
python scripts/evaluate_performance.py
```

This will generate performance metrics and save results to `performance_results.json`.

See `documentation/PERFORMANCE_METRICS.md` for detailed methodology and expected results.

## Documentation

All project documentation lives in the `documentation/` folder:

- **README.md**: Quick start guide and setup instructions (this file, at the repo root)
- **documentation/EXPLANATION.md**: Complete implementation details and technical documentation
- **documentation/ARCHITECTURE.md**: System architecture, design decisions, scalability, and security
- **documentation/PERFORMANCE_METRICS.md**: Performance evaluation methodology and metrics
- **documentation/PIPELINE_UPGRADE_DECISIONS.md**: Architecture decision record for the multi-jurisdiction pipeline upgrade

## License

This is a personal project.

