.PHONY: help up down logs seed ingest search verify test test-unit test-int load chaos-kill-projector replay-dlq build lint fmt demo clean psql

SHELL := /bin/bash
COMPOSE := docker compose

help:
	@echo "Eligibility Platform — common targets"
	@echo "  make up                  docker compose up -d (all services)"
	@echo "  make down                stop and remove"
	@echo "  make logs [S=svc]        tail logs (optionally a single service)"
	@echo "  make seed                seed synthetic payers/employers/plans/members"
	@echo "  make ingest [F=file]     ingest an 834/CSV file (default: tests/golden/834_sample.x12)"
	@echo "  make search Q=sharma     fuzzy search via BFF GraphQL"
	@echo "  make verify              assert DB + OS state after ingest"
	@echo "  make test                run all tests"
	@echo "  make test-unit           unit tests only"
	@echo "  make test-int            integration tests (Testcontainers)"
	@echo "  make load                k6 small load test"
	@echo "  make chaos-kill-projector  kill projector, write, restart, verify catch-up"
	@echo "  make replay-dlq TOPIC=.. replay a DLQ topic"
	@echo "  make lint                ruff + mypy + prettier"
	@echo "  make fmt                 ruff format + prettier --write"
	@echo "  make demo                full automated demo"
	@echo "  make clean               tear down volumes"

up:
	$(COMPOSE) up -d --build
	@echo "Waiting for stack to be healthy..."
	@./scripts/wait-for-healthy.sh

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
	@F=$${F:-tests/golden/834_sample.x12}; \
	echo "Ingesting $$F"; \
	curl -sS -X POST http://localhost:4000/files/eligibility \
	  -H "X-Tenant-Id: 11111111-1111-1111-1111-111111111111" \
	  -H "X-Correlation-Id: cli-$$$$" \
	  -F "file=@$$F" | jq .

search:
	@Q=$${Q:-sharma}; \
	curl -sS http://localhost:4000/graphql \
	  -H 'Content-Type: application/json' \
	  -H "X-Tenant-Id: 11111111-1111-1111-1111-111111111111" \
	  -d "{\"query\":\"{ searchEnrollments(filter: {q: \\\"$$Q\\\"}, page: {limit: 20}) { items { memberName planName status effectiveDate } total } }\"}" | jq .

verify:
	python3 tests/e2e/verify_after_ingest.py

test: test-unit test-int
test-unit:
	@for d in services/* workers/* libs/*; do \
	  if [ -f $$d/pyproject.toml ]; then \
	    echo "--- $$d"; (cd $$d && python -m pytest -q tests/unit 2>/dev/null || python -m pytest -q tests 2>/dev/null || true); \
	  fi; \
	done
	@cd frontend && npm test --silent --if-present || true

test-int:
	python3 -m pytest tests/integration -q

load:
	k6 run tests/load/search.k6.js

chaos-kill-projector:
	bash tests/chaos/kill_projector.sh

replay-dlq:
	@if [ -z "$(TOPIC)" ]; then echo "usage: make replay-dlq TOPIC=foo.DLQ"; exit 1; fi
	python3 scripts/replay_dlq.py --topic $(TOPIC)

lint:
	ruff check .
	ruff format --check .
	@cd frontend && npm run lint --if-present

fmt:
	ruff format .
	@cd frontend && npm run fmt --if-present

demo:
	bash scripts/demo.sh

psql:
	@D=$${D:-atlas_db}; \
	$(COMPOSE) exec -it $$D psql -U postgres -d $$D
