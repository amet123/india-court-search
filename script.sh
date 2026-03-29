#!/bin/bash
# Creates all project files directly on the Hostinger server
set -e
echo "Creating all project files..."

BASE="/root/india-court-search"
mkdir -p $BASE/backend/{ingestion,embeddings,search,api}
mkdir -p $BASE/frontend/{pages/cases,styles,public,components}
mkdir -p $BASE/infra
mkdir -p $BASE/docs
mkdir -p $BASE/scripts

# ── .env.example ─────────────────────────────────────────────
cat > $BASE/.env.example << 'EOF'
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=court_search
POSTGRES_USER=court_admin
POSTGRES_PASSWORD=change_me_strong_password
APP_ENV=production
SECRET_KEY=change_me_to_random_64chars
CORS_ORIGINS=http://localhost:3000
S3_BUCKET=indian-supreme-court-judgments
AWS_DEFAULT_REGION=ap-south-1
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
CHUNK_SIZE=800
CHUNK_OVERLAP=100
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_BATCH_SIZE=100
MAX_WORKERS=4
TOP_K_RESULTS=10
HYBRID_ALPHA=0.6
RAG_MODEL=claude-sonnet-4-6
RAG_MAX_TOKENS=2000
REDIS_URL=redis://redis:6379/0
NEXT_PUBLIC_API_URL=http://localhost:8000
EOF

# ── docker-compose.yml ────────────────────────────────────────
cat > $BASE/docker-compose.yml << 'EOF'
version: "3.9"
services:
  postgres:
    image: pgvector/pgvector:pg16
    container_name: court_postgres
    restart: unless-stopped
    environment:
      POSTGRES_DB: ${POSTGRES_DB:-court_search}
      POSTGRES_USER: ${POSTGRES_USER:-court_admin}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-change_me}
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./infra/init.sql:/docker-entrypoint-initdb.d/init.sql
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-court_admin}"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    container_name: court_redis
    restart: unless-stopped
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    command: redis-server --appendonly yes --maxmemory 512mb --maxmemory-policy allkeys-lru

  api:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: court_api
    restart: unless-stopped
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_started
    env_file: .env
    environment:
      - POSTGRES_HOST=postgres
      - REDIS_URL=redis://redis:6379/0
    ports:
      - "8000:8000"
    volumes:
      - ./data:/app/data

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
      args:
        NEXT_PUBLIC_API_URL: ${NEXT_PUBLIC_API_URL:-http://localhost:8000}
    container_name: court_frontend
    restart: unless-stopped
    depends_on:
      - api
    ports:
      - "3000:3000"
    environment:
      - NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL:-http://localhost:8000}

volumes:
  postgres_data:
  redis_data:
EOF

# ── backend/Dockerfile ────────────────────────────────────────
cat > $BASE/backend/Dockerfile << 'EOF'
FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev tesseract-ocr tesseract-ocr-eng poppler-utils \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
EOF

# ── frontend/Dockerfile ───────────────────────────────────────
cat > $BASE/frontend/Dockerfile << 'EOF'
FROM node:18-alpine
WORKDIR /app
COPY package.json ./
RUN npm install
COPY . .
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
EXPOSE 3000
CMD ["npm", "run", "dev"]
EOF

# ── frontend/next.config.js ───────────────────────────────────
cat > $BASE/frontend/next.config.js << 'EOF'
/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  reactStrictMode: true,
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000",
  },
};
module.exports = nextConfig;
EOF

# ── frontend/postcss.config.js ────────────────────────────────
cat > $BASE/frontend/postcss.config.js << 'EOF'
module.exports = { plugins: { tailwindcss: {}, autoprefixer: {} } };
EOF

# ── frontend/tailwind.config.js ───────────────────────────────
cat > $BASE/frontend/tailwind.config.js << 'EOF'
/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./pages/**/*.{js,ts,jsx,tsx}", "./components/**/*.{js,ts,jsx,tsx}"],
  theme: { extend: {} },
  plugins: [],
};
EOF

# ── frontend/tsconfig.json ────────────────────────────────────
cat > $BASE/frontend/tsconfig.json << 'EOF'
{
  "compilerOptions": {
    "target": "es5",
    "lib": ["dom", "dom.iterable", "esnext"],
    "allowJs": true,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "preserve",
    "incremental": true,
    "plugins": [{ "name": "next" }],
    "paths": { "@/*": ["./*"] }
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
  "exclude": ["node_modules"]
}
EOF

# ── frontend/package.json ─────────────────────────────────────
cat > $BASE/frontend/package.json << 'EOF'
{
  "name": "india-court-search-frontend",
  "version": "1.0.0",
  "private": true,
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "lint": "next lint"
  },
  "dependencies": {
    "next": "14.2.4",
    "react": "18.3.1",
    "react-dom": "18.3.1",
    "axios": "1.7.2",
    "clsx": "2.1.1",
    "lucide-react": "0.383.0",
    "react-markdown": "9.0.1",
    "remark-gfm": "4.0.0"
  },
  "devDependencies": {
    "@types/node": "20.14.9",
    "@types/react": "18.3.3",
    "@types/react-dom": "18.3.0",
    "autoprefixer": "10.4.19",
    "eslint": "8.57.0",
    "eslint-config-next": "14.2.4",
    "postcss": "8.4.39",
    "tailwindcss": "3.4.4",
    "typescript": "5.5.3"
  }
}
EOF

