"""
Hybrid search implementation: semantic + keyword (BM25) + exact match detection.
Combines vector similarity search with keyword matching for optimal retrieval.
"""

import logging
import re
from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict

try:
    from rank_bm25 import BM25Okapi
except ImportError:
    BM25Okapi = None
    logging.warning("rank_bm25 not available, BM25 search will be disabled. Install with: pip install rank-bm25")

from backend.retrieval.vector_store import VectorStore, get_vector_store, ScoredChunk
from backend.retrieval.relevance import apply_relevance_boosts
from backend.retrieval.query_enhancer import enhance_query
from backend.api.models import Chunk

logger = logging.getLogger(__name__)


# Pattern detection for statute numbers and case citations
STATUTE_PATTERNS = [
    r'§\s*(\d+\.\d+(?:\([0-9a-zA-Z]+\))*)',  # § 940.01, § 939.50(3)(a)
    r'(?:Section|section|Sec\.|sec\.)\s+(\d+\.\d+(?:\([0-9a-zA-Z]+\))*)',  # Section 940.01
    r'(?:Wis\.?\s*Stat\.?|W\.S\.A\.?)\s*(\d+\.\d+(?:\([0-9a-zA-Z]+\))*)',  # Wis. Stat. 940.01
]

CASE_CITATION_PATTERNS = [
    r'([A-Z][a-z]+\s+v\.?\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',  # State v. Smith
    r'([A-Z][a-z]+\s+v\.?\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*),\s*(\d{4})',  # State v. Smith, 2023
]


def detect_exact_patterns(query: str) -> Tuple[List[str], List[str]]:
    """
    Detect exact statute numbers and case citations in query.
    
    Args:
        query: Search query string
        
    Returns:
        Tuple of (statute_numbers, case_citations)
    """
    statute_numbers = []
    case_citations = []
    
    for pattern in STATUTE_PATTERNS:
        matches = re.findall(pattern, query, re.IGNORECASE)
        statute_numbers.extend(matches)
    
    for pattern in CASE_CITATION_PATTERNS:
        matches = re.findall(pattern, query)
        for match in matches:
            if isinstance(match, tuple):
                case_citations.append(match[0])
            else:
                case_citations.append(match)
    
    # Remove duplicates while preserving order
    statute_numbers = list(dict.fromkeys(statute_numbers))
    case_citations = list(dict.fromkeys(case_citations))
    
    return statute_numbers, case_citations


def normalize_text_for_bm25(text: str) -> List[str]:
    """
    Normalize text for BM25 indexing (simple tokenization).
    
    Args:
        text: Text to normalize
        
    Returns:
        List of tokens
    """
    # Simple tokenization: split on whitespace and punctuation
    # Convert to lowercase and remove empty strings
    tokens = re.findall(r'\b\w+\b', text.lower())
    return tokens


