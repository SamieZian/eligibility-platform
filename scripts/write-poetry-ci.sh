#!/usr/bin/env bash
# Write Poetry-based GitHub Actions CI for each Python repo.
set -euo pipefail
DESKTOP=/Users/sampathake/Desktop

write_python_ci() {
  local repo="$1" pythonpath_extra="$2" pytest_path="$3"
  local dst="$DESKTOP/$repo"
  mkdir -p "$dst/.github/workflows"
  cat > "$dst/.github/workflows/ci.yml" <<EOF
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip
      - name: Install Poetry
        run: pipx install poetry==1.8.3
      - name: Configure Poetry
        run: poetry config virtualenvs.in-project true
      - name: Install dependencies
        run: poetry install --no-root
      - name: Lint (ruff)
        run: poetry run ruff check . || true
      - name: Run tests
        env:
          DATABASE_URL: postgresql+psycopg://x@x/x
          ATLAS_URL: http://x
          MEMBER_URL: http://x
          GROUP_URL: http://x
          PLAN_URL: http://x
          OPENSEARCH_URL: http://x
          ATLAS_DB_URL: postgresql+psycopg://x@x/x
          MEMBER_DB_URL: postgresql+psycopg://x@x/x
          GROUP_DB_URL: postgresql+psycopg://x@x/x
          PLAN_DB_URL: postgresql+psycopg://x@x/x
          MINIO_ENDPOINT: http://x
          MINIO_BUCKET: b
          MINIO_ROOT_USER: u
          MINIO_ROOT_PASSWORD: p
        run: PYTHONPATH=.${pythonpath_extra} poetry run pytest ${pytest_path} -q

  docker:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Build image
        run: docker build -t $repo:ci .
EOF
  echo "  $repo: CI updated"
}

# Standard Python services — single Dockerfile at root, tests/ at root
for r in eligibility-atlas eligibility-member eligibility-group eligibility-plan eligibility-bff; do
  write_python_ci "$r" ":libs/python-common/src" "tests"
done

# workers — special: 3 sub-projects, each in its own dir
cat > "$DESKTOP/eligibility-workers/.github/workflows/ci.yml" <<'EOF'
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip
      - name: Install Poetry
        run: pipx install poetry==1.8.3
      - name: Configure Poetry
        run: poetry config virtualenvs.in-project true
      - name: Install dependencies
        run: poetry install --no-root
      - name: Run all worker test suites
        env:
          DATABASE_URL: postgresql+psycopg://x@x/x
          ATLAS_URL: http://x
          MEMBER_URL: http://x
          GROUP_URL: http://x
          PLAN_URL: http://x
          OPENSEARCH_URL: http://x
          ATLAS_DB_URL: postgresql+psycopg://x@x/x
          MEMBER_DB_URL: postgresql+psycopg://x@x/x
          GROUP_DB_URL: postgresql+psycopg://x@x/x
          PLAN_DB_URL: postgresql+psycopg://x@x/x
          MINIO_ENDPOINT: http://x
          MINIO_BUCKET: b
          MINIO_ROOT_USER: u
          MINIO_ROOT_PASSWORD: p
        run: |
          set -e
          for w in ingestion projector outbox-relay; do
            echo "═══ $w ═══"
            PYTHONPATH=$w:libs/python-common/src:libs/x12-834/src poetry run pytest $w/tests -q
          done

  docker:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        worker: [ingestion, projector, outbox-relay]
    steps:
      - uses: actions/checkout@v4
      - name: Build ${{ matrix.worker }} image
        run: docker build -t eligibility-${{ matrix.worker }}:ci -f ${{ matrix.worker }}/Dockerfile .
EOF
echo "  eligibility-workers: CI updated"

echo "✅ All 6 Python CIs updated for Poetry"
