.PHONY: help up down logs trust trust-fast generate publish-ehr publish-urgent publish-sftp publish-s3 reset reset-soft cdk-synth cdk-deploy cdk-deploy-no-sftp cdk-destroy gen-sources trust-bootstrap trust-bootstrap-no-sftp trust-seed trust-destroy

PY=python3
CDK_DIR=infra
CDK_OUTPUTS=$(CDK_DIR)/cdk-outputs.json

help:
	@echo "Local Docker targets:"
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
	@echo ""
	@echo "AWS targets:"
	@echo "  trust-bootstrap            - Do everything: deploy + DB setup + generate + publish"
	@echo "  trust-bootstrap-no-sftp    - Same, without Transfer Family (saves ~$$0.30/hr)"
	@echo "  cdk-deploy                 - Deploy infrastructure only"
	@echo "  cdk-deploy-no-sftp         - Deploy without Transfer Family"
	@echo "  trust-seed                 - Seed data into already-deployed infra"
	@echo "  trust-destroy              - Kill tunnel + destroy all AWS infra"
	@echo ""
	@echo "AWS utilities:"
	@echo "  cdk-synth          - Synthesise CloudFormation (no deploy)"
	@echo "  cdk-destroy        - Destroy all AWS resources"
	@echo "  gen-sources        - Write config/sources.yaml from CDK outputs"

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

# ── AWS CDK ───────────────────────────────────────────────────────────────────

cdk-synth:
	cd $(CDK_DIR) && cdk synth

cdk-deploy:
	cd $(CDK_DIR) && cdk deploy --outputs-file cdk-outputs.json --require-approval broadening

# Skip Transfer Family ($0.30/hr) - use when only testing EHR or S3 flows
cdk-deploy-no-sftp:
	cd $(CDK_DIR) && cdk deploy --outputs-file cdk-outputs.json --require-approval broadening -c deployTransferFamily=false

cdk-destroy:
	cd $(CDK_DIR) && cdk destroy --force

gen-sources:
	$(PY) scripts/export_outputs.py --cdk-outputs $(CDK_OUTPUTS) --sources config/sources.yaml --profile northshire-trust

trust-bootstrap:
	$(PY) scripts/aws_trust_up.py $(ARGS)

trust-bootstrap-no-sftp:
	$(PY) scripts/aws_trust_up.py --no-sftp $(ARGS)

trust-seed:
	$(PY) scripts/aws_trust_up.py --skip-deploy $(ARGS)

trust-destroy:
	-kill $$(cat .tunnel.pid 2>/dev/null) 2>/dev/null; rm -f .tunnel.pid
	cd $(CDK_DIR) && cdk destroy --force