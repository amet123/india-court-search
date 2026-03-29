# Deployment Guide — India Court Search Engine

## Prerequisites

Make sure your server has:
- **Docker** >= 24.x + **Docker Compose** >= 2.x
- **4 GB RAM minimum** (8 GB recommended for full dataset)
- **50 GB disk** for full 1950–2025 dataset (start with 10 GB for 3 years)
- Ports **3000**, **8000**, **5432** available (or use Nginx on port 80)

---

## Step 1 — Clone & configure

```bash
git clone <your-repo> india-court-search
cd india-court-search

# Create your .env file
make setup
# Now open .env and fill in your keys:
nano .env
```

**Required keys in .env:**
```
OPENAI_API_KEY=sk-...          ← for embeddings (text-embedding-3-small)
ANTHROPIC_API_KEY=sk-ant-...   ← for AI answers (Claude)
POSTGRES_PASSWORD=<strong-password>
```

---

## Step 2 — Start infrastructure

```bash
make up
```

This starts:
- PostgreSQL 16 + pgvector (port 5432)
- Redis 7 (port 6379)
- FastAPI backend (port 8000)
- Next.js frontend (port 3000)

Wait ~30 seconds for services to initialize, then verify:
```bash
curl http://localhost:8000/health
# → {"status":"ok","version":"1.0.0"}
```

---

## Step 3 — Run your first ingestion

Start small — 3 years is enough to validate everything (~3-5 GB download):

```bash
make ingest
# Downloads and processes: 2022, 2023, 2024
# Takes ~30-60 minutes depending on internet speed + hardware
```

Check progress:
```bash
make status
```

You'll see something like:
```json
{
  "total_cases": 12450,
  "total_chunks": 187340,
  "years": { "2022": 4200, "2023": 4150, "2024": 4100 }
}
```

---

## Step 4 — Open the search engine

```
http://localhost:3000
```

Try a search like: `"right to privacy as fundamental right"`

---

## Step 5 — Ingest more years (optional)

```bash
# Specific years
make ingest-years
# Enter: 2018 2019 2020 2021

# All years 1950–2025 (takes 6-12 hours, ~100k judgments)
make ingest-all
```

**Recommended ingestion order** (most recent first, as they're most searched):
```bash
docker-compose exec api python -m ingestion.pipeline --years \
  2024 2023 2022 2021 2020 2019 2018 2017 2016 2015
```

---

## Step 6 — Production hardening

### Use Nginx as reverse proxy
```bash
# Add nginx to docker-compose.yml or run separately:
docker run -d \
  -p 80:80 \
  -v $(pwd)/infra/nginx.conf:/etc/nginx/conf.d/default.conf \
  --network india-court-search_default \
  --name court-nginx \
  nginx:alpine
```

### Enable HTTPS with Certbot
```bash
apt install certbot python3-certbot-nginx
certbot --nginx -d yourdomain.com
```

### Set strong passwords in .env
```
POSTGRES_PASSWORD=<64-char random string>
SECRET_KEY=<64-char random string>
```

---

## Monitoring

### View logs
```bash
make logs                         # all services
docker-compose logs -f api        # API only
docker-compose logs -f postgres   # DB only
```

### Check DB directly
```bash
make shell-db

# Inside psql:
SELECT year, COUNT(*) FROM cases GROUP BY year ORDER BY year;
SELECT COUNT(*) FROM chunks;
\q
```

### Popular queries
```bash
curl http://localhost:8000/stats | python3 -m json.tool
```

---

## Cost Estimates

### OpenAI Embeddings (text-embedding-3-small)
- ~$0.02 per 1M tokens
- Average judgment ≈ 5,000 tokens → ~500 chunks of 800 tokens
- 100,000 judgments × 5,000 tokens = 500M tokens total
- **Estimated cost: ~$10 for full dataset**

### Anthropic Claude (per search with AI answer)
- claude-sonnet-4-6: ~$3 per 1M input tokens
- Each RAG query sends ~4,000 tokens of context
- 1,000 queries × 4,000 tokens = 4M tokens → ~$12
- **Estimate: ~$0.012 per AI-answered query**

### Storage
- PostgreSQL with full dataset: ~20-30 GB
- Raw PDFs (if kept): ~50 GB

---

## Troubleshooting

**"Connection refused" on port 8000**
```bash
docker-compose logs api   # check for Python import errors
docker-compose restart api
```

**Embedding errors during ingestion**
- Check your OPENAI_API_KEY is valid
- Check your rate limits: add `--no-skip` flag to retry failed cases

**pgvector extension not found**
```bash
# Make sure you're using the pgvector image, not plain postgres:
docker-compose exec postgres psql -U court_admin -d court_search -c "CREATE EXTENSION vector;"
```

**Out of disk space**
```bash
# Clean up downloaded tar files after ingestion:
find ./data/pdfs -name "*.tar" -delete
```

**Slow search**
- The HNSW index is built automatically on insert
- For fastest search, rebuild after bulk ingestion:
```sql
REINDEX INDEX CONCURRENTLY idx_chunks_embedding;
```
