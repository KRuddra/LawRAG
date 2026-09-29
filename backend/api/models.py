"""
Pydantic models for API requests and responses
"""

from pydantic import BaseModel, ConfigDict, Field
from typing import List, Optional, Dict, Any
from datetime import datetime


class ChatMessage(BaseModel):
    """Chat message request"""
    message: str
    conversation_id: Optional[str] = None
    jurisdiction: Optional[str] = Field(
        None,
        description="Jurisdiction id to scope the answer to (e.g. 'ca-bc', 'us-federal'). "
                    "Sub-national ids also include their co-applicable federal layer.",
    )
    categories: Optional[List[str]] = Field(
        None,
        description="Optional category filter (e.g. ['criminal', 'traffic']).",
    )


class SourceDocument(BaseModel):
    """Source document in response"""
    text: str
    metadata: Dict[str, Any]
    score: float


class ChatResponse(BaseModel):
    """Chat response with sources and metadata"""
    response: str
    sources: List[SourceDocument]
    confidence: float
    flags: List[str]
    conversation_id: str


class Document(BaseModel):
    """Normalized document object"""
    text: str = Field(..., description="Normalized document text content")
    metadata: Dict[str, Any] = Field(..., description="Extracted metadata")
    source_path: str = Field(..., description="Original file path")
    
    class Config:
        json_schema_extra = {
            "example": {
                "text": "Normalized document text...",
                "metadata": {
                    "title": "Wisconsin Statute 940.01",
                    "jurisdiction": "WI",
                    "document_type": "statute",
                    "statute_numbers": ["940.01"]
                },
                "source_path": "data/raw/statutes/940.01.pdf"
            }
        }


class IngestRequest(BaseModel):
    """Request for document ingestion"""
    directory: Optional[str] = Field(
        None, 
        description="Specific directory to ingest (defaults to RAW_DATA_DIR)"
    )
    file_types: Optional[List[str]] = Field(
        None,
        description="Specific file types to process (e.g., ['pdf', 'docx'])"
    )
    reindex: bool = Field(
        False,
        description="If true, chunk documents, generate embeddings, and index in vector database"
    )


class Chunk(BaseModel):
    """Document chunk with preserved legal context"""
    chunk_id: str = Field(..., description="Unique identifier for the chunk")
    doc_id: str = Field(..., description="Document identifier (source_path)")
    doc_type: str = Field(..., description="Document type: statute, case_law, policy, training")
    text: str = Field(..., description="Chunk text content")
    hierarchy_path: str = Field(..., description="Hierarchical path (e.g., 'Chapter 940 > Section 940.01 > Subsection (1)')")
    statute_number: Optional[str] = Field(None, description="Statute number if applicable (e.g., '940.01')")
    case_citation: Optional[str] = Field(None, description="Case citation if applicable (e.g., 'State v. Smith, 2023')")
    date: Optional[str] = Field(None, description="Date associated with the chunk")
    jurisdiction: str = Field(..., description="Legacy jurisdiction label (e.g., 'WI', 'US')")
    title: str = Field(..., description="Document title")
    source_uri: str = Field(..., description="Source file path/URI")

    # Multi-jurisdiction fields (Decision 7 / 8). Optional for backward
    # compatibility with existing single-jurisdiction chunks.
    jurisdiction_id: Optional[str] = Field(
        None, description="Structured jurisdiction id (e.g., 'ca-bc', 'us-federal')"
    )
    country: Optional[str] = Field(None, description="Country code (e.g., 'US', 'CA')")
    region: Optional[str] = Field(None, description="Sub-national region code (e.g., 'BC'); None for federal")
    level: Optional[str] = Field(None, description="Government level (e.g., 'federal', 'provincial')")
    category: Optional[str] = Field(
        None, description="Primary law category, used as the scalar retrieval filter (Decision 8)"
    )
    categories: List[str] = Field(
        default_factory=list, description="Full multi-label category list, for display"
    )
    source_id: Optional[str] = Field(None, description="Registry source id this chunk came from")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "chunk_id": "doc_123_chunk_0",
                "doc_id": "acts/C-46.xml",
                "doc_type": "statute",
                "text": "Every one commits an offence who...",
                "hierarchy_path": "Criminal Code > Part VIII > Section 222",
                "statute_number": "222",
                "case_citation": None,
                "date": "2023",
                "jurisdiction": "CA",
                "title": "Criminal Code",
                "source_uri": "https://laws-lois.justice.gc.ca/eng/acts/C-46/",
                "jurisdiction_id": "ca-federal",
                "country": "CA",
                "region": None,
                "level": "federal",
                "category": "criminal",
                "categories": ["criminal"],
                "source_id": "ca-justice-laws",
            }
        }
    )


class IngestResponse(BaseModel):
    """Document ingestion response"""
    status: str = Field(..., description="Ingestion status: 'success' or 'partial'")
    documents_processed: int = Field(..., description="Number of documents successfully processed")
    documents_failed: int = Field(..., description="Number of documents that failed to process")
    total_documents: int = Field(..., description="Total number of documents found")
    documents: List[Document] = Field(..., description="List of successfully processed documents")
    failures: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="List of failures with file paths and error messages"
    )
    processing_time_seconds: float = Field(..., description="Time taken to process all documents")
    chunks_created: Optional[int] = Field(
        None,
        description="Number of chunks created and indexed (only when reindex=True)"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "status": "success",
                "documents_processed": 10,
                "documents_failed": 0,
                "total_documents": 10,
                "documents": [],
                "failures": [],
                "processing_time_seconds": 2.5
            }
        }


class ContextSource(BaseModel):
    """Source in context packet for citations"""
    source_id: str = Field(..., description="Stable source identifier for citations")
    chunk_id: str = Field(..., description="Chunk identifier")
    text: str = Field(..., description="Source text content")
    title: str = Field(..., description="Document title")
    statute_number: Optional[str] = Field(None, description="Statute number if applicable")
    case_citation: Optional[str] = Field(None, description="Case citation if applicable")
    hierarchy_path: str = Field(..., description="Hierarchical path")
    doc_type: str = Field(..., description="Document type")
    jurisdiction: str = Field(..., description="Jurisdiction")
    source_uri: str = Field(..., description="Source URI")
    score: float = Field(..., description="Relevance score")
    source_type: str = Field(..., description="Source type: primary or crossref")
    tokens: int = Field(..., description="Token count for this source")


class ContextPacket(BaseModel):
    """Context packet with ordered sources for LLM generation"""
    sources: List[ContextSource] = Field(..., description="Ordered list of sources")
    total_tokens: int = Field(..., description="Total token count")
    
    class Config:
        json_schema_extra = {
            "example": {
                "sources": [],
                "total_tokens": 0
            }
        }

