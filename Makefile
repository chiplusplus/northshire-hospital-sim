.PHONY: gen-data load-data container-up container-down

PY=python3

gen-data:
	$(PY) -m generators.generate_data

load-data:
	$(PY) -m dynamic_exports.ehr.load_ehr
	$(PY) -m dynamic_exports.urgent_care.load_logs

container-up:
	docker compose up -d ehr_postgres
	docker compose up -d urgent_care_postgres

container-down:
	docker compose down