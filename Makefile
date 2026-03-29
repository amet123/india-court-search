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