class BM25Index:
    """
    In-memory BM25 index for keyword search.
    Maintains a cache of indexed chunks for fast retrieval.
    """
    
    def __init__(self):
        self.chunks: List[Chunk] = []
        self.tokenized_docs: List[List[str]] = []
        self.bm25: Optional[BM25Okapi] = None
        self.chunk_id_to_index: Dict[str, int] = {}
        self.is_initialized = False
    
    def index_chunks(self, chunks: List[Chunk]):
        """
        Index chunks for BM25 search.
        
        Args:
            chunks: List of chunks to index
        """
        if not BM25Okapi:
            logger.warning("BM25Okapi not available, skipping keyword indexing")
            return
        
        self.chunks = chunks
        self.tokenized_docs = []
        self.chunk_id_to_index = {}
        
        for idx, chunk in enumerate(chunks):
            # Combine chunk text with metadata for better matching
            searchable_text = f"{chunk.text} {chunk.title} {chunk.hierarchy_path}"
            if chunk.statute_number:
                searchable_text += f" {chunk.statute_number}"
            if chunk.case_citation:
                searchable_text += f" {chunk.case_citation}"
            
            tokens = normalize_text_for_bm25(searchable_text)
            self.tokenized_docs.append(tokens)
            self.chunk_id_to_index[chunk.chunk_id] = idx
        
        if self.tokenized_docs:
            self.bm25 = BM25Okapi(self.tokenized_docs)
            self.is_initialized = True
            logger.info(f"BM25 index initialized with {len(chunks)} chunks")
        else:
            logger.warning("No documents to index for BM25")
    
    def search(self, query: str, top_k: int = 20) -> List[Tuple[Chunk, float]]:
        """
        Search using BM25 keyword matching.
        
        Args:
            query: Search query
            top_k: Number of results to return
            
        Returns:
            List of (chunk, score) tuples sorted by score descending
        """
        if not self.is_initialized or not self.bm25:
            return []
        
        query_tokens = normalize_text_for_bm25(query)
        if not query_tokens:
            return []
        
        # Get BM25 scores
        scores = self.bm25.get_scores(query_tokens)
        
        # Create list of (index, score) tuples
        indexed_scores = [(i, score) for i, score in enumerate(scores)]
        
        # Sort by score descending
        indexed_scores.sort(key=lambda x: x[1], reverse=True)
        
        # Return top_k results
        results = []
        for idx, score in indexed_scores[:top_k]:
            if score > 0:  # Only return chunks with positive scores
                results.append((self.chunks[idx], score))
        
        return results


# Global BM25 index cache
_bm25_index: Optional[BM25Index] = None


def get_bm25_index(vector_store: Optional[VectorStore] = None, force_reload: bool = False) -> BM25Index:
    """
    Get or create the global BM25 index.
    If index doesn't exist, loads all chunks from vector store.
    
    Args:
        vector_store: Optional vector store instance (uses global if not provided)
        force_reload: If True, reload the index even if it exists
        
    Returns:
        BM25Index instance
    """
    global _bm25_index
    
    if _bm25_index is None or not _bm25_index.is_initialized or force_reload:
        logger.info("Initializing BM25 index from vector store...")
        if vector_store is None:
            vector_store = get_vector_store()
        
        # Get all chunks from vector store
        # Note: This is a simple approach - in production, you might want to
        # cache this differently or load incrementally
        try:
            # Get all chunks directly from vector store
            all_chunks = vector_store.get_all_chunks()
            
            if not all_chunks:
                logger.warning("No chunks in vector store, creating empty BM25 index")
                _bm25_index = BM25Index()
                return _bm25_index
            
            # Create and initialize BM25 index
            _bm25_index = BM25Index()
            _bm25_index.index_chunks(all_chunks)
            
            logger.info(f"BM25 index loaded with {len(all_chunks)} chunks")
            
        except Exception as e:
            logger.error(f"Error initializing BM25 index: {e}")
            _bm25_index = BM25Index()  # Create empty index as fallback
    
    return _bm25_index


def enforce_jurisdiction_scope(
    results: List[ScoredChunk], allowed_ids: Optional[List[str]]
) -> List[ScoredChunk]:
    """Hard jurisdiction isolation (Decision 7).

    Drop any result whose ``jurisdiction_id`` is not in ``allowed_ids``. This
    closes the leak path where BM25 keyword hits could surface chunks from
    other jurisdictions that never went through the semantic ``where`` filter.
    When ``allowed_ids`` is falsy, results pass through unchanged.
    """
    if not allowed_ids:
        return results
    allowed = set(allowed_ids)
    return [r for r in results if r.chunk.jurisdiction_id in allowed]


