import os

# Get password from env
password = os.environ.get('POSTGRES_PASSWORD', 'change_me')
user = os.environ.get('POSTGRES_USER', 'court_admin')
host = os.environ.get('POSTGRES_HOST', 'postgres')
db = os.environ.get('POSTGRES_DB', 'court_search')

print(f"DSN: postgresql://{user}:***@{host}:5432/{db}")

import argparse
import asyncio
import logging
import tarfile
import sys
import os
from pathlib import Path

import boto3
import pandas as pd
from botocore import UNSIGNED
from botocore.config import Config
from openai import OpenAI
import asyncpg
from pgvector.asyncpg import register_vector

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DATA_DIR = Path("/app/data")
BUCKET = "indian-supreme-court-judgments"

def get_dsn():
    user = os.environ.get('POSTGRES_USER', 'court_admin')
    password = os.environ.get('POSTGRES_PASSWORD', 'change_me')
    host = os.environ.get('POSTGRES_HOST', 'postgres')
    port = os.environ.get('POSTGRES_PORT', '5432')
    db = os.environ.get('POSTGRES_DB', 'court_search')
    return f"postgresql://{{user}}:{{password}}@{{host}}:{{port}}/{{db}}"

def get_openai_key():
    return os.environ.get('OPENAI_API_KEY', 'dummy')

def get_embedding_model():
    return os.environ.get('EMBEDDING_MODEL', 'text-embedding-3-small')

def get_s3():
    return boto3.client("s3", region_name="ap-south-1", config=Config(signature_version=UNSIGNED))

def download_file(s3, key, dest):
    dest = Path(dest)
    if dest.exists():
        logger.info(f"Already exists: {{dest}}")
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    logger.info(f"Downloading {{key}}...")
    s3.download_file(BUCKET, key, str(dest))
    logger.info(f"Downloaded: {{dest}}")
    return dest

def extract_tar(tar_path, dest_dir):
    dest_dir = Path(dest_dir)
    if dest_dir.exists() and any(dest_dir.iterdir()):
        logger.info(f"Already extracted: {{dest_dir}}")
        return dest_dir
    dest_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Extracting {{tar_path}}...")
    with tarfile.open(tar_path, "r") as tar:
        tar.extractall(path=dest_dir)
    logger.info(f"Extracted to {{dest_dir}}")
    return dest_dir

def extract_text(pdf_path):
    try:
        import fitz
        doc = fitz.open(str(pdf_path))
        text = "\\n\\n".join(page.get_text() for page in doc)
        doc.close()
        return text.strip() if len(text.strip()) > 100 else None
    except Exception as e:
        logger.warning(f"PDF failed {{pdf_path}}: {{e}}")
        return None

def chunk_text(text, chunk_size=800, overlap=100):
    words = text.split()
    chunks = []
    i = 0
    idx = 0
    while i < len(words):
        chunk = " ".join(words[i:i+chunk_size])
        chunks.append({{"chunk_index": idx, "chunk_text": chunk, "token_count": min(len(words[i:i+chunk_size]), chunk_size)}})
        i += chunk_size - overlap
        idx += 1
    return chunks

def embed_texts(texts, client, model):
    if not texts:
        return []
    try:
        response = client.embeddings.create(input=texts, model=model)
        return [item.embedding for item in response.data]
    except Exception as e:
        logger.error(f"Embedding failed: {{e}}")
        return [None] * len(texts)

