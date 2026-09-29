"""
API route handlers
"""

import os
import logging
import time
from pathlib import Path
from typing import List
from fastapi import APIRouter, HTTPException, UploadFile, File
from backend.config import settings
from backend.api.models import IngestRequest, IngestResponse, Document, ChatMessage, ChatResponse
from backend.ingestion.parsers import parse_file
from backend.ingestion.normalizer import normalize_text
from backend.ingestion.metadata import extract_metadata
from backend.ingestion.chunking import chunk_document
from backend.retrieval.vector_store import get_vector_store
from backend.retrieval.hybrid_search import hybrid_search
from backend.jurisdictions import applicable_ids, UnknownJurisdictionError
from backend.categories import normalise_category
from backend.retrieval.context import build_context
from backend.generation.prompts import LEGAL_ASSISTANT_SYSTEM_PROMPT, build_user_prompt
from backend.generation.llm_client import generate
from backend.generation.formatter import format_chat_response
from backend.generation.safety import compute_confidence, generate_flags, should_allow_use_of_force_response, USE_OF_FORCE_CAUTION
from backend.config import settings

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL, logging.INFO),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/test")
async def test_endpoint():
    """Test endpoint for incremental development"""
    return {"message": "API routes module initialized"}


@router.post("/ingest", response_model=IngestResponse)
async def ingest_documents(request: IngestRequest = None):
    """
    Ingest documents from the data/raw directory.
    
    Walks through data/raw/** subdirectories, parses files,
    normalizes text, extracts metadata, and returns Document objects.
    
    Note: This endpoint does NOT chunk or index documents yet.
    That will be handled in a subsequent step.
    
    Args:
        request: Optional IngestRequest with directory and file_types filters
        
    Returns:
        IngestResponse with processed documents and failures
    """
    start_time = time.time()
    
    # Determine directory to process
    if request and request.directory:
        raw_dir = Path(request.directory)
    else:
        raw_dir = Path(settings.RAW_DATA_DIR)
    
    if not raw_dir.exists():
        logger.warning(f"Raw data directory does not exist: {raw_dir}. Creating it.")
        raw_dir.mkdir(parents=True, exist_ok=True)
        return IngestResponse(
            status="success",
            documents_processed=0,
            documents_failed=0,
            total_documents=0,
            documents=[],
            failures=[],
            processing_time_seconds=time.time() - start_time
        )
    
    logger.info(f"Starting ingestion from directory: {raw_dir}")
    
    # Collect all files to process
    supported_extensions = {'.pdf', '.docx', '.doc', '.html', '.htm', '.txt', '.md'}
    
    files_to_process = []
    for root, dirs, filenames in os.walk(raw_dir):
        for filename in filenames:
            file_path = Path(root) / filename
            extension = file_path.suffix.lower()
            
            # Filter by extension
            if extension not in supported_extensions:
                continue
            
            # Filter by file_types if specified
            if request and request.file_types:
                file_type = extension.lstrip('.')
                if file_type not in request.file_types:
                    continue
            
            files_to_process.append(file_path)
    
    # Limit to MAX_DOCS
    total_files = len(files_to_process)
    if total_files > settings.MAX_DOCS:
        logger.warning(
            f"Found {total_files} files, limiting to {settings.MAX_DOCS} "
            f"as per MAX_DOCS setting"
        )
        files_to_process = files_to_process[:settings.MAX_DOCS]
    
    logger.info(f"Found {len(files_to_process)} files to process")
    
    # Process each file
    documents: List[Document] = []
    failures: List[dict] = []
    
    for file_path in files_to_process:
        try:
            logger.debug(f"Processing file: {file_path}")
            
            # Step 1: Parse file
            text, doc_type = parse_file(str(file_path))
            
            if not text or not text.strip():
                logger.warning(f"File {file_path} produced empty text, skipping")
                failures.append({
                    "file_path": str(file_path),
                    "error": "File produced empty text after parsing"
                })
                continue
            
            # Step 2: Normalize text
            normalized_text = normalize_text(text, remove_headers_footers=True)
            
            if not normalized_text or not normalized_text.strip():
                logger.warning(f"File {file_path} produced empty text after normalization, skipping")
                failures.append({
                    "file_path": str(file_path),
                    "error": "File produced empty text after normalization"
                })
                continue
            
            # Step 3: Extract metadata
            metadata = extract_metadata(normalized_text, doc_type, str(file_path))
            
            # Step 4: Create Document object
            document = Document(
                text=normalized_text,
                metadata=metadata,
                source_path=str(file_path)
            )
            
            documents.append(document)
            logger.info(
                f"Successfully processed: {file_path} "
                f"(type: {doc_type}, title: {metadata.get('title', 'N/A')[:50]})"
            )
            
            # If reindex is requested, chunk and index
            if request and request.reindex:
                try:
                    logger.debug(f"Chunking and indexing document: {file_path}")
                    chunks = chunk_document(document)
                    logger.info(f"Created {len(chunks)} chunks from {file_path}")
                    
                    # Get vector store and upsert chunks
                    vector_store = get_vector_store()
                    chunks_indexed = vector_store.upsert_chunks(chunks)
                    logger.info(f"Indexed {chunks_indexed} chunks from {file_path}")
                except Exception as e:
                    logger.error(f"Error indexing chunks for {file_path}: {str(e)}")
                    # Don't fail the entire ingestion if indexing fails for one file
                    failures.append({
                        "file_path": str(file_path),
                        "error": f"Indexing failed: {str(e)}"
                    })
            
        except FileNotFoundError as e:
            error_msg = f"File not found: {str(e)}"
            logger.error(f"Error processing {file_path}: {error_msg}")
            failures.append({
                "file_path": str(file_path),
                "error": error_msg
            })
        except ValueError as e:
            error_msg = f"Parsing error: {str(e)}"
            logger.error(f"Error processing {file_path}: {error_msg}")
            failures.append({
                "file_path": str(file_path),
                "error": error_msg
            })
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            logger.exception(f"Unexpected error processing {file_path}: {error_msg}")
            failures.append({
                "file_path": str(file_path),
                "error": error_msg
            })
    
    # Calculate processing time
    processing_time = time.time() - start_time
    
    # Determine status
    total_processed = len(documents) + len(failures)
    if len(failures) == 0:
        status = "success"
    elif len(documents) > 0:
        status = "partial"
    else:
        status = "failed"
    
    logger.info(
        f"Ingestion completed: {len(documents)} processed, {len(failures)} failed, "
        f"in {processing_time:.2f} seconds"
    )
    
    # Get indexing summary if reindex was performed
    chunks_created = None
    if request and request.reindex:
        try:
            vector_store = get_vector_store()
            stats = vector_store.get_collection_stats()
            chunks_created = stats.get("chunk_count", 0)
            logger.info(f"Vector database now contains {chunks_created} total chunks")
        except Exception as e:
            logger.warning(f"Could not get vector store stats: {str(e)}")
    
    # Return response
    return IngestResponse(
        status=status,
        documents_processed=len(documents),
        documents_failed=len(failures),
        total_documents=total_processed,
        documents=documents,
        failures=failures,
        processing_time_seconds=round(processing_time, 2),
        chunks_created=chunks_created
    )