def hybrid_search(
    query: str,
    filters: Optional[Dict[str, Any]] = None,
    top_k: int = 10,
    semantic_weight: float = 0.65,
    bm25_weight: float = 0.35,
    exact_match_bonus: float = 0.2,
    vector_store: Optional[VectorStore] = None,
    bm25_index: Optional[BM25Index] = None,
    use_query_enhancement: bool = True,
    enhanced_variant_weight: float = 0.5
) -> List[ScoredChunk]:
    """
    Perform hybrid search combining semantic, keyword, and exact match methods.
    
    Steps:
    1. Enhance query (abbreviations, synonyms, spell correction) - optional
    2. Detect exact statute/case patterns in query
    3. Run semantic retrieval from Chroma (topK=20) on primary query + enhanced variants
    4. Run keyword/BM25 retrieval (topK=20) on primary query + enhanced variants
    5. Merge with weighted scores: semantic * weight + bm25 * weight + exact_match_bonus
    6. Apply relevance boosts (jurisdiction, date, department)
    
    Args:
        query: Search query string
        filters: Metadata filters for semantic search
        top_k: Final number of results to return
        semantic_weight: Weight for semantic search scores (default 0.65)
        bm25_weight: Weight for BM25 search scores (default 0.35)
        exact_match_bonus: Bonus score for exact statute/case matches (default 0.2)
        vector_store: Optional vector store instance (uses global if not provided)
        bm25_index: Optional BM25 index instance (creates if not provided)
        use_query_enhancement: Whether to use query enhancement (default True)
        enhanced_variant_weight: Weight for enhanced variant results (default 0.5, lower than primary)
        
    Returns:
        List of ScoredChunk objects sorted by final relevance score
    """
    if vector_store is None:
        vector_store = get_vector_store()
    
    if bm25_index is None:
        bm25_index = get_bm25_index(vector_store)
    
    # Step 0: Enhance query if enabled
    enhanced = None
    query_variants = [query]
    
    if use_query_enhancement:
        enhanced = enhance_query(query)
        query_variants = enhanced.get_all_queries()
        if len(query_variants) > 1:
            logger.info(f"Query enhancement: original + {len(query_variants)-1} variants")
    
    # Step 1: Detect exact patterns (use original query)
    statute_numbers, case_citations = detect_exact_patterns(query)
    
    if statute_numbers:
        logger.info(f"Detected statute numbers in query: {statute_numbers}")
    if case_citations:
        logger.info(f"Detected case citations in query: {case_citations}")
    
    # Step 2: Run semantic retrieval on primary query + enhanced variants
    all_semantic_chunks = {}
    all_semantic_scores = {}
    
    for i, query_variant in enumerate(query_variants):
        variant_weight = 1.0 if i == 0 else enhanced_variant_weight
        
        semantic_results = vector_store.semantic_query(
            query_text=query_variant,
            filters=filters,
            top_k=20
        )
        
        # Store results with variant weight
        for result in semantic_results:
            chunk_id = result.chunk.chunk_id
            # Convert distance to similarity, then apply variant weight
            similarity = 1.0 / (1.0 + result.score) * variant_weight
            
            if chunk_id not in all_semantic_scores:
                all_semantic_chunks[chunk_id] = result.chunk
                all_semantic_scores[chunk_id] = similarity
            else:
                # Take max score across variants
                all_semantic_scores[chunk_id] = max(all_semantic_scores[chunk_id], similarity)
    
    # Convert back to ScoredChunk list
    semantic_results = [ScoredChunk(chunk=all_semantic_chunks[chunk_id], score=score) 
                       for chunk_id, score in all_semantic_scores.items()]
    
    # Step 3: Run BM25 keyword retrieval on primary query + enhanced variants
    all_bm25_results = []
    all_bm25_scores = {}
    
    for i, query_variant in enumerate(query_variants):
        variant_weight = 1.0 if i == 0 else enhanced_variant_weight
        
        bm25_results = bm25_index.search(query_variant, top_k=20)
        
        # Store results with variant weight
        for chunk, score in bm25_results:
            chunk_id = chunk.chunk_id
            normalized_score = score * variant_weight  # Normalization happens later
            
            if chunk_id not in all_bm25_scores:
                all_bm25_results.append((chunk, normalized_score))
                all_bm25_scores[chunk_id] = normalized_score
            else:
                # Take max score across variants
                all_bm25_scores[chunk_id] = max(all_bm25_scores[chunk_id], normalized_score)
    
    bm25_results = all_bm25_results
    
    # Step 4: Normalize and merge scores
    # Semantic scores are already normalized and weighted from query variants
    semantic_scores = {}
    for result in semantic_results:
        semantic_scores[result.chunk.chunk_id] = result.score
    
    # Normalize BM25 scores (BM25 scores can vary widely, normalize to 0-1)
    bm25_max_score = max([score for _, score in bm25_results], default=1.0)
    bm25_scores = {}
    for chunk, score in bm25_results:
        normalized_score = score / bm25_max_score if bm25_max_score > 0 else 0.0
        bm25_scores[chunk.chunk_id] = normalized_score
    
    # Merge scores for chunks that appear in both results
    all_chunk_ids = set(semantic_scores.keys()) | set(bm25_scores.keys())
    
    merged_scores = {}
    chunk_map = {}  # chunk_id -> Chunk
    
    for chunk_id in all_chunk_ids:
        semantic_score = semantic_scores.get(chunk_id, 0.0)
        bm25_score = bm25_scores.get(chunk_id, 0.0)
        
        # Weighted combination
        combined_score = (semantic_score * semantic_weight) + (bm25_score * bm25_weight)
        
        # Exact match bonus
        # Get the chunk to check for exact matches
        chunk = None
        if chunk_id in semantic_scores:
            for result in semantic_results:
                if result.chunk.chunk_id == chunk_id:
                    chunk = result.chunk
                    break
        if not chunk and chunk_id in bm25_scores:
            for c, _ in bm25_results:
                if c.chunk_id == chunk_id:
                    chunk = c
                    break
        
        if chunk:
            chunk_map[chunk_id] = chunk
            
            # Check for exact statute number match
            if chunk.statute_number and statute_numbers:
                if any(stat_num in chunk.statute_number or chunk.statute_number in stat_num 
                       for stat_num in statute_numbers):
                    combined_score += exact_match_bonus
                    logger.debug(f"Exact statute match bonus for {chunk.statute_number}")
            
            # Check for exact case citation match
            if chunk.case_citation and case_citations:
                if any(case_cit.lower() in chunk.case_citation.lower() or 
                       chunk.case_citation.lower() in case_cit.lower()
                       for case_cit in case_citations):
                    combined_score += exact_match_bonus
                    logger.debug(f"Exact case citation match bonus for {chunk.case_citation}")
        
        merged_scores[chunk_id] = combined_score
    
    # Step 5: Apply relevance boosts and create ScoredChunk objects
    final_results = []
    for chunk_id, base_score in merged_scores.items():
        chunk = chunk_map.get(chunk_id)
        if not chunk:
            continue
        
        # Apply relevance boosts
        adjusted_score, reasons = apply_relevance_boosts(chunk, base_score, filters)
        
        # Create ScoredChunk
        scored_chunk = ScoredChunk(chunk=chunk, score=adjusted_score)
        
        # Store boost reasons in chunk metadata if available (for debugging)
        # Note: ScoredChunk doesn't have a reasons field, but we can log it
        if reasons:
            logger.debug(f"Score adjustments for chunk {chunk_id}: {', '.join(reasons)}")
        
        final_results.append(scored_chunk)
    
    # Sort by score descending
    final_results.sort(key=lambda x: x.score, reverse=True)

    # Hard jurisdiction isolation (Decision 7): enforce scope on the merged
    # results so BM25 keyword matches cannot leak other jurisdictions.
    if filters and filters.get("jurisdiction_id"):
        allowed = filters["jurisdiction_id"]
        if not isinstance(allowed, (list, tuple, set)):
            allowed = [allowed]
        final_results = enforce_jurisdiction_scope(final_results, list(allowed))

    # Return top_k
    return final_results[:top_k]
