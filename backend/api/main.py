import logging
from contextlib import asynccontextmanager
from typing import Optional, List, Dict
import re
import anthropic
import asyncpg
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwt
from openai import AsyncOpenAI
from pgvector.asyncpg import register_vector
from pydantic import BaseModel, Field
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import get_settings
from auth.router import router as auth_router
from payments.router import router as payments_router
from admin.router import router as admin_router
from middleware.plan_check import check_search_limit, check_ai_credits, deduct_credit, log_search, get_llm_model, get_plan_features

logger = logging.getLogger(__name__)
settings = get_settings()
_security = HTTPBearer(auto_error=False)

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(_security), request: Request = None):
    if not credentials:
        return None
    try:
        payload = jwt.decode(credentials.credentials, "bharatlawfinder_secret_change_in_production", algorithms=["HS256"])
        user_id = int(payload["sub"])
    except Exception:
        return None
    try:
        pool = request.app.state.pool
        async with pool.acquire() as conn:
            sql = "SELECT u.id, u.email, u.full_name, u.is_admin, u.is_active, u.credits_used, u.credits_reset, p.name AS plan_name, p.display_name AS plan_display, p.credits_monthly, p.searches_daily, p.llm_model, p.features, s.expires_at AS subscription_expires FROM users u JOIN plans p ON p.id = u.plan_id LEFT JOIN subscriptions s ON s.user_id = u.id AND s.status = $2 WHERE u.id = $1 AND u.is_active = TRUE"
            user = await conn.fetchrow(sql, user_id, "active")
        return dict(user) if user else None
    except Exception:
        return None

@asynccontextmanager
async def lifespan(app: FastAPI):
    dsn = "postgresql://{}:{}@{}:{}/{}".format(settings.postgres_user, settings.postgres_password, settings.postgres_host, settings.postgres_port, settings.postgres_db)
    async def init_conn(conn):
        await register_vector(conn)
    pool = await asyncpg.create_pool(dsn, min_size=2, max_size=10, init=init_conn)
    app.state.pool = pool
    app.state.settings = settings
    app.state.openai = AsyncOpenAI(api_key=settings.openai_api_key)
    if settings.anthropic_api_key and settings.anthropic_api_key != "dummy":
        app.state.anthropic = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    else:
        app.state.anthropic = None
    yield
    await pool.close()

app = FastAPI(title="BharatLawFinder API", version="2.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(auth_router)
app.include_router(payments_router)
app.include_router(admin_router)

class SearchRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=500)
    year: Optional[int] = Field(None, ge=1950, le=2025)
    disposal: Optional[str] = None
    generate_answer: bool = False

class SegmentSpan(BaseModel):
    type: str
    label: str
    start_para: int
    end_para: int
    confidence: float
    preview: str

class CaseSegmentsResponse(BaseModel):
    case_id: str
    total_paragraphs: int
    segments: List[SegmentSpan]

class PrecedentItem(BaseModel):
    precedent: str
    mention_count: int
    paragraphs: List[int]

class CasePrecedentsResponse(BaseModel):
    case_id: str
    total_mentions: int
    precedents: List[PrecedentItem]

@app.get("/health")
async def health():
    return {"status": "ok", "version": "2.0.0"}

@app.get("/stats")
async def stats(request: Request):
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        total_cases = await conn.fetchval("SELECT COUNT(*) FROM cases") or 0
        total_chunks = await conn.fetchval("SELECT COUNT(*) FROM chunks") or 0
        years = await conn.fetch("SELECT year, COUNT(*) AS cnt FROM cases GROUP BY year ORDER BY year DESC")
    return {"total_cases": total_cases, "total_chunks": total_chunks, "years": {r["year"]: r["cnt"] for r in years}, "popular_queries": []}

@app.post("/search")
async def search(req: SearchRequest, request: Request, user: Optional[dict] = Depends(get_current_user)):
    pool = request.app.state.pool
    if not user:
        rows = await _keyword_search(pool, req.query, req.year, req.disposal, limit=5)
        return {"query": req.query, "results": rows, "answer": None, "latency_ms": 0, "total_results": len(rows), "guest": True}
    await check_search_limit(user, pool)
    await log_search(user["id"], pool, req.query, request.client.host if request.client else "")
    features = get_plan_features(user)
    if features["semantic_search"] and settings.openai_api_key != "dummy":
        rows = await _semantic_search(request, pool, req.query, req.year, req.disposal)
    else:
        rows = await _keyword_search(pool, req.query, req.year, req.disposal)
    answer = None
    if req.generate_answer and features["ai_answers"]:
        await check_ai_credits(user, pool)
        model = get_llm_model(user)
        if model and request.app.state.anthropic:
            answer = await _generate_answer(request, req.query, rows, model)
            await deduct_credit(user["id"], pool, "ai_answer", model, req.query)
    return {"query": req.query, "results": rows, "answer": answer, "latency_ms": 0, "total_results": len(rows)}

