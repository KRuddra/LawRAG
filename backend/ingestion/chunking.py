"""
Legal-aware document chunking strategy
Preserves context, handles hierarchical structures, and maintains legal citations
"""

import re
import hashlib
from typing import List, Optional
from backend.api.models import Document, Chunk


# Constants
TARGET_CHUNK_TOKENS = 1200
CHARS_PER_TOKEN_ESTIMATE = 4  # Rough estimate: ~4 characters per token
TARGET_CHUNK_CHARS = TARGET_CHUNK_TOKENS * CHARS_PER_TOKEN_ESTIMATE
CHUNK_OVERLAP_CHARS = 200  # Overlap between chunks to preserve context


def estimate_tokens(text: str) -> int:
    """Estimate token count from character count"""
    return len(text) // CHARS_PER_TOKEN_ESTIMATE


def generate_chunk_id(doc_id: str, chunk_index: int) -> str:
    """Generate a unique chunk ID"""
    # Create a hash from doc_id for shorter ID
    doc_hash = hashlib.md5(doc_id.encode()).hexdigest()[:8]
    return f"{doc_hash}_chunk_{chunk_index}"


def find_statute_boundaries(text: str) -> List[tuple]:
    """
    Find statute/section boundaries in text.
    Returns list of (start_index, match_text) tuples for splitting points.
    """
    boundaries = []
    
    # Pattern 1: Section markers like "§ 940.01", "§940.01"
    pattern1 = r'§\s*\d+\.\d+(?:\([0-9a-zA-Z]+\))*'
    
    # Pattern 2: "Section 940.01" or "section 940.01"
    pattern2 = r'(?:Section|section|Sec\.|sec\.)\s+\d+\.\d+(?:\([0-9a-zA-Z]+\))*'
    
    # Pattern 3: Subsections like "939.50(3)(a)" or "(1)", "(2)(a)"
    pattern3 = r'(?:^|\n)\s*\(\d+\)(?:\s*\([a-zA-Z]+\))?\s+[A-Z]'
    
    # Combine patterns
    combined_pattern = f'({pattern1}|{pattern2}|{pattern3})'
    
    for match in re.finditer(combined_pattern, text, re.MULTILINE | re.IGNORECASE):
        boundaries.append((match.start(), match.group(0)))
    
    return sorted(boundaries, key=lambda x: x[0])


def find_case_law_headings(text: str) -> List[tuple]:
    """
    Find case law section headings like FACTS, HOLDING, REASONING.
    Returns list of (start_index, heading_text) tuples.
    """
    headings = []
    
    # Pattern: ALL CAPS headings on their own line
    # Common legal section headings
    legal_sections = [
        'FACTS', 'HOLDING', 'REASONING', 'ANALYSIS', 'CONCLUSION',
        'ISSUE', 'BACKGROUND', 'PROCEDURAL HISTORY', 'DISCUSSION',
        'DISSENT', 'CONCURRENCE', 'OPINION'
    ]
    
    pattern = r'(?:^|\n)\s*(' + '|'.join(legal_sections) + r')\s*(?:\n|$)'
    
    for match in re.finditer(pattern, text, re.MULTILINE | re.IGNORECASE):
        headings.append((match.start(), match.group(1).upper()))
    
    return sorted(headings, key=lambda x: x[0])


def find_numbered_headings(text: str) -> List[tuple]:
    """
    Find numbered headings like "1.0", "2.1.3", "3.2.1(a)".
    Returns list of (start_index, heading_text) tuples.
    """
    headings = []
    
    # Pattern: Numbered headings like "1.0", "2.1.3", "3.2.1(a)"
    # Must be at start of line or after whitespace
    pattern = r'(?:^|\n)\s*(\d+(?:\.\d+)*(?:\([a-zA-Z]+\))?)\s+[A-Z]'
    
    for match in re.finditer(pattern, text, re.MULTILINE):
        headings.append((match.start(), match.group(1)))
    
    return sorted(headings, key=lambda x: x[0])


