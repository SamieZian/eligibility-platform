# Pulumi — GCP stack for `eligibility-platform`

Python Pulumi program that provisions a production-shape footprint for
the Eligibility & Enrollment Platform on Google Cloud:

| Layer | Resources |
|---|---|
| Network | VPC, regional subnet, Private Service Access range + peering |
| Registry | Artifact Registry (Docker) |
| Secrets | Secret Manager (DB passwords, member KMS key, BFF OIDC secret) |
| Databases | 4 Cloud SQL Postgres 15 instances — one per bounded context (`atlas`, `member`, `group`, `plan`) — private IP, PITR, query insights |
| Event bus | 5 Pub/Sub topics + pull subscriptions with retry + DLQ (`enrollment-events`, `member-events`, `group-events`, `plan-events`, `files-received`) |
| Object storage | Cloud Storage bucket for raw 834 / CSV with versioning + NEARLINE/COLDLINE lifecycle |
| Compute | Cloud Run v2 services for `atlas`, `member`, `group`, `plan`, `bff` — wired to Artifact Registry + VPC egress |

## Prerequisites

```bash
# 1. Auth to GCP
gcloud auth application-default login

# 2. Auth to Pulumi (local backend is fine for a skeleton)
pulumi login
```

You also need:

- Python 3.11+
- A GCP project with billing enabled, and the following APIs on:
  `compute`, `servicenetworking`, `sqladmin`, `pubsub`,
  `secretmanager`, `artifactregistry`, `run`, `storage`.

## Install

```bash
cd pulumi/gcp
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Deploy

```bash
# First-time only — creates the stack
pulumi stack init dev

# Point at your GCP project
pulumi config set gcp:project YOUR_PROJECT
pulumi config set gcp:region   asia-south1   # default

# Review the plan
pulumi preview

# Apply
pulumi up
```

CI/CD reads the following stack outputs:

- `bff_url` — the public BFF endpoint
- `service_urls` — map of all Cloud Run URIs
- `sql_connection_names` — for Cloud SQL Auth Proxy sidecars
- `files_bucket`, `registry`, `topics`, `vpc`

## Teardown

```bash
pulumi destroy
pulumi stack rm dev
```

Cloud SQL instances have `deletion_protection=True`. To actually destroy
them, flip that to `False`, run `pulumi up`, then `pulumi destroy`.

## TODOs for a real prod stack

These are intentionally out of scope for this skeleton — each one is its
own review cycle:

- **VPC Service Controls perimeter** around Cloud SQL, GCS, Secret
  Manager. Requires an Org-level policy admin and an Access Context
  Manager policy; not expressible inside a single stack.
- **CMEK** on Cloud SQL + GCS with a dedicated KMS key ring. Rotate
  annually via `gcp.kms.CryptoKey.rotation_period`.
- **IAM bindings** per Cloud Run service account — each service should
  only get `secretmanager.secretAccessor` on its own secrets,
  `pubsub.publisher`/`subscriber` on its own topics, and
  `cloudsql.client` on its own instance.
- **Cloud SQL IAM DB auth** instead of passwords in Secret Manager.
- **Cloud Armor + external HTTPS load balancer** in front of the BFF,
  with a managed certificate and a WAF policy.
- **Monitoring & alert policies** (`gcp.monitoring.AlertPolicy`) for
  SLO burn rate, Pub/Sub DLQ depth, and Cloud SQL CPU.
- **Multiple stacks** — split `dev`, `staging`, `prod` with
  `Pulumi.<stack>.yaml` per env and a shared component library.

## Layout

```
pulumi/gcp/
├── Pulumi.yaml          # project + runtime
├── Pulumi.dev.yaml      # dev stack config
├── requirements.txt     # pulumi + pulumi-gcp pins
├── __main__.py          # the program (network, SQL, Pub/Sub, GCS, Cloud Run)
└── README.md            # this file
```

`__main__.py` is organised into one helper per section (`_network`,
`_cloud_sql`, `_pubsub`, `_storage`, `_cloud_run`, ...) so each layer is
readable on its own.
