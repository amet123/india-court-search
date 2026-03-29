import logging
import os
from contextlib import asynccontextmanager
from typing import Optional

import anthropic
import asyncpg
import redis.asyncio as aioredis
from fastapi import FastAPI, HTTPException, Query, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from openai import AsyncOpenAI
from pgvector.asyncpg import register_vector
from pydantic import BaseModel, Field

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import get_settings
from search.engine import SearchEngine

logger = logging.getLogger(__name__)
settings = get_settings()

# ─── Lifespan (startup / shutdown) ───────────────────────────────

engine: Optional[SearchEngine] = None
redis_client: Optional[aioredis.Redis] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global engine, redis_client

    dsn = (
        f"postgresql://{settings.postgres_user}:{settings.postgres_password}"
        f"@{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"
    )

    async def init_conn(conn):
        await register_vector(conn)

    pool = await asyncpg.create_pool(dsn, min_size=2, max_size=10, init=init_conn)

    openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
    anthropic_client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    engine = SearchEngine(
        pool=pool,
        openai_client=openai_client,
        anthropic_client=anthropic_client,
        embedding_model=settings.embedding_model,
        top_k=settings.top_k_results,
        alpha=settings.hybrid_alpha,
        rag_model=settings.rag_model,
        rag_max_tokens=settings.rag_max_tokens,
    )

    redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)

    logger.info("Search engine ready.")
    yield

    await pool.close()
    await redis_client.close()


# ─── App ──────────────────────────────────────────────────────────

app = FastAPI(
    title="India Court Search Engine",
    description="AI-powered search over Indian Supreme Court judgments (1950–2025)",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Schemas ──────────────────────────────────────────────────────

class SearchRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=500)
    year: Optional[int] = Field(None, ge=1950, le=2025)
    disposal: Optional[str] = None
    generate_answer: bool = False
    top_k: Optional[int] = Field(None, ge=1, le=50)


class CaseResult(BaseModel):
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


class SearchResponse(BaseModel):
    query: str
    results: list[CaseResult]
    answer: Optional[str] = None
    latency_ms: int
    total_results: int


# ─── Endpoints ────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}


@app.post("/search", response_model=SearchResponse)
async def search(req: SearchRequest):
    """Hybrid semantic + keyword search over all judgments."""
    if not engine:
        raise HTTPException(503, "Search engine not ready")

    # Check cache
    cache_key = f"search:{req.query}:{req.year}:{req.disposal}:{req.generate_answer}"
    if redis_client:
        cached = await redis_client.get(cache_key)
        if cached:
            import json
            return SearchResponse(**json.loads(cached))

    response = await engine.search(
        query=req.query,
        year_filter=req.year,
        disposal_filter=req.disposal,
        generate_answer=req.generate_answer,
    )

    result = SearchResponse(
        query=response.query,
        results=[
            CaseResult(
                case_id=r.case_id,
                year=r.year,
                title=r.title or "",
                petitioner=r.petitioner,
                respondent=r.respondent,
                date_of_judgment=r.date_of_judgment,
                disposal_nature=r.disposal_nature,
                bench=r.bench,
                citation=r.citation,
                pdf_url=r.pdf_url,
                chunk_text=r.chunk_text,
                score=round(r.score, 4),
            )
            for r in response.results
        ],
        answer=response.answer or None,
        latency_ms=response.latency_ms,
        total_results=len(response.results),
    )

    # Cache for 10 minutes
    if redis_client:
        import json
        await redis_client.setex(cache_key, 600, result.model_dump_json())

    # Log search
    async with engine.pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO search_logs (query, results, latency_ms) VALUES ($1, $2, $3)",
            req.query, result.total_results, result.latency_ms,
        )

    return result


@app.post("/search/ask", response_model=SearchResponse)
async def search_and_ask(req: SearchRequest):
    """Search + generate a synthesized AI answer — convenience wrapper."""
    req.generate_answer = True
    return await search(req)


