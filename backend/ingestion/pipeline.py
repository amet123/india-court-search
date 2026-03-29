import argparse
import asyncio
import logging
import tarfile
import sys
from pathlib import Path

import boto3
import pandas as pd
from botocore import UNSIGNED
from botocore.config import Config
from openai import OpenAI
import asyncpg
from pgvector.asyncpg import register_vector

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

settings = get_settings()
DATA_DIR = Path("/app/data")
BUCKET = "indian-supreme-court-judgments"


def get_s3():
    return boto3.client("s3", region_name="ap-south-1", config=Config(signature_version=UNSIGNED))


def download_file(s3, key, dest):
    dest = Path(dest)
    if dest.exists():
        logger.info(f"Already exists: {dest}")
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    logger.info(f"Downloading {key}...")
    s3.download_file(BUCKET, key, str(dest))
    logger.info(f"Downloaded: {dest}")
    return dest


def extract_tar(tar_path, dest_dir):
    dest_dir = Path(dest_dir)
    if dest_dir.exists() and any(dest_dir.iterdir()):
        logger.info(f"Already extracted: {dest_dir}")
        return dest_dir
    dest_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Extracting {tar_path}...")
    with tarfile.open(tar_path, "r") as tar:
        tar.extractall(path=dest_dir)
    logger.info(f"Extracted to {dest_dir}")
    return dest_dir


def extract_text(pdf_path):
    try:
        import fitz
        doc = fitz.open(str(pdf_path))
        text = "\n\n".join(page.get_text() for page in doc)
        doc.close()
        return text.strip() if len(text.strip()) > 100 else None
    except Exception as e:
        logger.warning(f"PDF extraction failed {pdf_path}: {e}")
        return None


def chunk_text(text, chunk_size=800, overlap=100):
    words = text.split()
    chunks = []
    i = 0
    idx = 0
    while i < len(words):
        chunk = " ".join(words[i:i+chunk_size])
        chunks.append({"chunk_index": idx, "chunk_text": chunk, "token_count": len(words[i:i+chunk_size])})
        i += chunk_size - overlap
        idx += 1
    return chunks


def embed_texts(texts, client):
    if not texts:
        return []
    try:
        response = client.embeddings.create(input=texts, model=settings.embedding_model)
        return [item.embedding for item in response.data]
    except Exception as e:
        logger.error(f"Embedding failed: {e}")
        return [None] * len(texts)


async def process_year(year, settings):
    s3 = get_s3()
    openai_client = OpenAI(api_key=settings.openai_api_key)

    # Download metadata
    meta_path = download_file(s3, f"metadata/parquet/year={year}/metadata.parquet", DATA_DIR / f"metadata_{year}.parquet")
    df = pd.read_parquet(meta_path)
    logger.info(f"Year {year}: {len(df)} cases in metadata")

    # Normalize columns
    df.columns = [c.lower().replace(" ", "_") for c in df.columns]
    if "case_no" in df.columns:
        df["case_id"] = df["case_no"].astype(str).str.strip() + f"_{year}"
    else:
        df["case_id"] = df.index.astype(str) + f"_{year}"

    for col in ["file_name", "filename", "pdf_file"]:
        if col in df.columns:
            df["pdf_filename"] = df[col]
            break
    if "pdf_filename" not in df.columns:
        df["pdf_filename"] = df["case_id"] + ".pdf"

    # Download PDFs
    tar_path = download_file(s3, f"data/tar/year={year}/english/english.tar", DATA_DIR / f"english_{year}.tar")
    pdf_dir = extract_tar(tar_path, DATA_DIR / str(year))

    # Connect DB
    dsn = f"postgresql://{settings.postgres_user}:{settings.postgres_password}@{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"
    conn = await asyncpg.connect(dsn)
    await register_vector(conn)

    processed = 0
    skipped = 0
    failed = 0

    for _, row in df.iterrows():
        case_id = row["case_id"]

        # Skip if already done
        exists = await conn.fetchval("SELECT 1 FROM chunks WHERE case_id = $1 LIMIT 1", case_id)
        if exists:
            skipped += 1
            continue

        # Find PDF
        pdf_name = str(row.get("pdf_filename", ""))
        found = list(pdf_dir.rglob(pdf_name))
        if not found:
            failed += 1
            continue
        pdf_path = found[0]

        # Extract text
        text = extract_text(pdf_path)
        if not text:
            failed += 1
            continue

        # Insert case
        try:
            await conn.execute("""
                INSERT INTO cases (case_id, year, title, petitioner, respondent,
                    date_of_judgment, disposal_nature, full_text)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                ON CONFLICT (case_id) DO NOTHING
            """,
                case_id, year,
                f"{row.get('petitioner','?')} vs {row.get('respondent','?')}",
                str(row.get("petitioner", "")),
                str(row.get("respondent", "")),
                pd.to_datetime(row.get("date_of_judgment"), errors="coerce"),
                str(row.get("disposal_nature", "")),
                text[:50000],
            )
        except Exception as e:
            logger.error(f"Case insert failed {case_id}: {e}")
            failed += 1
            continue

        # Chunk
        chunks = chunk_text(text)
        if not chunks:
            failed += 1
            continue

        # Embed in batches
        batch_size = 50
        all_embeddings = []
        for i in range(0, len(chunks), batch_size):
            batch = [c["chunk_text"] for c in chunks[i:i+batch_size]]
            embeddings = embed_texts(batch, openai_client)
            all_embeddings.extend(embeddings)

        # Insert chunks
        await conn.execute("DELETE FROM chunks WHERE case_id = $1", case_id)
        for chunk, embedding in zip(chunks, all_embeddings):
            if embedding is None:
                continue
            try:
                await conn.execute("""
                    INSERT INTO chunks (case_id, chunk_index, chunk_text, token_count, embedding)
                    VALUES ($1,$2,$3,$4,$5)
                """, case_id, chunk["chunk_index"], chunk["chunk_text"], chunk["token_count"], embedding)
            except Exception as e:
                logger.error(f"Chunk insert failed: {e}")

        processed += 1
        if processed % 10 == 0:
            logger.info(f"Year {year}: processed={processed} skipped={skipped} failed={failed}")

    await conn.close()
    logger.info(f"Year {year} DONE: processed={processed} skipped={skipped} failed={failed}")
    return processed


async def main(years):
    settings = get_settings()
    for year in years:
        logger.info(f"\n{'='*50}\nProcessing year {year}\n{'='*50}")
        await process_year(year, settings)
    logger.info("All years done!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--years", nargs="+", type=int, default=[2024])
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()
    years = args.years
    asyncio.run(main(years))
