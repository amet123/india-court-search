# 🏛️ India Court Search Engine — AI-Powered

A full-stack, self-hosted AI search engine over Indian Supreme Court judgments (1950–2025).

## Architecture

```
S3 (Public Dataset)
    ↓
Ingestion Pipeline (Python)
    ↓
Text Extraction + Chunking
    ↓
Embeddings (OpenAI / local)
    ↓
pgvector (PostgreSQL) — Vector + Full-text hybrid store
    ↓
FastAPI Backend — Hybrid search + RAG with Claude
    ↓
Next.js Frontend — Search UI + Chat interface
```

## Tech Stack

| Layer | Technology |
|---|---|
| Dataset | AWS S3 public bucket (no auth needed) |
| PDF extraction | PyMuPDF + pdfplumber |
| Chunking | LangChain RecursiveCharacterTextSplitter |
| Embeddings | OpenAI text-embedding-3-small |
| Vector DB | PostgreSQL + pgvector (self-hosted) |
| Full-text search | PostgreSQL tsvector (BM25-like) |
| LLM / RAG | Anthropic Claude (claude-sonnet-4-6) |
| API | FastAPI (Python) |
| Frontend | Next.js 14 + Tailwind CSS |
| Infrastructure | Docker Compose (self-hosted) |

---

## Prerequisites

- Docker + Docker Compose
- Python 3.11+
- Node.js 18+
- OpenAI API key (for embeddings)
- Anthropic API key (for RAG answers)
- ~50GB disk space for full dataset (start with 2-3 years)

---

## Quick Start

### 1. Clone & configure

```bash
git clone <your-repo>
cd india-court-search
cp .env.example .env
# Edit .env with your API keys
```

### 2. Start infrastructure

```bash
docker-compose up -d
# Starts PostgreSQL with pgvector
```

### 3. Run ingestion (start with 2-3 years)

```bash
cd backend
pip install -r requirements.txt

# Download + process 2022-2024 judgments
python -m ingestion.pipeline --years 2022 2023 2024

# This will:
# 1. Download metadata.parquet for each year
# 2. Download english.tar for each year
# 3. Extract text from PDFs
# 4. Chunk + embed + store in pgvector
```

### 4. Start API

```bash
uvicorn api.main:app --reload --port 8000
```

### 5. Start Frontend

```bash
cd frontend
npm install
npm run dev
# Open http://localhost:3000
```

---

## Dataset Structure

```
s3://indian-supreme-court-judgments/
├── metadata/
│   └── parquet/
│       └── year=YYYY/
│           └── metadata.parquet      ← case info (petitioner, respondent, date, etc.)
└── data/
    └── tar/
        └── year=YYYY/
            └── english/
                └── english.tar       ← PDFs for that year
```

---

## Scaling to Full Dataset

The dataset has ~100k+ judgments. Recommended approach:

1. Start with 5 years (~5-10GB) to validate the pipeline
2. Run ingestion year by year in parallel
3. Use pgvector's HNSW index for fast ANN search at scale
4. Add Redis caching for popular queries

---

## Features

- **Semantic search** — find judgments by legal concept, not just keywords
- **Hybrid search** — BM25 + vector search combined
- **Faceted filters** — filter by year, disposal type, bench, petitioner
- **AI answers** — Claude synthesizes answers with case citations
- **Chat interface** — conversational legal research
- **Citation graph** — see related cases

---

## License

Dataset: [Indian Supreme Court Judgments](https://github.com/vanga/indian-supreme-court-judgments) — open access.
