"""
backend/search/engine.py

Hybrid search engine:
  - Vector search (semantic, via pgvector cosine similarity)
  - Full-text search (BM25-like, via PostgreSQL tsvector)
  - Reciprocal Rank Fusion to merge results
  - Claude RAG to synthesize final answer with citations
"""
import logging
import time
from dataclasses import dataclass
from typing import Optional

import anthropic
import asyncpg
from openai import AsyncOpenAI
from pgvector.asyncpg import register_vector

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    case_id: str
    year: int
    title: str
    petitioner: Optional[str]
    respondent: Optional[str]
    date_of_judgment: Optional[str]
    disposal_nature: Optional[str]
    bench: Optional[str]
    citation: Optional[str]
    pdf_url: Optional[str]
    chunk_text: str
    score: float
    vector_rank: Optional[int] = None
    bm25_rank: Optional[int] = None


@dataclass
class RAGResponse:
    answer: str
    results: list[SearchResult]
    query: str
    latency_ms: int


async def embed_query(query: str, openai_client: AsyncOpenAI, model: str) -> list[float]:
    """Embed a single query string."""
    response = await openai_client.embeddings.create(input=[query], model=model)
    return response.data[0].embedding


async def vector_search(
    conn: asyncpg.Connection,
    embedding: list[float],
    top_k: int = 20,
    year_filter: Optional[int] = None,
    disposal_filter: Optional[str] = None,
) -> list[dict]:
    """
    Pure vector (semantic) search using pgvector cosine distance.
    Returns top_k chunks sorted by similarity.
    """
    params = [embedding, top_k]
    conditions = []

    if year_filter:
        conditions.append(f"c.year = ${len(params) + 1}")
        params.append(year_filter)

    if disposal_filter:
        conditions.append(f"c.disposal_nature ILIKE ${len(params) + 1}")
        params.append(f"%{disposal_filter}%")

    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

    sql = f"""
        SELECT
            ch.case_id,
            ch.chunk_text,
            ch.chunk_index,
            1 - (ch.embedding <=> $1::vector) AS score,
            c.year,
            c.title,
            c.petitioner,
            c.respondent,
            c.date_of_judgment::TEXT,
            c.disposal_nature,
            c.bench,
            c.citation,
            c.pdf_url
        FROM chunks ch
        JOIN cases c ON c.case_id = ch.case_id
        {where_clause}
        ORDER BY ch.embedding <=> $1::vector
        LIMIT $2
    """

    rows = await conn.fetch(sql, *params)
    return [dict(r) for r in rows]


async def fulltext_search(
    conn: asyncpg.Connection,
    query: str,
    top_k: int = 20,
    year_filter: Optional[int] = None,
    disposal_filter: Optional[str] = None,
) -> list[dict]:
    """
    Full-text search using PostgreSQL tsvector (BM25-like ranking).
    Good for finding specific party names, case numbers, citations.
    """
    params = [query, top_k]
    conditions = ["ch.ts_vector @@ plainto_tsquery('english', $1)"]

    if year_filter:
        conditions.append(f"c.year = ${len(params) + 1}")
        params.append(year_filter)

    if disposal_filter:
        conditions.append(f"c.disposal_nature ILIKE ${len(params) + 1}")
        params.append(f"%{disposal_filter}%")

    where_clause = "WHERE " + " AND ".join(conditions)

    sql = f"""
        SELECT
            ch.case_id,
            ch.chunk_text,
            ch.chunk_index,
            ts_rank_cd(ch.ts_vector, plainto_tsquery('english', $1)) AS score,
            c.year,
            c.title,
            c.petitioner,
            c.respondent,
            c.date_of_judgment::TEXT,
            c.disposal_nature,
            c.bench,
            c.citation,
            c.pdf_url
        FROM chunks ch
        JOIN cases c ON c.case_id = ch.case_id
        {where_clause}
        ORDER BY score DESC
        LIMIT $2
    """

    rows = await conn.fetch(sql, *params)
    return [dict(r) for r in rows]


def reciprocal_rank_fusion(
    vector_results: list[dict],
    bm25_results: list[dict],
    alpha: float = 0.6,  # weight for vector search
    k: int = 60,
) -> list[dict]:
    """
    Combine vector and BM25 results using Reciprocal Rank Fusion.
    alpha=0.6 means 60% weight to vector, 40% to BM25.
    """
    scores: dict[str, float] = {}
    vector_ranks: dict[str, int] = {}
    bm25_ranks: dict[str, int] = {}
    all_results: dict[str, dict] = {}

    # Vector results
    for rank, result in enumerate(vector_results):
        key = f"{result['case_id']}_{result['chunk_index']}"
        scores[key] = scores.get(key, 0) + alpha * (1 / (k + rank + 1))
        vector_ranks[key] = rank + 1
        all_results[key] = result

    # BM25 results
    for rank, result in enumerate(bm25_results):
        key = f"{result['case_id']}_{result['chunk_index']}"
        scores[key] = scores.get(key, 0) + (1 - alpha) * (1 / (k + rank + 1))
        bm25_ranks[key] = rank + 1
        all_results[key] = result

    # Sort by fused score
    sorted_keys = sorted(scores.keys(), key=lambda k: scores[k], reverse=True)

    fused = []
    for key in sorted_keys:
        result = all_results[key].copy()
        result["fused_score"] = scores[key]
        result["vector_rank"] = vector_ranks.get(key)
        result["bm25_rank"] = bm25_ranks.get(key)
        fused.append(result)

    return fused


