.PHONY: help up down logs seed ingest search verify test test-poetry install-poetry load chaos-kill-projector replay-dlq lint fmt demo clean psql bootstrap

SHELL := /bin/bash
COMPOSE := docker compose

help:
	@echo "Eligibility Platform (orchestration repo) — common targets"
	@echo "  make bootstrap           clone all 7 sibling service repos into parent dir"
	@echo "  make up                  docker compose up -d (builds from sibling repos)"
	@echo "  make down                stop and remove"
	@echo "  make logs [S=svc]        tail logs (optionally single service)"
	@echo "  make seed                seed synthetic payers/employers/plans"
	@echo "  make ingest [F=file]     upload an 834/CSV via BFF (default: samples/834_demo.x12, 18 members)"
	@echo "  make search Q=sharma     fuzzy search via GraphQL"
	@echo "  make verify              assert DB + OS state after ingest"
	@echo "  make test                run pytest in every repo via Poetry"
	@echo "  make install-poetry      poetry install in every repo (one-time setup)"
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

# Rich demo dataset: seed refs + ingest 18-member 834 + post-ingest mutations
# that produce varied statuses (active + pending + terminated + corrected).
# Run AFTER `make up`. Idempotent on a fresh stack; re-runs may error because
# the ingest step rejects duplicate segments.
seed-demo:
	@$(MAKE) seed
	@$(MAKE) ingest
	@echo ""
	@./scripts/seed_demo.sh

ingest:
	@F=$${F:-samples/834_demo.x12}; \
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

test: test-poetry

test-poetry:
	@echo "Running pytest in all 6 Python repos via Poetry"
	@for d in ../eligibility-atlas ../eligibility-member ../eligibility-group ../eligibility-plan ../eligibility-bff; do \
	  if [ -d "$$d" ]; then printf "%-30s " "$$(basename $$d):"; \
	    (cd $$d && poetry run pytest --no-header 2>&1 | grep -E "passed|failed|error" | tail -1); fi; \
	done
	@if [ -d ../eligibility-workers ]; then \
	  for w in ingestion projector outbox-relay; do \
	    printf "%-30s " "workers/$$w:"; \
	    (cd ../eligibility-workers && PYTHONPATH=$$w:libs/python-common/src:libs/x12-834/src poetry run pytest $$w/tests --no-header 2>&1 | grep -E "passed|failed|error" | tail -1); \
	  done; \
	fi

install-poetry:
	@echo "Installing Poetry venvs in all 6 Python repos (uses python3.12)"
	@for d in ../eligibility-atlas ../eligibility-member ../eligibility-group ../eligibility-plan ../eligibility-bff ../eligibility-workers; do \
	  if [ -d "$$d" ]; then echo "--- $$(basename $$d)"; \
	    (cd $$d && poetry env use python3.12 2>&1 | tail -1; poetry install --no-root 2>&1 | tail -1); fi; \
	done

load:
	@command -v k6 >/dev/null 2>&1 || { echo "k6 not installed. Install: brew install k6"; exit 1; }
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