def find_all_caps_headings(text: str) -> List[tuple]:
    """
    Find ALL CAPS headings (common in policies/training documents).
    Returns list of (start_index, heading_text) tuples.
    """
    headings = []
    
    # Pattern: Lines that are ALL CAPS, at least 3 words, on their own line
    pattern = r'(?:^|\n)\s*([A-Z][A-Z\s]{10,})(?:\n|$)'
    
    for match in re.finditer(pattern, text):
        heading_text = match.group(1).strip()
        # Filter out lines that are too short or contain lowercase letters
        if len(heading_text.split()) >= 3 and heading_text.isupper():
            headings.append((match.start(), heading_text))
    
    return sorted(headings, key=lambda x: x[0])


def extract_statute_number_from_text(text: str) -> Optional[str]:
    """Extract statute number from text chunk"""
    # Look for patterns like § 940.01 or Section 940.01
    patterns = [
        r'§\s*(\d+\.\d+(?:\([0-9a-zA-Z]+\))*)',
        r'(?:Section|section|Sec\.|sec\.)\s+(\d+\.\d+(?:\([0-9a-zA-Z]+\))*)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    
    return None


def extract_case_citation_from_text(text: str) -> Optional[str]:
    """Extract case citation from text chunk"""
    # Pattern: "State v. Smith" or "State v Smith" or similar case names
    pattern = r'([A-Z][a-z]+\s+v\.?\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)'
    match = re.search(pattern, text)
    if match:
        return match.group(1)
    
    return None


def create_hierarchy_path(doc_type: str, text: str, chunk_index: int) -> str:
    """
    Create a hierarchy path string for the chunk.
    Examples:
    - "Chapter 940 > Section 940.01 > Subsection (1)"
    - "FACTS > Paragraph 1"
    - "Section 2.1 > Subsection 2.1.3"
    """
    if doc_type == 'statute':
        # Try to extract chapter and section
        chapter_match = re.search(r'Chapter\s+(\d+)', text, re.IGNORECASE)
        section_match = re.search(r'§\s*(\d+\.\d+)', text)
        
        parts = []
        if chapter_match:
            parts.append(f"Chapter {chapter_match.group(1)}")
        if section_match:
            parts.append(f"Section {section_match.group(1)}")
        
        # Check for subsection
        subsection_match = re.search(r'\((\d+)\)', text)
        if subsection_match:
            parts.append(f"Subsection ({subsection_match.group(1)})")
        
        return " > ".join(parts) if parts else f"Section {chunk_index + 1}"
    
    elif doc_type == 'case_law':
        # Try to find section heading
        headings = find_case_law_headings(text)
        if headings:
            return headings[0][1]
        return f"Section {chunk_index + 1}"
    
    elif doc_type in ['policy', 'training']:
        # Try to find numbered heading
        numbered = find_numbered_headings(text)
        if numbered:
            return f"Section {numbered[0][1]}"
        
        # Try ALL CAPS heading
        caps = find_all_caps_headings(text)
        if caps:
            return caps[0][1][:50]  # Truncate long headings
        
        return f"Section {chunk_index + 1}"
    
    return f"Section {chunk_index + 1}"


def split_text_at_boundaries(text: str, boundaries: List[tuple]) -> List[str]:
    """
    Split text at boundary points, preserving boundary markers with their sections.
    """
    if not boundaries:
        return [text]
    
    chunks = []
    last_index = 0
    
    for i, (start_idx, boundary_text) in enumerate(boundaries):
        # Get text from last boundary to current boundary
        if start_idx > last_index:
            chunk_text = text[last_index:start_idx].strip()
            if chunk_text:
                chunks.append(chunk_text)
        
        # Include boundary text with the next chunk
        # Find the end of this section (next boundary or end of text)
        if i + 1 < len(boundaries):
            next_start = boundaries[i + 1][0]
            chunk_text = text[start_idx:next_start].strip()
        else:
            chunk_text = text[start_idx:].strip()
        
        if chunk_text:
            chunks.append(chunk_text)
        
        last_index = start_idx + len(chunk_text)
    
    # Add any remaining text
    if last_index < len(text):
        remaining = text[last_index:].strip()
        if remaining:
            chunks.append(remaining)
    
    return chunks if chunks else [text]


def subchunk_text(text: str, max_chars: int = TARGET_CHUNK_CHARS, overlap: int = CHUNK_OVERLAP_CHARS) -> List[str]:
    """
    Split text into smaller chunks if it exceeds max_chars, with overlap.
    Tries to split at sentence boundaries when possible.
    """
    if len(text) <= max_chars:
        return [text]
    
    chunks = []
    current_pos = 0
    last_pos = -1  # Track last position to detect infinite loops
    
    while current_pos < len(text):
        # Safety check to prevent infinite loops
        if current_pos <= last_pos:
            # If we're not making progress, force advance
            current_pos = last_pos + max_chars // 2
            if current_pos >= len(text):
                break
        
        last_pos = current_pos
        
        # Calculate end position
        end_pos = min(current_pos + max_chars, len(text))
        
        if end_pos >= len(text):
            # Last chunk
            remaining = text[current_pos:].strip()
            if remaining:
                chunks.append(remaining)
            break
        
        # Try to find a good split point (sentence boundary)
        # Look for sentence endings in the last 20% of the chunk
        search_start = max(current_pos, end_pos - (max_chars // 5))
        search_text = text[search_start:end_pos]
        
        # Find last sentence boundary
        sentence_end_match = None
        for match in re.finditer(r'[.!?]\s+', search_text):
            sentence_end_match = match
        
        if sentence_end_match:
            # Found a sentence boundary
            actual_end = search_start + sentence_end_match.end()
            chunk = text[current_pos:actual_end].strip()
            if chunk:
                chunks.append(chunk)
            # Move forward, accounting for overlap
            current_pos = max(actual_end - overlap, actual_end - (overlap // 2))
        else:
            # No sentence boundary found, split at word boundary
            # Look for last space in the search area
            last_space = text.rfind(' ', search_start, end_pos)
            if last_space > search_start:
                chunk = text[current_pos:last_space].strip()
                if chunk:
                    chunks.append(chunk)
                current_pos = max(last_space - overlap, last_space - (overlap // 2))
            else:
                # Force split at end_pos
                chunk = text[current_pos:end_pos].strip()
                if chunk:
                    chunks.append(chunk)
                current_pos = end_pos - (overlap // 2)
    
    return chunks if chunks else [text]


def merge_small_chunks(chunks: List[str], min_size: int = 1000) -> List[str]:
    """
    Merge small chunks with adjacent chunks to reach minimum size.
    Helps avoid too many tiny chunks.
    """
    if not chunks:
        return chunks
    
    merged = []
    current = chunks[0]
    
    for next_chunk in chunks[1:]:
        # If current chunk is too small, try to merge with next
        if len(current) < min_size and next_chunk:
            current = current + "\n\n" + next_chunk
        else:
            # Current chunk is big enough, save it and start new one
            if current.strip():
                merged.append(current)
            current = next_chunk
    
    # Add the last chunk
    if current.strip():
        merged.append(current)
    
    return merged if merged else chunks


def chunk_statute(document: Document) -> List[Chunk]:
    """Chunk a statute document by section boundaries"""
    text = document.text
    metadata = document.metadata
    chunks = []
    
    # Find section boundaries - focus on major sections first
    # Only look for actual section numbers like "§ 940.01", not subsections
    major_boundary_pattern = r'§\s*\d+\.\d+(?:\([0-9a-zA-Z]+\))*|(?:Section|section|Sec\.|sec\.)\s+\d+\.\d+(?:\([0-9a-zA-Z]+\))*'
    
    boundaries = []
    for match in re.finditer(major_boundary_pattern, text, re.MULTILINE | re.IGNORECASE):
        boundaries.append((match.start(), match.group(0)))
    
    boundaries = sorted(boundaries, key=lambda x: x[0])
    
    # Split at major boundaries
    if boundaries:
        section_chunks = split_text_at_boundaries(text, boundaries)
    else:
        # Fallback: use all boundaries (including subsections)
        boundaries = find_statute_boundaries(text)
        section_chunks = split_text_at_boundaries(text, boundaries)
    
    # Merge very small chunks first (before subchunking)
    section_chunks = merge_small_chunks(section_chunks, min_size=500)
    
    chunk_index = 0
    for section_text in section_chunks:
        # Only subchunk if significantly larger than target
        if len(section_text) > TARGET_CHUNK_CHARS * 1.5:
            subchunks = subchunk_text(section_text)
        else:
            subchunks = [section_text]
        
        for subchunk in subchunks:
            # Skip very small chunks (likely artifacts)
            if len(subchunk.strip()) < 10:
                continue
                
            statute_number = extract_statute_number_from_text(subchunk) or \
                           (metadata.get('statute_numbers', [None])[0] if metadata.get('statute_numbers') else None)
            
            hierarchy_path = create_hierarchy_path('statute', subchunk, chunk_index)
            
            chunk = Chunk(
                chunk_id=generate_chunk_id(document.source_path, chunk_index),
                doc_id=document.source_path,
                doc_type=metadata.get('document_type', 'statute'),
                text=subchunk,
                hierarchy_path=hierarchy_path,
                statute_number=statute_number,
                case_citation=None,
                date=metadata.get('dates', [None])[0] if metadata.get('dates') else None,
                jurisdiction=metadata.get('jurisdiction', 'WI'),
                title=metadata.get('title', 'Untitled'),
                source_uri=document.source_path
            )
            chunks.append(chunk)
            chunk_index += 1
    
    return chunks


def chunk_case_law(document: Document) -> List[Chunk]:
    """Chunk a case law document by section headings"""
    text = document.text
    metadata = document.metadata
    chunks = []
    
    # Find section headings
    headings = find_case_law_headings(text)
    
    if headings:
        # Split at headings
        boundaries = [(h[0], h[1]) for h in headings]
        section_chunks = split_text_at_boundaries(text, boundaries)
    else:
        # No headings found, chunk by paragraph or size
        section_chunks = [text]
    
    chunk_index = 0
    for section_text in section_chunks:
        # Extract case citation
        case_citation = extract_case_citation_from_text(section_text) or \
                       extract_case_citation_from_text(text)
        
        # Subchunk if needed
        subchunks = subchunk_text(section_text)
        
        for subchunk in subchunks:
            # Extract statute number from chunk if present (case law often references statutes)
            statute_number = extract_statute_number_from_text(subchunk)
            
            hierarchy_path = create_hierarchy_path('case_law', subchunk, chunk_index)
            
            chunk = Chunk(
                chunk_id=generate_chunk_id(document.source_path, chunk_index),
                doc_id=document.source_path,
                doc_type=metadata.get('document_type', 'case_law'),
                text=subchunk,
                hierarchy_path=hierarchy_path,
                statute_number=statute_number,  # Now extracts statute numbers from case law chunks
                case_citation=case_citation if chunk_index == 0 else None,  # Only include in first chunk
                date=metadata.get('dates', [None])[0] if metadata.get('dates') else None,
                jurisdiction=metadata.get('jurisdiction', 'WI'),
                title=metadata.get('title', 'Untitled'),
                source_uri=document.source_path
            )
            chunks.append(chunk)
            chunk_index += 1
    
    return chunks


def chunk_policy_training(document: Document) -> List[Chunk]:
    """Chunk policy/training documents by numbered headings or ALL CAPS headings"""
    text = document.text
    metadata = document.metadata
    chunks = []
    
    # Find numbered headings first
    numbered_headings = find_numbered_headings(text)
    
    # Find ALL CAPS headings
    caps_headings = find_all_caps_headings(text)
    
    # Combine and sort boundaries
    all_boundaries = []
    if numbered_headings:
        all_boundaries.extend([(h[0], h[1]) for h in numbered_headings])
    if caps_headings:
        all_boundaries.extend([(h[0], h[1]) for h in caps_headings])
    
    all_boundaries = sorted(set(all_boundaries), key=lambda x: x[0])
    
    if all_boundaries:
        section_chunks = split_text_at_boundaries(text, all_boundaries)
    else:
        # No headings found, chunk by paragraph or size
        section_chunks = [text]
    
    chunk_index = 0
    for section_text in section_chunks:
        # Subchunk if needed
        subchunks = subchunk_text(section_text)
        
        for subchunk in subchunks:
            hierarchy_path = create_hierarchy_path(metadata.get('document_type', 'policy'), subchunk, chunk_index)
            
            chunk = Chunk(
                chunk_id=generate_chunk_id(document.source_path, chunk_index),
                doc_id=document.source_path,
                doc_type=metadata.get('document_type', 'policy'),
                text=subchunk,
                hierarchy_path=hierarchy_path,
                statute_number=None,
                case_citation=None,
                date=metadata.get('dates', [None])[0] if metadata.get('dates') else None,
                jurisdiction=metadata.get('jurisdiction', 'WI'),
                title=metadata.get('title', 'Untitled'),
                source_uri=document.source_path
            )
            chunks.append(chunk)
            chunk_index += 1
    
    return chunks


def _enrich_chunks(chunks: List[Chunk], metadata: dict) -> List[Chunk]:
    """Attach multi-jurisdiction / category metadata to chunks (Decisions 7 & 8).

    Reads the structured fields an adapter placed on the Document's metadata and
    copies them onto every chunk, so retrieval can filter by jurisdiction and
    category. ``category`` is the primary (first) label used as the scalar
    filter; the full list is preserved on ``categories``.
    """
    categories = list(metadata.get('categories') or [])
    primary = categories[0] if categories else metadata.get('category')
    for chunk in chunks:
        chunk.jurisdiction_id = metadata.get('jurisdiction_id')
        chunk.country = metadata.get('country')
        chunk.region = metadata.get('region')
        chunk.level = metadata.get('level')
        chunk.category = primary
        chunk.categories = categories
        chunk.source_id = metadata.get('source_id')
    return chunks


def chunk_document(document: Document) -> List[Chunk]:
    """
    Chunk a document using legal-aware strategies based on document type.

    Heuristics:
    - statute: split on statute/section boundaries (§ 940.01, 939.50(3)(a))
    - case_law: split by headings (FACTS / HOLDING / REASONING), capture "State v." patterns
    - policies/training: split by numbered headings (1.0, 2.1.3) and ALL CAPS headings

    Size targets: chunk by section first, then subchunk to ~1200 tokens with overlap.

    Args:
        document: Document object with text and metadata

    Returns:
        List of Chunk objects with preserved legal context
    """
    doc_type = document.metadata.get('document_type', 'unknown')

    if doc_type == 'statute':
        chunks = chunk_statute(document)
    elif doc_type == 'case_law':
        chunks = chunk_case_law(document)
    elif doc_type in ['policy', 'training']:
        chunks = chunk_policy_training(document)
    else:
        # Fallback: chunk by size only
        chunks = []
        subchunks = subchunk_text(document.text)

        for i, subchunk in enumerate(subchunks):
            chunk = Chunk(
                chunk_id=generate_chunk_id(document.source_path, i),
                doc_id=document.source_path,
                doc_type=doc_type,
                text=subchunk,
                hierarchy_path=f"Section {i + 1}",
                statute_number=None,
                case_citation=None,
                date=document.metadata.get('dates', [None])[0] if document.metadata.get('dates') else None,
                jurisdiction=document.metadata.get('jurisdiction', 'WI'),
                title=document.metadata.get('title', 'Untitled'),
                source_uri=document.source_path
            )
            chunks.append(chunk)

    return _enrich_chunks(chunks, document.metadata)