# ── frontend/styles/globals.css ───────────────────────────────
cat > $BASE/frontend/styles/globals.css << 'EOF'
@tailwind base;
@tailwind components;
@tailwind utilities;

mark {
  background: #fef08a;
  color: #713f12;
  border-radius: 2px;
  padding: 0 2px;
}

.line-clamp-3 {
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
EOF

# ── frontend/pages/_app.tsx ───────────────────────────────────
cat > $BASE/frontend/pages/_app.tsx << 'EOF'
import type { AppProps } from "next/app";
import "../styles/globals.css";
export default function App({ Component, pageProps }: AppProps) {
  return <Component {...pageProps} />;
}
EOF

# ── frontend/pages/index.tsx ──────────────────────────────────
cat > $BASE/frontend/pages/index.tsx << 'EOF'
"use client";
import { useState, useEffect } from "react";
import { Search, Scale, Loader2, X, Sparkles, ExternalLink } from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface CaseResult {
  case_id: string;
  year: number;
  title: string;
  petitioner?: string;
  respondent?: string;
  date_of_judgment?: string;
  disposal_nature?: string;
  bench?: string;
  citation?: string;
  pdf_url?: string;
  chunk_text: string;
  score: number;
}

interface SearchResponse {
  query: string;
  results: CaseResult[];
  answer?: string;
  latency_ms: number;
  total_results: number;
}

function CaseCard({ c, query }: { c: CaseResult; query: string }) {
  const [expanded, setExpanded] = useState(false);
  const highlight = (text: string) => {
    if (!query) return text;
    const words = query.split(/\s+/).filter(w => w.length > 3);
    if (!words.length) return text;
    return text.replace(new RegExp(`(${words.join("|")})`, "gi"), "<mark>$1</mark>");
  };
  return (
    <div className="border border-gray-200 rounded-xl p-5 hover:border-orange-300 hover:shadow-sm transition-all bg-white">
      <div className="flex items-center gap-2 flex-wrap mb-2">
        <span className="text-xs font-medium bg-orange-50 text-orange-700 px-2 py-0.5 rounded-full">{c.year}</span>
        {c.disposal_nature && (
          <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${
            c.disposal_nature.toLowerCase().includes("allow") ? "bg-green-50 text-green-700" :
            c.disposal_nature.toLowerCase().includes("dismiss") ? "bg-red-50 text-red-700" :
            "bg-gray-100 text-gray-600"}`}>{c.disposal_nature}</span>
        )}
        {c.citation && <span className="text-xs text-gray-500 font-mono">{c.citation}</span>}
        <span className="text-xs text-gray-400 ml-auto">Score: {(c.score * 100).toFixed(1)}%</span>
      </div>
      <h3 className="font-semibold text-gray-900 text-sm mb-1">{c.title || `${c.petitioner} vs ${c.respondent}`}</h3>
      {c.bench && <p className="text-xs text-gray-500 mb-2"><span className="font-medium">Bench:</span> {c.bench}</p>}
      <div
        className={`text-sm text-gray-600 leading-relaxed ${!expanded ? "line-clamp-3" : ""}`}
        dangerouslySetInnerHTML={{ __html: highlight(c.chunk_text) }}
      />
      <div className="flex items-center gap-3 mt-3">
        <button onClick={() => setExpanded(!expanded)} className="text-xs text-orange-600 hover:text-orange-700 font-medium">
          {expanded ? "Show less" : "Read more"}
        </button>
        {c.pdf_url && (
          <a href={`${API}/cases/${c.case_id}/pdf`} target="_blank" rel="noopener noreferrer"
            className="text-xs text-blue-600 hover:text-blue-700 font-medium flex items-center gap-1">
            <ExternalLink size={11} /> View PDF
          </a>
        )}
      </div>
    </div>
  );
}

export default function HomePage() {
  const [query, setQuery] = useState("");
  const [yearFilter, setYearFilter] = useState("");
  const [loading, setLoading] = useState(false);
  const [response, setResponse] = useState<SearchResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [generateAnswer, setGenerateAnswer] = useState(false);
  const [availableYears, setAvailableYears] = useState<number[]>([]);

  useEffect(() => {
    fetch(`${API}/filters/years`).then(r => r.json()).then(setAvailableYears).catch(() => {});
  }, []);

  const handleSearch = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!query.trim()) return;
    setLoading(true); setError(null); setResponse(null);
    try {
      const res = await fetch(`${API}/search`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: query.trim(), year: yearFilter ? parseInt(yearFilter) : undefined, generate_answer: generateAnswer }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setResponse(await res.json());
    } catch (err: any) {
      setError(err.message || "Search failed. Is the backend running?");
    } finally { setLoading(false); }
  };

  const examples = ["Right to privacy fundamental right", "Basic structure doctrine", "Bail conditions criminal cases", "Article 370 abrogation", "Land acquisition compensation"];

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200 sticky top-0 z-10">
        <div className="max-w-4xl mx-auto px-4 py-3 flex items-center gap-2">
          <Scale className="text-orange-500" size={22} />
          <span className="font-bold text-gray-900 text-lg">India Court Search</span>
          <span className="text-xs text-gray-400 ml-1 hidden sm:block">Supreme Court · 1950–2025 · AI-Powered</span>
        </div>
      </header>
      <main className="max-w-4xl mx-auto px-4 py-8">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-gray-900 mb-2">Search Supreme Court Judgments</h1>
          <p className="text-gray-500 text-sm">100,000+ judgments · Semantic AI search · Instant answers</p>
        </div>
        <form onSubmit={handleSearch} className="mb-6">
          <div className="flex gap-2 mb-3">
            <div className="relative flex-1">
              <Search size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
              <input type="text" value={query} onChange={e => setQuery(e.target.value)}
                placeholder="Search by legal principle, party name, statute…"
                className="w-full pl-10 pr-4 py-3 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-orange-300 bg-white shadow-sm" />
              {query && <button type="button" onClick={() => { setQuery(""); setResponse(null); }}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"><X size={16} /></button>}
            </div>
            <button type="submit" disabled={loading || !query.trim()}
              className="bg-orange-500 text-white px-6 py-3 rounded-xl font-medium hover:bg-orange-600 disabled:opacity-50 transition-colors shadow-sm flex items-center gap-2">
              {loading ? <Loader2 size={16} className="animate-spin" /> : <Search size={16} />} Search
            </button>
          </div>
          <div className="flex items-center gap-3 flex-wrap">
            <select value={yearFilter} onChange={e => setYearFilter(e.target.value)}
              className="text-sm border border-gray-200 rounded-lg px-3 py-1.5 bg-white focus:outline-none focus:ring-2 focus:ring-orange-300">
              <option value="">All years</option>
              {availableYears.map(y => <option key={y} value={y}>{y}</option>)}
            </select>
            <label className="flex items-center gap-1.5 text-sm text-gray-600 cursor-pointer ml-auto">
              <input type="checkbox" checked={generateAnswer} onChange={e => setGenerateAnswer(e.target.checked)} className="rounded" />
              <Sparkles size={13} className="text-orange-400" /> Generate AI answer
            </label>
          </div>
        </form>
        {!response && !loading && (
          <div className="mb-8">
            <p className="text-xs text-gray-400 mb-2">Try searching for:</p>
            <div className="flex flex-wrap gap-2">
              {examples.map(q => (
                <button key={q} onClick={() => setQuery(q)}
                  className="text-xs bg-white border border-gray-200 text-gray-600 px-3 py-1.5 rounded-full hover:border-orange-300 hover:text-orange-600 transition-colors">{q}</button>
              ))}
            </div>
          </div>
        )}
        {error && <div className="bg-red-50 border border-red-200 text-red-700 rounded-xl px-4 py-3 text-sm mb-6">{error}</div>}
        {response && (
          <div>
            <p className="text-sm text-gray-500 mb-4">
              <span className="font-medium text-gray-900">{response.total_results}</span> results · {response.latency_ms}ms
            </p>
            {response.answer && (
              <div className="bg-orange-50 border border-orange-200 rounded-xl p-5 mb-5">
                <div className="flex items-center gap-2 mb-2">
                  <Sparkles size={14} className="text-orange-500" />
                  <span className="text-sm font-semibold text-orange-800">AI Answer</span>
                </div>
                <p className="text-sm text-gray-800 leading-relaxed whitespace-pre-wrap">{response.answer}</p>
              </div>
            )}
            <div className="space-y-3">
              {response.results.map(c => <CaseCard key={c.case_id} c={c} query={query} />)}
            </div>
            {response.results.length === 0 && (
              <div className="text-center py-12 text-gray-400">
                <Scale size={40} className="mx-auto mb-3 text-gray-200" />
                <p>No judgments found. Try a different search term.</p>
              </div>
            )}
          </div>
        )}
        {!response && !loading && !error && (
          <div className="text-center py-16 text-gray-300">
            <Scale size={60} className="mx-auto mb-4" />
            <p className="text-gray-400 text-sm">Search across 100,000+ Supreme Court judgments</p>
          </div>
        )}
      </main>
    </div>
  );
}
EOF

# ── backend/requirements.txt ──────────────────────────────────
cat > $BASE/backend/requirements.txt << 'EOF'
fastapi==0.111.0
uvicorn[standard]==0.30.1
pydantic==2.7.1
pydantic-settings==2.3.0
python-dotenv==1.0.1
asyncpg==0.29.0
sqlalchemy[asyncio]==2.0.30
pgvector==0.3.1
psycopg2-binary==2.9.9
boto3==1.34.131
botocore==1.34.131
PyMuPDF==1.24.5
pdfplumber==0.11.1
pytesseract==0.3.10
Pillow==10.3.0
langchain==0.2.5
langchain-community==0.2.5
langchain-openai==0.1.8
langchain-anthropic==0.1.15
tiktoken==0.7.0
openai==1.35.3
anthropic==0.29.0
numpy==1.26.4
pandas==2.2.2
pyarrow==16.1.0
tqdm==4.66.4
aiofiles==23.2.1
httpx==0.27.0
redis==5.0.6
hiredis==2.3.2
structlog==24.2.0
EOF

# ── backend/config.py ─────────────────────────────────────────
cat > $BASE/backend/config.py << 'EOF'
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_env: str = "development"
    secret_key: str = "change_me"
    cors_origins: str = "http://localhost:3000"
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "court_search"
    postgres_user: str = "court_admin"
    postgres_password: str = "change_me"
    s3_bucket: str = "indian-supreme-court-judgments"
    aws_default_region: str = "ap-south-1"
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    chunk_size: int = 800
    chunk_overlap: int = 100
    embedding_model: str = "text-embedding-3-small"
    embedding_batch_size: int = 100
    max_workers: int = 4
    top_k_results: int = 10
    hybrid_alpha: float = 0.6
    rag_model: str = "claude-sonnet-4-6"
    rag_max_tokens: int = 2000
    redis_url: str = "redis://localhost:6379/0"

    @property
    def database_url(self):
        return f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"

@lru_cache
def get_settings():
    return Settings()
EOF

# ── __init__.py files ─────────────────────────────────────────
touch $BASE/backend/__init__.py
touch $BASE/backend/ingestion/__init__.py
touch $BASE/backend/embeddings/__init__.py
touch $BASE/backend/search/__init__.py
touch $BASE/backend/api/__init__.py

# ── infra/init.sql ────────────────────────────────────────────
cat > $BASE/infra/init.sql << 'EOF'
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS cases (
    id                  BIGSERIAL PRIMARY KEY,
    case_id             TEXT UNIQUE NOT NULL,
    year                INTEGER NOT NULL,
    title               TEXT,
    petitioner          TEXT,
    respondent          TEXT,
    date_of_judgment    DATE,
    bench               TEXT,
    court               TEXT DEFAULT 'Supreme Court of India',
    disposal_nature     TEXT,
    citation            TEXT,
    s3_key              TEXT,
    pdf_url             TEXT,
    full_text           TEXT,
    summary             TEXT,
    acts_mentioned      TEXT[],
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS chunks (
    id              BIGSERIAL PRIMARY KEY,
    case_id         TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
    chunk_index     INTEGER NOT NULL,
    chunk_text      TEXT NOT NULL,
    token_count     INTEGER,
    embedding       vector(1536),
    ts_vector       tsvector,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (case_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_cases_year       ON cases(year);
CREATE INDEX IF NOT EXISTS idx_cases_disposal   ON cases(disposal_nature);
CREATE INDEX IF NOT EXISTS idx_cases_petitioner ON cases USING gin(petitioner gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_chunks_embedding ON chunks USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);
CREATE INDEX IF NOT EXISTS idx_chunks_ts        ON chunks USING gin(ts_vector);

CREATE TABLE IF NOT EXISTS search_logs (
    id          BIGSERIAL PRIMARY KEY,
    query       TEXT NOT NULL,
    results     INTEGER,
    latency_ms  INTEGER,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

SELECT 'Schema ready.' AS status;
EOF

# ── Makefile ──────────────────────────────────────────────────
cat > $BASE/Makefile << 'EOF'
.PHONY: up down logs ingest status

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f

ingest:
	docker compose exec api python -m ingestion.pipeline --years 2022 2023 2024

ingest-all:
	docker compose exec api python -m ingestion.pipeline --all

status:
	curl -s http://localhost:8000/stats | python3 -m json.tool
EOF

echo ""
echo "================================================"
echo "  All files created successfully!"
echo "  Run: cd /root/india-court-search && ls -la"
echo "================================================"