@app.get("/cases/{case_id}")
async def get_case(case_id: str):
    """Get full details for a specific case."""
    if not engine:
        raise HTTPException(503, "Search engine not ready")

    async with engine.pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT case_id, year, title, petitioner, respondent,
                   date_of_judgment::TEXT, bench, court, disposal_nature,
                   citation, pdf_url, acts_mentioned, full_text, created_at
            FROM cases WHERE case_id = $1
            """,
            case_id,
        )

    if not row:
        raise HTTPException(404, f"Case {case_id!r} not found")

    return dict(row)


@app.get("/cases/{case_id}/pdf")
async def get_case_pdf(case_id: str):
    """Redirect to the original PDF on S3."""
    if not engine:
        raise HTTPException(503)

    async with engine.pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT pdf_url FROM cases WHERE case_id = $1", case_id
        )

    if not row or not row["pdf_url"]:
        raise HTTPException(404, "PDF not found")

    return RedirectResponse(row["pdf_url"])


@app.get("/stats")
async def stats():
    """Return ingestion statistics."""
    if not engine:
        raise HTTPException(503)

    async with engine.pool.acquire() as conn:
        total_cases = await conn.fetchval("SELECT COUNT(*) FROM cases")
        total_chunks = await conn.fetchval("SELECT COUNT(*) FROM chunks")
        years = await conn.fetch(
            "SELECT year, COUNT(*) AS cnt FROM cases GROUP BY year ORDER BY year DESC"
        )
        popular = await conn.fetch(
            """
            SELECT query, COUNT(*) AS cnt
            FROM search_logs
            GROUP BY query ORDER BY cnt DESC LIMIT 10
            """
        )

    return {
        "total_cases": total_cases,
        "total_chunks": total_chunks,
        "years": {r["year"]: r["cnt"] for r in years},
        "popular_queries": [{"query": r["query"], "count": r["cnt"]} for r in popular],
    }


@app.get("/filters/years")
async def get_years():
    if not engine:
        raise HTTPException(503)
    async with engine.pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT DISTINCT year FROM cases ORDER BY year DESC"
        )
    return [r["year"] for r in rows]


@app.get("/filters/disposals")
async def get_disposals():
    if not engine:
        raise HTTPException(503)
    async with engine.pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT disposal_nature, COUNT(*) AS cnt
            FROM cases
            WHERE disposal_nature IS NOT NULL
            GROUP BY disposal_nature
            ORDER BY cnt DESC
            LIMIT 30
            """
        )
    return [{"value": r["disposal_nature"], "count": r["cnt"]} for r in rows]


# ─── WebSocket chat ───────────────────────────────────────────────

@app.websocket("/chat")
async def chat_ws(websocket: WebSocket):
    """
    Streaming conversational interface.
    Client sends: {"query": "...", "history": [...], "year": null, "disposal": null}
    Server streams back text tokens.
    """
    import json

    await websocket.accept()

    try:
        while True:
            data = await websocket.receive_text()
            payload = json.loads(data)
            query = payload.get("query", "")
            history = payload.get("history", [])
            year_filter = payload.get("year")
            disposal_filter = payload.get("disposal")

            if not query or not engine:
                await websocket.send_text(json.dumps({"error": "invalid query"}))
                continue

            # Search first
            embedding = await embed_query(query, engine.openai, engine.embedding_model)

            async with engine.pool.acquire() as conn:
                await register_vector(conn)
                from search.engine import vector_search, fulltext_search, reciprocal_rank_fusion, deduplicate_by_case
                vr, br = await asyncio.gather(
                    vector_search(conn, embedding, 20, year_filter, disposal_filter),
                    fulltext_search(conn, query, 20, year_filter, disposal_filter),
                )

            fused = reciprocal_rank_fusion(vr, br)
            deduped = deduplicate_by_case(fused, 6)

            # Send search results first
            await websocket.send_text(json.dumps({
                "type": "results",
                "results": [
                    {
                        "case_id": r["case_id"],
                        "title": r.get("title", ""),
                        "year": r.get("year"),
                        "score": round(r.get("fused_score", 0), 4),
                    }
                    for r in deduped
                ],
            }))

            # Build context
            context = "\n\n---\n\n".join(
                f"[{r.get('title', r['case_id'])} ({r.get('year', '')})]\n{r['chunk_text']}"
                for r in deduped[:6]
            )

            # Build conversation messages
            messages = []
            for h in history[-6:]:  # keep last 6 turns
                messages.append({"role": h["role"], "content": h["content"]})

            messages.append({
                "role": "user",
                "content": f"Context from Supreme Court judgments:\n{context}\n\nQuestion: {query}",
            })

            # Stream Claude response
            from search.engine import RAG_SYSTEM_PROMPT
            async with engine.anthropic.messages.stream(
                model=engine.rag_model,
                max_tokens=engine.rag_max_tokens,
                system=RAG_SYSTEM_PROMPT,
                messages=messages,
            ) as stream:
                async for token in stream.text_stream:
                    await websocket.send_text(json.dumps({"type": "token", "text": token}))

            await websocket.send_text(json.dumps({"type": "done"}))

    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        await websocket.close()


import asyncio  # noqa
from search.engine import embed_query  # noqa