async def _keyword_search(pool, query, year=None, disposal=None, limit=10):
    conditions = ["ch.ts_vector @@ plainto_tsquery($2, $1)"]
    params = [query, "english"]
    if year:
        params.append(year)
        conditions.append("c.year = $" + str(len(params)))
    if disposal:
        params.append("%" + disposal + "%")
        conditions.append("c.disposal_nature ILIKE $" + str(len(params)))
    params.append(limit)
    where = " AND ".join(conditions)
    sql = "SELECT c.case_id, c.year, c.title, c.petitioner, c.respondent, c.date_of_judgment::TEXT, c.disposal_nature, c.bench, c.citation, c.pdf_url, ch.chunk_text, ts_rank_cd(ch.ts_vector, plainto_tsquery($2, $1)) AS score FROM chunks ch JOIN cases c ON c.case_id = ch.case_id WHERE " + where + " ORDER BY score DESC LIMIT $" + str(len(params))
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, *params)
    return _format_results(rows)

def _format_results(rows):
    seen = set()
    results = []
    for r in rows:
        if r["case_id"] not in seen:
            seen.add(r["case_id"])
            results.append({"case_id": r["case_id"], "year": r["year"], "title": r["title"] or "", "petitioner": r["petitioner"], "respondent": r["respondent"], "date_of_judgment": r["date_of_judgment"], "disposal_nature": r["disposal_nature"], "bench": r["bench"], "citation": r["citation"], "pdf_url": r["pdf_url"], "chunk_text": r["chunk_text"], "score": round(float(r["score"]), 4)})
    return results

async def _generate_answer(request, query, results, model):
    parts = []
    for r in results[:6]:
        parts.append("[" + str(r.get("title", "")) + " (" + str(r.get("year", "")) + ")]" + chr(10) + str(r["chunk_text"]))
    context = (chr(10) + chr(10)).join(parts)
    try:
        resp = await request.app.state.anthropic.messages.create(model=model, max_tokens=1500, system="You are an expert Indian legal research assistant.", messages=[{"role": "user", "content": "Question: " + query + chr(10) + chr(10) + "Context: " + context}])
        return resp.content[0].text
    except Exception as e:
        return "AI answer abhi available nahi hai."

def _split_paragraphs(text: str) -> List[str]:
    if not text:
        return []
    parts = [p.strip() for p in re.split(r"\n\s*\n+", text) if p.strip()]
    if parts:
        return parts
    return [p.strip() for p in text.split("\n") if p.strip()]

def _normalize_label(label: str) -> str:
    mapping = {
        "facts": "Facts",
        "issues": "Issues",
        "petitioner_arguments": "Petitioner's Arguments",
        "respondent_arguments": "Respondent's Arguments",
        "analysis_of_law": "Analysis of the Law",
        "precedent_analysis": "Precedent Analysis",
        "court_reasoning": "Court's Reasoning",
        "conclusion": "Conclusion",
    }
    return mapping.get(label, label.replace("_", " ").title())

def _guess_segment_type(paragraph: str) -> str:
    p = paragraph.lower()
    if any(k in p for k in ["facts of the case", "brief facts", "factual matrix"]):
        return "facts"
    if any(k in p for k in ["issue for consideration", "points for determination", "the issue is"]):
        return "issues"
    if any(k in p for k in ["learned counsel for the petitioner", "petitioner contends", "for the petitioner"]):
        return "petitioner_arguments"
    if any(k in p for k in ["learned counsel for the respondent", "respondent contends", "for the respondent", "state submits"]):
        return "respondent_arguments"
    if any(k in p for k in ["article", "section", "statute", "constitution", "interpretation"]):
        return "analysis_of_law"
    if any(k in p for k in ["relied on", "cited", "precedent", "in the case of", "vs."]):
        return "precedent_analysis"
    if any(k in p for k in ["we hold", "in our view", "therefore", "it follows", "we are of the opinion"]):
        return "court_reasoning"
    if any(k in p for k in ["appeal is dismissed", "appeal is allowed", "disposed of", "ordered accordingly"]):
        return "conclusion"
    return "analysis_of_law"

