"""
Vector database wrapper (ChromaDB)
Handles embedding storage and retrieval with metadata filtering
"""

import logging
from typing import List, Optional, Dict, Any
import chromadb
from chromadb.config import Settings as ChromaSettings
from chromadb.utils import embedding_functions

from backend.config import settings
from backend.api.models import Chunk

logger = logging.getLogger(__name__)


class ScoredChunk:
    """Chunk with similarity score"""
    def __init__(self, chunk: Chunk, score: float):
        self.chunk = chunk
        self.score = score


def build_where_clause(filters: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Build a ChromaDB ``where`` clause from a simple filters dict.

    - ``None`` values are dropped.
    - list/tuple/set values become an ``$in`` membership test (used for
      jurisdiction scope, e.g. ``["ca-bc", "ca-federal"]``).
    - Multiple conditions are combined with ``$and``.

    Returns ``None`` when there is nothing to filter on.
    """
    if not filters:
        return None

    conditions: List[Dict[str, Any]] = []
    for key, value in filters.items():
        if value is None:
            continue
        if isinstance(value, (list, tuple, set)):
            values = [v for v in value if v is not None]
            if not values:
                continue
            conditions.append({key: {"$in": list(values)}})
        else:
            conditions.append({key: value})

    if not conditions:
        return None
    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}


class VectorStore:
    """ChromaDB vector store wrapper"""
    
    COLLECTION_NAME = "legal_documents"
    
    def __init__(self, persist_directory: Optional[str] = None):
        """
        Initialize ChromaDB client with persistent storage.
        
        Args:
            persist_directory: Directory to persist ChromaDB data (defaults to config)
        """
        self.persist_directory = persist_directory or settings.CHROMA_PERSIST_DIR
        
        # Initialize embedding function (OpenAI)
        if not settings.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is required for embeddings. Please set it in .env file.")
        
        self.embedding_function = embedding_functions.OpenAIEmbeddingFunction(
            api_key=settings.OPENAI_API_KEY,
            model_name=settings.EMBEDDING_MODEL
        )
        
        # Initialize ChromaDB client
        self.client = chromadb.PersistentClient(
            path=self.persist_directory,
            settings=ChromaSettings(
                anonymized_telemetry=False,
                allow_reset=True
            )
        )
        
        # Get or create collection
        self.collection = self.client.get_or_create_collection(
            name=self.COLLECTION_NAME,
            embedding_function=self.embedding_function,
            metadata={"hnsw:space": "cosine"}  # Use cosine similarity
        )
        
        logger.info(f"Initialized ChromaDB vector store at {self.persist_directory}")
        logger.info(f"Collection '{self.COLLECTION_NAME}' ready with {self.collection.count()} existing chunks")
    
    def upsert_chunks(self, chunks: List[Chunk]) -> int:
        """
        Upsert (insert or update) chunks into ChromaDB.
        
        Args:
            chunks: List of Chunk objects to store
            
        Returns:
            Number of chunks successfully upserted
        """
        if not chunks:
            logger.warning("No chunks provided for upsert")
            return 0
        
        try:
            # Prepare data for ChromaDB
            ids = []
            texts = []
            metadatas = []
            
            for chunk in chunks:
                # ID is the chunk_id
                ids.append(chunk.chunk_id)
                texts.append(chunk.text)
                
                # Prepare metadata for filtering
                metadata = {
                    "doc_id": chunk.doc_id,
                    "doc_type": chunk.doc_type,
                    "jurisdiction": chunk.jurisdiction,
                    "title": chunk.title,
                    "source_uri": chunk.source_uri,
                    "hierarchy_path": chunk.hierarchy_path,
                }
                
                # Add optional metadata fields if present
                if chunk.statute_number:
                    metadata["statute_number"] = chunk.statute_number
                if chunk.case_citation:
                    metadata["case_citation"] = chunk.case_citation
                if chunk.date:
                    metadata["date"] = chunk.date
                if chunk.chunk_id:  # Always include chunk_id in metadata for retrieval
                    metadata["chunk_id"] = chunk.chunk_id

                # Multi-jurisdiction metadata (Decision 7 / 8). Stored as scalars
                # because ChromaDB metadata cannot hold lists; the full category
                # list is stored as a CSV string for display only.
                if chunk.jurisdiction_id:
                    metadata["jurisdiction_id"] = chunk.jurisdiction_id
                if chunk.country:
                    metadata["country"] = chunk.country
                if chunk.region:
                    metadata["region"] = chunk.region
                if chunk.level:
                    metadata["level"] = chunk.level
                if chunk.category:
                    metadata["category"] = chunk.category
                if chunk.categories:
                    metadata["categories_csv"] = ",".join(chunk.categories)
                if chunk.source_id:
                    metadata["source_id"] = chunk.source_id
                
                # Optional fields (if present in original metadata)
                # These would come from document metadata if we extend Chunk model
                # For now, we'll set defaults
                metadata["is_current"] = "true"  # Default to current
                # department would come from document metadata if available
                
                metadatas.append(metadata)
            
            # Upsert to ChromaDB
            self.collection.upsert(
                ids=ids,
                documents=texts,
                metadatas=metadatas
            )
            
            logger.info(f"Successfully upserted {len(chunks)} chunks to ChromaDB")
            return len(chunks)
            
        except Exception as e:
            logger.error(f"Error upserting chunks to ChromaDB: {str(e)}")
            raise
    
    def semantic_query(
        self,
        query_embedding: Optional[List[float]] = None,
        query_text: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        top_k: int = 5
    ) -> List[ScoredChunk]:
        """
        Perform semantic search query.
        
        Args:
            query_embedding: Pre-computed embedding vector (optional)
            query_text: Query text to embed (required if query_embedding not provided)
            filters: Metadata filters (e.g., {"doc_type": "statute", "jurisdiction": "WI"})
            top_k: Number of results to return
            
        Returns:
            List of ScoredChunk objects sorted by relevance
        """
        if not query_embedding and not query_text:
            raise ValueError("Either query_embedding or query_text must be provided")
        
        try:
            # Build where clause for filtering (supports $in for list values,
            # e.g. jurisdiction scope ["ca-bc", "ca-federal"]).
            where_clause = build_where_clause(filters)
            
            # Perform query
            if query_text:
                # Use query_text - ChromaDB will embed it using the embedding function
                results = self.collection.query(
                    query_texts=[query_text],
                    n_results=top_k,
                    where=where_clause if where_clause else None
                )
            else:
                # Use pre-computed embedding
                results = self.collection.query(
                    query_embeddings=[query_embedding],
                    n_results=top_k,
                    where=where_clause if where_clause else None
                )
            
            # Convert results to ScoredChunk objects
            scored_chunks = []
            
            if results["ids"] and len(results["ids"][0]) > 0:
                for i in range(len(results["ids"][0])):
                    chunk_id = results["ids"][0][i]
                    metadata = results["metadatas"][0][i]
                    text = results["documents"][0][i]
                    distance = results["distances"][0][i] if "distances" in results else None
                    
                    # Convert distance to similarity score (1 - distance for cosine similarity)
                    score = 1.0 - distance if distance is not None else 1.0
                    
                    # Reconstruct Chunk object from metadata and text
                    chunk = Chunk(
                        chunk_id=chunk_id,
                        doc_id=metadata.get("doc_id", ""),
                        doc_type=metadata.get("doc_type", "unknown"),
                        text=text,
                        hierarchy_path=metadata.get("hierarchy_path", ""),
                        statute_number=metadata.get("statute_number"),
                        case_citation=metadata.get("case_citation"),
                        date=metadata.get("date"),
                        jurisdiction=metadata.get("jurisdiction", "WI"),
                        title=metadata.get("title", ""),
                        source_uri=metadata.get("source_uri", ""),
                        jurisdiction_id=metadata.get("jurisdiction_id"),
                        country=metadata.get("country"),
                        region=metadata.get("region"),
                        level=metadata.get("level"),
                        category=metadata.get("category"),
                        categories=(
                            metadata["categories_csv"].split(",")
                            if metadata.get("categories_csv") else []
                        ),
                        source_id=metadata.get("source_id"),
                    )
                    
                    scored_chunks.append(ScoredChunk(chunk=chunk, score=score))
            
            logger.debug(f"Semantic query returned {len(scored_chunks)} results")
            return scored_chunks
            
        except Exception as e:
            logger.error(f"Error performing semantic query: {str(e)}")
            raise
    
    def get_collection_stats(self) -> Dict[str, Any]:
        """Get statistics about the collection"""
        count = self.collection.count()
        return {
            "collection_name": self.COLLECTION_NAME,
            "chunk_count": count,
            "persist_directory": self.persist_directory
        }
    
    def get_all_chunks(self, limit: int = 10000) -> List[Chunk]:
        """
        Get all chunks from the collection (for BM25 indexing).
        
        Args:
            limit: Maximum number of chunks to retrieve
            
        Returns:
            List of Chunk objects
        """
        try:
            # ChromaDB's get() method with limit
            results = self.collection.get(limit=limit)
            
            chunks = []
            if results and results.get("ids"):
                for i in range(len(results["ids"])):
                    chunk_id = results["ids"][i]
                    metadata = results["metadatas"][i] if results.get("metadatas") else {}
                    text = results["documents"][i] if results.get("documents") else ""
                    
                    chunk = Chunk(
                        chunk_id=chunk_id,
                        doc_id=metadata.get("doc_id", ""),
                        doc_type=metadata.get("doc_type", "unknown"),
                        text=text,
                        hierarchy_path=metadata.get("hierarchy_path", ""),
                        statute_number=metadata.get("statute_number"),
                        case_citation=metadata.get("case_citation"),
                        date=metadata.get("date"),
                        jurisdiction=metadata.get("jurisdiction", "WI"),
                        title=metadata.get("title", ""),
                        source_uri=metadata.get("source_uri", ""),
                        jurisdiction_id=metadata.get("jurisdiction_id"),
                        country=metadata.get("country"),
                        region=metadata.get("region"),
                        level=metadata.get("level"),
                        category=metadata.get("category"),
                        categories=(
                            metadata["categories_csv"].split(",")
                            if metadata.get("categories_csv") else []
                        ),
                        source_id=metadata.get("source_id"),
                    )
                    chunks.append(chunk)
            
            logger.debug(f"Retrieved {len(chunks)} chunks from collection")
            return chunks
            
        except Exception as e:
            logger.error(f"Error getting all chunks: {e}")
            return []
    
    def reset_collection(self):
        """Reset (delete) the collection. Use with caution!"""
        try:
            self.client.delete_collection(name=self.COLLECTION_NAME)
            self.collection = self.client.create_collection(
                name=self.COLLECTION_NAME,
                embedding_function=self.embedding_function,
                metadata={"hnsw:space": "cosine"}
            )
            logger.warning(f"Collection '{self.COLLECTION_NAME}' has been reset")
        except Exception as e:
            logger.error(f"Error resetting collection: {str(e)}")
            raise


# Global instance
_vector_store: Optional[VectorStore] = None


def get_vector_store() -> VectorStore:
    """Get or create global vector store instance"""
    global _vector_store
    if _vector_store is None:
        _vector_store = VectorStore()
    return _vector_store
