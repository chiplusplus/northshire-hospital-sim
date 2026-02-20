.PHONY: help up down logs trust trust-fast generate publish-ehr publish-urgent publish-sftp publish-s3 reset reset-soft

PY=python3

help:
	@echo "Targets:"
	@echo "  up             - Start docker services"
	@echo "  down           - Stop docker services (keeps volumes)"
	@echo "  down-v         - Stop docker services and remove volumes"
	@echo "  logs           - Tail logs"
	@echo "  generate       - Generate staging data"
	@echo "  publish-ehr    - Load ehr_internal + refresh ehr_mirror"
	@echo "  publish-urgent - Load urgent_internal + refresh urgent_mirror"
	@echo "  publish-sftp   - Publish staged exports to SFTP drop"
	@echo "  publish-s3     - Upload diagnostics + providers excel to S3"
	@echo "  trust          - Full bootstrap (up + generate + publish all)"
	@echo "  trust-fast     - Bootstrap without docker up (assumes services already running)"
	@echo "  reset          - Full reset: stop containers, remove volumes, delete all generated artefacts"
	@echo "  reset-soft     - Soft reset: delete generated artefacts only (keeps containers/volumes)"

up:
	docker compose up -d

down:
	docker compose down

down-v:
	docker compose down -v

logs:
	docker compose logs -f --tail=200

generate:
	$(PY) scripts/generate_data.py --staging-dir data/staging

publish-ehr:
	$(PY) scripts/publish_ehr.py --sources config/sources.yaml --staging-core data/staging/core

publish-urgent:
	$(PY) scripts/publish_urgent_care.py --sources config/sources.yaml --staging-core data/staging/core

publish-sftp:
	$(PY) scripts/publish_sftp.py --staging-exports data/staging/exports

publish-s3:
	$(PY) scripts/publish_s3.py --sources config/sources.yaml --staging-exports data/staging/exports --create-buckets-if-missing

trust:
	$(PY) scripts/trust.py --start-services --create-buckets-if-missing $(ARGS)

trust-fast:
	$(PY) scripts/trust.py --create-buckets-if-missing $(ARGS)
reset: 
	docker compose down -v
	rm -rf data/staging data/sftp_drop data/s3_exports

reset-soft: 
	rm -rf data/staging data/sftp_drop data/s3_exports