def _build_segments(case_id: str, text: str) -> CaseSegmentsResponse:
    paras = _split_paragraphs(text)
    if not paras:
        return CaseSegmentsResponse(case_id=case_id, total_paragraphs=0, segments=[])
    segments: List[SegmentSpan] = []
    start = 1
    current_type = _guess_segment_type(paras[0])
    for idx, paragraph in enumerate(paras, start=1):
        guessed = _guess_segment_type(paragraph)
        if guessed != current_type:
            prev_idx = idx - 1
            preview = paras[start - 1][:280]
            segments.append(
                SegmentSpan(
                    type=current_type,
                    label=_normalize_label(current_type),
                    start_para=start,
                    end_para=prev_idx,
                    confidence=0.72,
                    preview=preview,
                )
            )
            start = idx
            current_type = guessed
    preview = paras[start - 1][:280]
    segments.append(
        SegmentSpan(
            type=current_type,
            label=_normalize_label(current_type),
            start_para=start,
            end_para=len(paras),
            confidence=0.72,
            preview=preview,
        )
    )
    return CaseSegmentsResponse(case_id=case_id, total_paragraphs=len(paras), segments=segments)

def _extract_precedents(case_id: str, text: str) -> CasePrecedentsResponse:
    paras = _split_paragraphs(text)
    precedent_map: Dict[str, Dict[str, object]] = {}
    pattern = re.compile(r"([A-Z][A-Za-z0-9&.,' -]{2,80}\s+v(?:s\.?|\.?)\s+[A-Z][A-Za-z0-9&.,' -]{2,80})")
    for idx, para in enumerate(paras, start=1):
        matches = pattern.findall(para)
        for m in matches:
            key = " ".join(m.split())
            if key not in precedent_map:
                precedent_map[key] = {"mention_count": 0, "paragraphs": []}
            precedent_map[key]["mention_count"] = int(precedent_map[key]["mention_count"]) + 1
            precedent_map[key]["paragraphs"].append(idx)
    precedents = [
        PrecedentItem(precedent=name, mention_count=int(data["mention_count"]), paragraphs=data["paragraphs"][:30])
        for name, data in sorted(precedent_map.items(), key=lambda kv: int(kv[1]["mention_count"]), reverse=True)[:50]
    ]
    total = sum(p.mention_count for p in precedents)
    return CasePrecedentsResponse(case_id=case_id, total_mentions=total, precedents=precedents)

@app.get("/filters/years")
async def get_years(request: Request):
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT DISTINCT year FROM cases ORDER BY year DESC")
    return [r["year"] for r in rows]

@app.get("/filters/disposals")
async def get_disposals(request: Request):
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT disposal_nature, COUNT(*) AS cnt FROM cases WHERE disposal_nature IS NOT NULL GROUP BY disposal_nature ORDER BY cnt DESC LIMIT 20")
    return [{"value": r["disposal_nature"], "count": r["cnt"]} for r in rows]

@app.get("/cases/{case_id}")
async def get_case(case_id: str, request: Request, user: Optional[dict] = Depends(get_current_user)):
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM cases WHERE case_id = $1", case_id)
    if not row:
        raise HTTPException(404, "Case not found")
    data = dict(row)
    if not user or user.get("plan_name") == "free":
        data.pop("full_text", None)
    return data

@app.get("/cases/{case_id}/pdf")
async def get_case_pdf(case_id: str, request: Request, user: Optional[dict] = Depends(get_current_user)):
    if not user:
        raise HTTPException(401, "Login required")
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT pdf_url FROM cases WHERE case_id = $1", case_id)
    if not row or not row["pdf_url"]:
        raise HTTPException(404, "PDF not found")
    from fastapi.responses import RedirectResponse
    return RedirectResponse(row["pdf_url"])

@app.get("/cases/{case_id}/segments", response_model=CaseSegmentsResponse)
async def get_case_segments(case_id: str, request: Request, user: Optional[dict] = Depends(get_current_user)):
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT case_id, full_text FROM cases WHERE case_id = $1", case_id)
    if not row:
        raise HTTPException(404, "Case not found")
    text = row["full_text"] or ""
    return _build_segments(case_id, text)

@app.get("/cases/{case_id}/precedents", response_model=CasePrecedentsResponse)
async def get_case_precedents(case_id: str, request: Request, user: Optional[dict] = Depends(get_current_user)):
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT case_id, full_text FROM cases WHERE case_id = $1", case_id)
    if not row:
        raise HTTPException(404, "Case not found")
    text = row["full_text"] or ""
    return _extract_precedents(case_id, text)