@router.post("/chat", response_model=ChatResponse)
async def chat(message: ChatMessage):
    """
    Chat endpoint: enhance query -> hybrid search -> context build -> LLM generate -> format response.
    
    Implements the full RAG pipeline:
    1. Enhance query (abbreviations, synonyms)
    2. Hybrid search (semantic + keyword + exact match)
    3. Build context (with cross-reference expansion, budget constraints)
    4. Generate response with LLM
    5. Format response with citations and safety flags
    
    Args:
        message: ChatMessage with user query
        
    Returns:
        ChatResponse with answer, sources, confidence, and flags
    """
    query = message.message.strip()
    
    if not query:
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    
    try:
        logger.info(f"Processing chat query: {query[:100]}")

        # Step 0: Build jurisdiction/category scope filters (Decisions 7 & 8).
        # A sub-national jurisdiction expands to include its co-applicable
        # federal layer; categories filter on the primary scalar category.
        scope_filters: dict = {}
        if message.jurisdiction:
            try:
                scope_filters["jurisdiction_id"] = applicable_ids(message.jurisdiction)
            except UnknownJurisdictionError as exc:
                raise HTTPException(status_code=400, detail=str(exc))
        if message.categories:
            categories = [
                c.value for c in (normalise_category(name) for name in message.categories)
                if c is not None
            ]
            if categories:
                scope_filters["category"] = categories

        # Step 1: Hybrid search with query enhancement, scoped to the jurisdiction
        search_results = hybrid_search(
            query=query,
            filters=scope_filters or None,
            top_k=10,
            use_query_enhancement=True
        )
        
        if not search_results:
            # No results found
            return ChatResponse(
                response="I apologize, but I could not find any relevant sources in the database to answer your question. Please try rephrasing your query or ensure relevant documents are indexed.",
                sources=[],
                confidence=0.1,
                flags=["LOW_CONFIDENCE"],
                conversation_id=message.conversation_id or "default"
            )
        
        # Step 2: Build context with cross-reference expansion
        context_packet = build_context(
            ranked_chunks=search_results,
            max_chunks=10,
            max_tokens=4000,  # Adjust based on model context window
            expand_crossrefs_flag=True,
            max_crossrefs=5,
            enforce_diversity=True
        )
        
        # Step 3: Compute confidence and generate flags
        # Extract retrieval signals
        top_score = search_results[0].score if search_results else 0.0
        scores = [r.score for r in search_results]
        score_variance = float(sum((s - sum(scores)/len(scores))**2 for s in scores) / len(scores)) if scores else 1.0
        
        # Check for exact matches
        exact_match = any(
            r.chunk.statute_number and any(
                stat_num in r.chunk.statute_number or r.chunk.statute_number in stat_num
                for stat_num in [query]
            ) for r in search_results[:3]
        )
        
        retrieval_signals = {
            "exact_match": exact_match,
            "top_score": top_score,
            "num_sources": len(context_packet.sources),
            "score_variance": score_variance
        }
        
        # Initial confidence computation (before citations)
        confidence = compute_confidence(retrieval_signals, [], context_packet)
        
        # Generate flags
        flags = generate_flags(query, context_packet, confidence, retrieval_signals)
        
        # Step 4: Handle use-of-force queries with special care
        if USE_OF_FORCE_CAUTION in flags and not should_allow_use_of_force_response(query, context_packet):
            return ChatResponse(
                response=(
                    "I cannot provide information about use-of-force procedures without explicit "
                    "supporting policy documents or statutes in the available sources. "
                    "Please consult your department's official use-of-force policy and legal counsel "
                    "for guidance on these matters.\n\n"
                    "⚠️ DISCLAIMER: This information is for informational purposes only and does not constitute legal advice.\n\n"
                    "🚨 USE OF FORCE CAUTION: This response involves use-of-force matters. Verify information with official "
                    "department policies and legal counsel before taking action."
                ),
                sources=[],
                confidence=0.1,
                flags=flags,
                conversation_id=message.conversation_id or "default"
            )
        
        # Step 5: Generate context text
        context_text = context_packet.get_context_text()
        
        # Step 6: Build prompts
        user_prompt = build_user_prompt(query, context_text)
        
        # Step 7: Generate LLM response
        llm_response = generate(
            prompt=user_prompt,
            system_prompt=LEGAL_ASSISTANT_SYSTEM_PROMPT,
            model=settings.LLM_MODEL,
            temperature=settings.LLM_TEMPERATURE,
            max_tokens=1000
        )
        
        # Step 8: Extract citations from LLM response and recompute confidence
        from backend.generation.formatter import extract_citations_from_text
        citations = extract_citations_from_text(llm_response)
        
        # Recompute confidence with citations
        final_confidence = compute_confidence(retrieval_signals, citations, context_packet)
        
        # Update flags based on final confidence
        if final_confidence < 0.5 and "LOW_CONFIDENCE" not in flags:
            flags.append("LOW_CONFIDENCE")
        
        # Step 9: Format response
        chat_response = format_chat_response(
            llm_response=llm_response,
            context_packet=context_packet,
            query=query,
            confidence=final_confidence,
            flags=flags
        )
        
        # Set conversation ID
        chat_response.conversation_id = message.conversation_id or "default"
        
        logger.info(f"Chat response generated: confidence={final_confidence:.2f}, flags={flags}, sources={len(chat_response.sources)}")
        
        return chat_response
        
    except Exception as e:
        logger.error(f"Error processing chat query: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error processing query: {str(e)}")
