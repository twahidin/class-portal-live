"""
RAG (Retrieval-Augmented Generation) service for storing and querying textbook content
per module tree. Enables the learning agent to ground responses in uploaded textbook PDFs.
"""

import os
import re
import io
import logging
import uuid
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

# Chunking defaults
CHUNK_SIZE = 800
CHUNK_OVERLAP = 150
MAX_CHUNKS_QUERY = 5


def _extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract text from PDF using PyPDF2."""
    try:
        import PyPDF2
        reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
        parts = []
        for i, page in enumerate(reader.pages):
            text = page.extract_text()
            if text and text.strip():
                parts.append(f"--- Page {i + 1} ---\n{text.strip()}")
        return "\n\n".join(parts)
    except Exception as e:
        logger.error("Error extracting text from PDF: %s", e)
        return ""


def _chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
    """Split text into overlapping chunks (by character count, roughly sentence-aware)."""
    if not text or not text.strip():
        return []
    text = text.replace("\r\n", "\n").strip()
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        if end >= len(text):
            chunks.append(text[start:].strip())
            break
        # Prefer breaking at paragraph or sentence
        break_at = text.rfind("\n\n", start, end + 1)
        if break_at < start:
            break_at = text.rfind(". ", start, end + 1)
        if break_at >= start:
            end = break_at + 1
        chunks.append(text[start:end].strip())
        start = end - overlap
        if start >= len(text):
            break
    return [c for c in chunks if c]


def _get_embedding_function():
    """Return OpenAI embedding function for ChromaDB if available."""
    try:
        import chromadb.utils.embedding_functions as ef
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            return None
        return ef.OpenAIEmbeddingFunction(api_key=api_key, model="text-embedding-3-small")
    except Exception as e:
        logger.warning("OpenAI embedding function not available: %s", e)
        return None


def _get_chroma_client():
    """Return persistent ChromaDB client. Data stored under data/chromadb."""
    try:
        import chromadb
    except ImportError:
        logger.warning("chromadb not installed; run: pip install chromadb")
        return None
    data_dir = os.getenv("CHROMA_DATA_PATH", os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "chromadb"))
    os.makedirs(data_dir, exist_ok=True)
    return chromadb.PersistentClient(path=data_dir)


def _collection_name(module_id: str) -> str:
    """ChromaDB collection name for a module's textbook. Sanitize for Chroma."""
    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", module_id)
    return f"textbook_{safe}"[:63]


def ingest_textbook(
    module_id: str,
    pdf_bytes: bytes,
    title: Optional[str] = None,
    append: bool = True,
) -> Dict[str, Any]:
    """
    Ingest a textbook PDF for a module tree: extract text, chunk, embed, store in ChromaDB.
    By default appends to existing content so you can upload chapters one at a time.

    Args:
        module_id: Root module_id of the module tree.
        pdf_bytes: Raw PDF file bytes.
        title: Optional display name for this upload (e.g. chapter name).
        append: If True (default), add to existing RAG content. If False, replace all content.

    Returns:
        Dict with success, chunk_count (this upload), total_chunk_count (total in RAG), error.
    """
    client = _get_chroma_client()
    if not client:
        return {"success": False, "error": "Vector store not available (install chromadb)."}

    emb_fn = _get_embedding_function()
    if not emb_fn:
        return {"success": False, "error": "Embeddings not available (set OPENAI_API_KEY)."}

    text = _extract_text_from_pdf(pdf_bytes)
    if not text or len(text.strip()) < 100:
        return {"success": False, "error": "Could not extract enough text from the PDF (may be image-only or corrupted)."}

    chunks = _chunk_text(text)
    if not chunks:
        return {"success": False, "error": "No text chunks produced from PDF."}

    coll_name = _collection_name(module_id)
    try:
        if not append:
            try:
                client.delete_collection(coll_name)
            except Exception:
                pass
        try:
            collection = client.get_collection(name=coll_name, embedding_function=emb_fn)
        except Exception:
            collection = client.create_collection(
                name=coll_name,
                embedding_function=emb_fn,
                metadata={"hnsw:space": "cosine"},
            )
        ids = [str(uuid.uuid4()) for _ in chunks]
        upload_title = (title or "Textbook").strip()[:200]
        metadatas = [
            {"page_chunk": i + 1, "batch_chunks": len(chunks), "upload_title": upload_title}
            for i in range(len(chunks))
        ]
        collection.add(ids=ids, documents=chunks, metadatas=metadatas)
        total = collection.count()
        return {
            "success": True,
            "chunk_count": len(chunks),
            "total_chunk_count": total,
            "title": title or "Textbook",
        }
    except Exception as e:
        logger.exception("Error ingesting textbook for module %s: %s", module_id, e)
        return {"success": False, "error": str(e), "chunk_count": 0, "total_chunk_count": 0}


def query_textbook(
    module_id: str,
    query: str,
    k: int = MAX_CHUNKS_QUERY,
) -> Dict[str, Any]:
    """
    Query the textbook RAG store for a module. Returns relevant chunks for context.

    Args:
        module_id: Root module_id of the module tree.
        query: Natural language or keyword query (or current module title/objectives).
        k: Max number of chunks to return.

    Returns:
        Dict with success, chunks (list of { content, metadata }), error.
    """
    if not query or not query.strip():
        return {"success": True, "chunks": []}

    client = _get_chroma_client()
    if not client:
        return {"success": False, "chunks": [], "error": "Vector store not available."}

    emb_fn = _get_embedding_function()
    if not emb_fn:
        return {"success": False, "chunks": [], "error": "Embeddings not available."}

    coll_name = _collection_name(module_id)
    try:
        collection = client.get_collection(name=coll_name, embedding_function=emb_fn)
    except Exception:
        return {"success": True, "chunks": []}

    try:
        results = collection.query(query_texts=[query.strip()], n_results=min(k, 10))
        if not results or not results.get("documents") or not results["documents"][0]:
            return {"success": True, "chunks": []}
        docs = results["documents"][0]
        metadatas = (results.get("metadatas") or [[]])[0]
        chunks = []
        for i, doc in enumerate(docs):
            meta = metadatas[i] if i < len(metadatas) else {}
            chunks.append({"content": doc, "metadata": meta})
        return {"success": True, "chunks": chunks}
    except Exception as e:
        logger.warning("Error querying textbook for module %s: %s", module_id, e)
        return {"success": False, "chunks": [], "error": str(e)}


def textbook_has_content(module_id: str) -> bool:
    """Return True if this module has a textbook ingested in the vector store."""
    client = _get_chroma_client()
    if not client:
        return False
    coll_name = _collection_name(module_id)
    try:
        coll = client.get_collection(coll_name)
        return coll.count() > 0
    except Exception:
        return False


def delete_textbook(module_id: str) -> Dict[str, Any]:
    """Remove textbook collection for this module."""
    client = _get_chroma_client()
    if not client:
        return {"success": False, "error": "Vector store not available."}
    coll_name = _collection_name(module_id)
    try:
        client.delete_collection(coll_name)
        return {"success": True}
    except Exception as e:
        logger.warning("Error deleting textbook for module %s: %s", module_id, e)
        return {"success": False, "error": str(e)}
