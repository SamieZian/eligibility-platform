.PHONY: help up down logs seed ingest search verify test load chaos-kill-projector replay-dlq lint fmt demo clean psql bootstrap

SHELL := /bin/bash
COMPOSE := docker compose

help:
	@echo "Eligibility Platform (orchestration repo) — common targets"
	@echo "  make bootstrap           clone all 7 sibling service repos into parent dir"
	@echo "  make up                  docker compose up -d (builds from sibling repos)"
	@echo "  make down                stop and remove"
	@echo "  make logs [S=svc]        tail logs (optionally single service)"
	@echo "  make seed                seed synthetic payers/employers/plans"
	@echo "  make ingest [F=file]     upload an 834/CSV via BFF (default: samples/834_sample.x12)"
	@echo "  make search Q=sharma     fuzzy search via GraphQL"
	@echo "  make verify              assert DB + OS state after ingest"
	@echo "  make test                run all tests"
	@echo "  make load                k6 small load run"
	@echo "  make chaos-kill-projector  kill projector, write, restart, verify catch-up"
	@echo "  make replay-dlq TOPIC=.. replay a DLQ topic"
	@echo "  make demo                automated tour"
	@echo "  make psql D=atlas_db     psql into any service's db"
	@echo "  make clean               tear down volumes"

bootstrap:
	./bootstrap.sh

up:
	$(COMPOSE) up -d --build
	@./scripts/wait-for-healthy.sh || true

down:
	$(COMPOSE) down

clean:
	$(COMPOSE) down -v

logs:
	@if [ -z "$(S)" ]; then $(COMPOSE) logs -f --tail=100; \
	else $(COMPOSE) logs -f --tail=100 $(S); fi

seed:
	$(COMPOSE) exec -T bff python -m app.cli seed

ingest:
	@F=$${F:-samples/834_sample.x12}; \
	echo "Ingesting $$F"; \
	curl -sS -X POST http://localhost:4000/files/eligibility \
	  -H "X-Tenant-Id: 11111111-1111-1111-1111-111111111111" \
	  -H "X-Correlation-Id: cli-$$$$" \
	  -F "file=@$$F" | jq . 2>/dev/null || cat

search:
	@Q=$${Q:-sharma}; \
	curl -sS -X POST http://localhost:4000/graphql \
	  -H 'Content-Type: application/json' \
	  -H "X-Tenant-Id: 11111111-1111-1111-1111-111111111111" \
	  -d "{\"query\":\"{ searchEnrollments(filter: {q: \\\"$$Q\\\"}, page: {limit: 20}) { total items { memberName planName employerName status effectiveDate } } }\"}" \
	  | jq . 2>/dev/null || cat

verify:
	python3 tests/e2e/verify_after_ingest.py

test:
	@for d in ../eligibility-atlas ../eligibility-member ../eligibility-group ../eligibility-plan ../eligibility-bff; do \
	  if [ -d "$$d" ]; then echo "--- $$d"; \
	    (cd $$d && PYTHONPATH=.:libs/python-common/src python -m pytest tests -q 2>&1 | tail -5); fi; \
	done
	@if [ -d ../eligibility-workers ]; then \
	  for w in ingestion projector outbox-relay; do \
	    echo "--- workers/$$w"; \
	    (cd ../eligibility-workers/$$w && PYTHONPATH=.:../libs/python-common/src:../libs/x12-834/src python -m pytest tests -q 2>&1 | tail -5); \
	  done; \
	fi

load:
	k6 run tests/load/search.k6.js

chaos-kill-projector:
	bash tests/chaos/kill_projector.sh

replay-dlq:
	@if [ -z "$(TOPIC)" ]; then echo "usage: make replay-dlq TOPIC=foo.DLQ"; exit 1; fi
	python3 scripts/replay_dlq.py --topic $(TOPIC)

demo:
	bash scripts/demo.sh

psql:
	@D=$${D:-atlas_db}; \
	$(COMPOSE) exec -it $$D psql -U postgres -d $$D
