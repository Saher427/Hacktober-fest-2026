"""
embeddings.py — ChromaDB indexing and retrieval, persisted per-repo.
Fully resilient: all operations degrade gracefully when Ollama is offline.
"""
from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path
from typing import Optional

import chromadb
from chromadb.config import Settings

logger = logging.getLogger(__name__)


class EmbeddingStore:
    """
    Manages ChromaDB collections for per-repo file embeddings.
    Uses Ollama's nomic-embed-text model for embeddings.
    Falls back to keyword-based search when Ollama is unavailable.
    """

    def __init__(
        self,
        persist_dir: str = "./chroma_db",
        ollama_base_url: str = "http://localhost:11434",
        embed_model: str = "nomic-embed-text",
    ):
        self.persist_dir = Path(persist_dir)
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self.ollama_base_url = ollama_base_url
        self.embed_model = embed_model
        self.ollama_available = self._check_ollama()

        self.client = chromadb.PersistentClient(
            path=str(self.persist_dir),
            settings=Settings(anonymized_telemetry=False),
        )
        self._embedding_fn = self._get_embedding_function()

        # In-memory fallback store for when embeddings fail
        self._fallback_docs: dict[str, list[dict]] = {}

    def _check_ollama(self) -> bool:
        """Quick check if Ollama is reachable."""
        try:
            import requests
            resp = requests.get(f"{self.ollama_base_url}/api/tags", timeout=2)
            if resp.status_code == 200:
                models = [m["name"] for m in resp.json().get("models", [])]
                # Check if our embed model is available
                return any(self.embed_model in m for m in models)
            return False
        except Exception:
            return False

    def _get_embedding_function(self):
        """Create an Ollama-backed embedding function for ChromaDB."""
        if not self.ollama_available:
            logger.warning(
                f"Ollama embed model '{self.embed_model}' not available. "
                "Using keyword-based fallback for file search."
            )
            return self._KeywordEmbeddingFn()

        try:
            from chromadb.utils.embedding_functions import OllamaEmbeddingFunction
            return OllamaEmbeddingFunction(
                url=f"{self.ollama_base_url}/api/embeddings",
                model_name=self.embed_model,
            )
        except (ImportError, Exception) as e:
            logger.warning(f"ChromaDB OllamaEmbeddingFunction unavailable ({e}), using custom.")
            return self._CustomOllamaEmbeddingFn(self.ollama_base_url, self.embed_model)

    class _KeywordEmbeddingFn:
        """Deterministic TF-style keyword embedding — no network needed."""
        DIM = 256

        def __call__(self, input: list[str]) -> list[list[float]]:
            result = []
            for text in input:
                vec = [0.0] * self.DIM
                words = text.lower().split()
                for word in words:
                    idx = hash(word) % self.DIM
                    vec[idx] += 1.0
                # Normalize
                total = sum(vec) or 1.0
                vec = [v / total for v in vec]
                result.append(vec)
            return result

    class _CustomOllamaEmbeddingFn:
        """Fallback embedding function calling Ollama directly."""
        def __init__(self, base_url: str, model: str):
            self.base_url = base_url
            self.model = model

        def __call__(self, input: list[str]) -> list[list[float]]:
            import requests
            embeddings = []
            for text in input:
                try:
                    resp = requests.post(
                        f"{self.base_url}/api/embeddings",
                        json={"model": self.model, "prompt": text[:8000]},
                        timeout=60,
                    )
                    resp.raise_for_status()
                    embeddings.append(resp.json()["embedding"])
                except Exception as e:
                    logger.warning(f"Embedding API error (using keyword fallback): {e}")
                    # Return a keyword-derived vector as fallback
                    vec = [0.0] * 768
                    for word in text.lower().split():
                        idx = hash(word) % 768
                        vec[idx] += 1.0
                    total = sum(vec) or 1.0
                    embeddings.append([v / total for v in vec])
            return embeddings

    def get_collection_id(self, repo_url: str, branch: str = "main") -> str:
        """Generate a stable, valid ChromaDB collection name from a repo URL."""
        h = hashlib.md5(f"{repo_url}:{branch}".encode()).hexdigest()[:8]
        parts = repo_url.rstrip("/").split("/")
        owner_repo = "_".join(parts[-2:]) if len(parts) >= 2 else parts[-1]
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in owner_repo)
        name = f"fif_{safe[:40]}_{h}"
        return name[:63]

    def collection_exists(self, repo_url: str) -> bool:
        """Check if a collection already exists for this repo."""
        col_id = self.get_collection_id(repo_url)
        try:
            existing = [c.name for c in self.client.list_collections()]
            # Only treat as existing if it has documents
            if col_id in existing:
                col = self.client.get_collection(col_id)
                return col.count() > 0
            return False
        except Exception:
            return False

    def index_files(
        self,
        repo_url: str,
        files: dict,  # dict[str, FileInfo]
        progress_callback=None,
        batch_size: int = 10,
    ) -> str:
        """
        Index all file summaries into ChromaDB.
        Falls back to in-memory keyword store if ChromaDB/Ollama fails.
        Returns the collection ID.
        """
        col_id = self.get_collection_id(repo_url)

        # Delete existing collection if present (re-index)
        try:
            self.client.delete_collection(col_id)
        except Exception:
            pass

        collection = self.client.create_collection(
            name=col_id,
            embedding_function=self._embedding_fn,
            metadata={"repo_url": repo_url},
        )

        # Prepare documents
        documents = []
        metadatas = []
        ids = []
        fallback_docs = []

        for path, info in files.items():
            doc_parts = [f"File: {path}"]
            if info.classes:
                doc_parts.append(f"Classes: {', '.join(info.classes[:10])}")
            if info.functions:
                doc_parts.append(f"Functions: {', '.join(info.functions[:20])}")
            if info.docstring:
                doc_parts.append(f"Description: {info.docstring[:300]}")
            if info.raw_content:
                doc_parts.append(f"Code:\n{info.raw_content[:1500]}")

            doc = "\n".join(doc_parts)
            documents.append(doc)
            meta = {
                "path": path,
                "extension": info.extension,
                "complexity": info.complexity_score,
                "lines": info.line_count,
                "functions": ",".join(info.functions[:20]),
                "classes": ",".join(info.classes[:10]),
            }
            metadatas.append(meta)
            ids.append(hashlib.md5(path.encode()).hexdigest())
            fallback_docs.append({"path": path, "content": doc, "metadata": meta, "distance": 0.5})

        # Always populate in-memory fallback
        self._fallback_docs[repo_url] = fallback_docs

        # Index in batches
        total = len(documents)
        success_count = 0
        for i in range(0, total, batch_size):
            batch_docs = documents[i:i+batch_size]
            batch_meta = metadatas[i:i+batch_size]
            batch_ids = ids[i:i+batch_size]

            try:
                collection.add(
                    documents=batch_docs,
                    metadatas=batch_meta,
                    ids=batch_ids,
                )
                success_count += len(batch_docs)
            except Exception as e:
                logger.warning(f"Indexing batch {i//batch_size} failed (keyword fallback active): {e}")

            if progress_callback:
                progress_callback(
                    f"Indexing files... ({min(i+batch_size, total)}/{total})"
                )

        if success_count > 0:
            logger.info(f"Indexed {success_count}/{total} files into ChromaDB collection '{col_id}'")
        else:
            logger.warning(f"ChromaDB indexing failed — using in-memory keyword search for {total} files")

        return col_id

    def search(
        self,
        repo_url: str,
        query: str,
        n_results: int = 5,
    ) -> list[dict]:
        """
        Semantic search over indexed files.
        Falls back to keyword matching if ChromaDB is empty or unavailable.
        Returns list of {path, content, metadata, distance}.
        """
        if n_results <= 0:
            return []

        col_id = self.get_collection_id(repo_url)

        # Try ChromaDB first
        try:
            collection = self.client.get_collection(
                name=col_id,
                embedding_function=self._embedding_fn,
            )
            count = collection.count()
            if count > 0:
                actual_n = min(n_results, count)
                results = collection.query(
                    query_texts=[query],
                    n_results=actual_n,
                )
                output = []
                if results and results["documents"]:
                    for doc, meta, dist in zip(
                        results["documents"][0],
                        results["metadatas"][0],
                        results["distances"][0],
                    ):
                        output.append({
                            "path": meta.get("path", ""),
                            "content": doc,
                            "metadata": meta,
                            "distance": dist,
                        })
                if output:
                    return output
        except Exception as e:
            logger.warning(f"ChromaDB search failed, falling back to keyword search: {e}")

        # Fallback: keyword search over in-memory docs
        return self._keyword_search(repo_url, query, n_results)

    def _keyword_search(self, repo_url: str, query: str, n_results: int) -> list[dict]:
        """Simple keyword-based fallback search."""
        docs = self._fallback_docs.get(repo_url, [])
        if not docs:
            return []

        query_words = set(query.lower().split())
        scored = []
        for doc in docs:
            content_lower = doc["content"].lower()
            score = sum(1 for w in query_words if w in content_lower)
            if score > 0:
                scored.append((score, doc))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [d for _, d in scored[:n_results]]

    def get_all_documents(self, repo_url: str) -> list[dict]:
        """Retrieve all indexed documents for a repo."""
        col_id = self.get_collection_id(repo_url)
        try:
            collection = self.client.get_collection(
                name=col_id,
                embedding_function=self._embedding_fn,
            )
            results = collection.get(include=["documents", "metadatas"])
            output = []
            for doc, meta in zip(results["documents"], results["metadatas"]):
                output.append({"path": meta.get("path", ""), "content": doc, "metadata": meta})
            return output
        except Exception as e:
            logger.warning(f"Get all documents failed, using fallback: {e}")
            return self._fallback_docs.get(repo_url, [])