async def process_year(year):
    s3 = get_s3()
    openai_key = get_openai_key()
    embedding_model = get_embedding_model()
    openai_client = OpenAI(api_key=openai_key)
    dsn = get_dsn()
    logger.info(f"Connecting to DB...")

    meta_path = download_file(s3, f"metadata/parquet/year={{year}}/metadata.parquet", DATA_DIR / f"metadata_{{year}}.parquet")
    df = pd.read_parquet(meta_path)
    logger.info(f"Year {{year}}: {{len(df)}} cases")

    df.columns = [c.lower().replace(" ", "_") for c in df.columns]
    df["case_id"] = df["case_id"].astype(str).str.strip().str.replace(" ", "_") + f"_{{year}}"
    df["pdf_filename"] = df["path"].astype(str) + "_EN.pdf"

    tar_path = download_file(s3, f"data/tar/year={{year}}/english/english.tar", DATA_DIR / f"english_{{year}}.tar")
    pdf_dir = extract_tar(tar_path, DATA_DIR / str(year))

    conn = await asyncpg.connect(dsn)
    await register_vector(conn)
    logger.info("DB connected!")

    processed = skipped = failed = 0

    for _, row in df.iterrows():
        case_id = row["case_id"]

        exists = await conn.fetchval("SELECT 1 FROM chunks WHERE case_id = $1 LIMIT 1", case_id)
        if exists:
            skipped += 1
            continue

        pdf_name = str(row["pdf_filename"])
        pdf_path = pdf_dir / pdf_name
        if not pdf_path.exists():
            found = list(pdf_dir.glob(pdf_name))
            if not found:
                logger.warning(f"PDF not found: {{pdf_name}}")
                failed += 1
                continue
            pdf_path = found[0]

        text = extract_text(pdf_path)
        if not text:
            logger.warning(f"No text: {{pdf_name}}")
            failed += 1
            continue

        try:
            petitioner = str(row.get("petitioner", ""))
            respondent = str(row.get("respondent", ""))
            title = str(row.get("title", petitioner + " vs " + respondent))
            date_val = pd.to_datetime(row.get("decision_date") or row.get("date_of_judgment"), errors="coerce", dayfirst=True)
            if pd.isna(date_val):
                date_val = None
            disposal = str(row.get("disposal_nature", ""))
            citation = str(row.get("citation", ""))
            pdf_url = f"https://indian-supreme-court-judgments.s3.ap-south-1.amazonaws.com/data/tar/year={{year}}/english/{{pdf_name}}"

            await conn.execute(
                '''INSERT INTO cases (case_id, year, title, petitioner, respondent,
                    date_of_judgment, disposal_nature, citation, pdf_url, full_text)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
                    ON CONFLICT (case_id) DO NOTHING''',
                case_id, year, title, petitioner, respondent,
                date_val, disposal, citation, pdf_url, text[:50000]
            )
        except Exception as e:
            logger.error(f"Case insert failed {{case_id}}: {{e}}")
            failed += 1
            continue

        chunks = chunk_text(text)
        if not chunks:
            failed += 1
            continue

        all_embeddings = []
        for i in range(0, len(chunks), 50):
            batch = [c["chunk_text"] for c in chunks[i:i+50]]
            all_embeddings.extend(embed_texts(batch, openai_client, embedding_model))

        await conn.execute("DELETE FROM chunks WHERE case_id = $1", case_id)
        inserted = 0
        for chunk, emb in zip(chunks, all_embeddings):
            if emb is None:
                continue
            try:
                await conn.execute(
                    '''INSERT INTO chunks (case_id, chunk_index, chunk_text, token_count, embedding)
                        VALUES ($1,$2,$3,$4,$5)''',
                    case_id, chunk["chunk_index"], chunk["chunk_text"], chunk["token_count"], emb
                )
                inserted += 1
            except Exception as e:
                logger.error(f"Chunk insert error: {{e}}")

        processed += 1
        logger.info(f"Year {{year}}: processed={{processed}} skipped={{skipped}} failed={{failed}} chunks={{inserted}}")

    await conn.close()
    logger.info(f"Year {{year}} DONE: processed={{processed}} skipped={{skipped}} failed={{failed}}")

async def main(years):
    for year in years:
        logger.info(f"Processing year {{year}}")
        await process_year(year)
    logger.info("All done!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--years", nargs="+", type=int, default=[2024])
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(args.years))