def deduplicate_by_case(results: list[dict], top_k: int) -> list[dict]:
    """
    Keep only the top chunk per case to avoid showing 5 chunks from same judgment.
    Returns top_k unique cases.
    """
    seen_cases = set()
    deduped = []
    for r in results:
        if r["case_id"] not in seen_cases:
            seen_cases.add(r["case_id"])
            deduped.append(r)
        if len(deduped) >= top_k:
            break
    return deduped


RAG_SYSTEM_PROMPT = """You are an expert Indian legal research assistant with deep knowledge of the Supreme Court of India's jurisprudence.

You help lawyers, researchers, and citizens understand court judgments clearly and accurately.

When answering questions:
1. Base your answer ONLY on the provided judgment excerpts
2. Cite specific cases by name and year (e.g., "In Kesavananda Bharati (1973)...")
3. If the excerpts don't contain enough information, say so clearly
4. Use clear, plain language — avoid unnecessary legal jargon
5. Highlight key legal principles established by the cases
6. Note any landmark or constitution bench judgments

Format your response with:
- A direct answer to the question
- Key cases and their holdings
- Important legal principles
- Any limitations or caveats
"""


async def generate_rag_answer(
    query: str,
    results: list[dict],
    anthropic_client: anthropic.AsyncAnthropic,
    model: str = "claude-sonnet-4-6",
    max_tokens: int = 2000,
) -> str:
    """
    Generate a synthesized answer using Claude with retrieved chunks as context.
    """
    # Build context from top results
    context_parts = []
    for i, r in enumerate(results[:8]):  # use top 8 chunks for context
        context_parts.append(
            f"[Case {i+1}: {r.get('title', r['case_id'])} ({r.get('year', '')})"
            f" | {r.get('disposal_nature', '')}]\n{r['chunk_text']}"
        )

    context = "\n\n---\n\n".join(context_parts)

    user_message = f"""Based on the following Supreme Court judgment excerpts, please answer this question:

**Question:** {query}

**Judgment Excerpts:**

{context}

Please provide a comprehensive answer with specific case citations."""

    response = await anthropic_client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=RAG_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    return response.content[0].text


class SearchEngine:
    """Main search engine — holds connections and orchestrates search."""

    def __init__(
        self,
        pool: asyncpg.Pool,
        openai_client: AsyncOpenAI,
        anthropic_client: anthropic.AsyncAnthropic,
        embedding_model: str = "text-embedding-3-small",
        top_k: int = 10,
        alpha: float = 0.6,
        rag_model: str = "claude-sonnet-4-6",
        rag_max_tokens: int = 2000,
    ):
        self.pool = pool
        self.openai = openai_client
        self.anthropic = anthropic_client
        self.embedding_model = embedding_model
        self.top_k = top_k
        self.alpha = alpha
        self.rag_model = rag_model
        self.rag_max_tokens = rag_max_tokens

    async def search(
        self,
        query: str,
        year_filter: Optional[int] = None,
        disposal_filter: Optional[str] = None,
        generate_answer: bool = False,
    ) -> RAGResponse:
        start = time.monotonic()

        async with self.pool.acquire() as conn:
            await register_vector(conn)

            # Embed query
            embedding = await embed_query(query, self.openai, self.embedding_model)

            # Run both searches in parallel
            vector_task = vector_search(
                conn, embedding, top_k=self.top_k * 2,
                year_filter=year_filter, disposal_filter=disposal_filter,
            )
            bm25_task = fulltext_search(
                conn, query, top_k=self.top_k * 2,
                year_filter=year_filter, disposal_filter=disposal_filter,
            )

            vector_results, bm25_results = await asyncio.gather(vector_task, bm25_task)

        # Fuse and deduplicate
        fused = reciprocal_rank_fusion(vector_results, bm25_results, alpha=self.alpha)
        deduped = deduplicate_by_case(fused, self.top_k)

        # Convert to SearchResult objects
        search_results = [
            SearchResult(
                case_id=r["case_id"],
                year=r["year"],
                title=r.get("title", ""),
                petitioner=r.get("petitioner"),
                respondent=r.get("respondent"),
                date_of_judgment=r.get("date_of_judgment"),
                disposal_nature=r.get("disposal_nature"),
                bench=r.get("bench"),
                citation=r.get("citation"),
                pdf_url=r.get("pdf_url"),
                chunk_text=r["chunk_text"],
                score=r["fused_score"],
                vector_rank=r.get("vector_rank"),
                bm25_rank=r.get("bm25_rank"),
            )
            for r in deduped
        ]

        # Generate RAG answer if requested
        answer = ""
        if generate_answer and deduped:
            answer = await generate_rag_answer(
                query, deduped, self.anthropic,
                model=self.rag_model,
                max_tokens=self.rag_max_tokens,
            )

        latency_ms = int((time.monotonic() - start) * 1000)

        return RAGResponse(
            answer=answer,
            results=search_results,
            query=query,
            latency_ms=latency_ms,
        )


import asyncio  # noqa: E402 — needed for gather() above
