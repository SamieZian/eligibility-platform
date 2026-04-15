"""
Eligibility & Enrollment Platform — GCP Pulumi program.

Provisions a production-shape footprint for the platform:

  Network           : VPC + regional subnet + Private Service Access
                      for Cloud SQL (private IP only).
  Registry          : Artifact Registry (Docker) for service images.
  Secrets           : Secret Manager for DB passwords + KMS keys.
  Databases         : One Cloud SQL Postgres instance per bounded
                      context (atlas / member / group / plan).
  Event bus         : Pub/Sub topic + subscription + DLQ per event
                      family, with retry & dead-letter policies.
  Object storage    : Cloud Storage bucket for raw 834 / CSV payloads
                      with versioning + lifecycle to NEARLINE.
  Compute           : Cloud Run v2 services for the 4 FastAPI services
                      + the BFF, wired to Artifact Registry + VPC
                      egress (so they can reach Cloud SQL on private IP).

The structure intentionally mirrors the bounded contexts in the repo
(`services/atlas`, `services/member`, `services/group`, `services/plan`
+ BFF) so the reviewer can trace "one service = one module = one DB".

This is a skeleton — it defines resources but does not manage IAM
bindings, CMEK, or VPC-SC perimeters. Those are captured as TODOs in
the README and are the natural next layer for a production stack.
"""

from __future__ import annotations

import pulumi
import pulumi_gcp as gcp

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_gcp_cfg = pulumi.Config("gcp")
_cfg = pulumi.Config()

PROJECT: str = _gcp_cfg.require("project")
REGION: str = _gcp_cfg.get("region") or "asia-south1"
ENV: str = _cfg.get("env") or "dev"
IMAGE_TAG: str = _cfg.get("image_tag") or "latest"

# Bounded contexts — each gets its own Cloud SQL instance + DB + user.
BOUNDED_CONTEXTS: list[str] = ["atlas", "member", "group", "plan"]

# Pub/Sub event families — one topic + sub + DLQ per family.
EVENT_FAMILIES: list[str] = [
    "enrollment-events",
    "member-events",
    "group-events",
    "plan-events",
    "files-received",
]

# Cloud Run services — (name, container port). BFF runs on 4000 (Strawberry
# GraphQL + FastAPI), the FastAPI services all use 8000.
CLOUD_RUN_SERVICES: list[tuple[str, int]] = [
    ("atlas", 8000),
    ("member", 8000),
    ("group", 8000),
    ("plan", 8000),
    ("bff", 4000),
]

LABELS = {"app": "eligibility-platform", "env": ENV, "managed-by": "pulumi"}


# ---------------------------------------------------------------------------
# Network — VPC, subnet, and Private Service Access for Cloud SQL
# ---------------------------------------------------------------------------


def _network() -> tuple[gcp.compute.Network, gcp.compute.Subnetwork, gcp.servicenetworking.Connection]:
    vpc = gcp.compute.Network(
        "eligibility-vpc",
        name=f"eligibility-{ENV}-vpc",
        auto_create_subnetworks=False,
        routing_mode="REGIONAL",
    )

    subnet = gcp.compute.Subnetwork(
        "eligibility-subnet",
        name=f"eligibility-{ENV}-subnet",
        ip_cidr_range="10.20.0.0/20",
        region=REGION,
        network=vpc.id,
        private_ip_google_access=True,
    )

    # Range reserved for Google-managed services (Cloud SQL, etc.) to sit on
    # private IPs inside our VPC.
    pr_range = gcp.compute.GlobalAddress(
        "eligibility-psa-range",
        name=f"eligibility-{ENV}-psa-range",
        purpose="VPC_PEERING",
        address_type="INTERNAL",
        prefix_length=16,
        network=vpc.id,
    )

    pr_conn = gcp.servicenetworking.Connection(
        "eligibility-psa-conn",
        network=vpc.id,
        service="servicenetworking.googleapis.com",
        reserved_peering_ranges=[pr_range.name],
    )

    return vpc, subnet, pr_conn


# ---------------------------------------------------------------------------
# Artifact Registry — one Docker repo for all service images
# ---------------------------------------------------------------------------


def _artifact_registry() -> gcp.artifactregistry.Repository:
    return gcp.artifactregistry.Repository(
        "eligibility-registry",
        repository_id="eligibility",
        location=REGION,
        format="DOCKER",
        description="Container images for eligibility-platform services.",
        labels=LABELS,
    )


# ---------------------------------------------------------------------------
# Secret Manager — DB passwords + KMS keys placeholder
# ---------------------------------------------------------------------------


def _secrets() -> dict[str, gcp.secretmanager.Secret]:
    secret_ids = [f"{svc}-db-password" for svc in BOUNDED_CONTEXTS] + [
        "member-kms-key",  # consumed by member service for SSN envelope encryption
        "bff-oidc-client-secret",
    ]
    secrets: dict[str, gcp.secretmanager.Secret] = {}
    for sid in secret_ids:
        secrets[sid] = gcp.secretmanager.Secret(
            sid,
            secret_id=sid,
            replication=gcp.secretmanager.SecretReplicationArgs(
                auto=gcp.secretmanager.SecretReplicationAutoArgs(),
            ),
            labels=LABELS,
        )
    return secrets


# ---------------------------------------------------------------------------
# Cloud SQL — one Postgres instance per bounded context
# ---------------------------------------------------------------------------


def _cloud_sql(
    vpc: gcp.compute.Network,
    pr_conn: gcp.servicenetworking.Connection,
) -> dict[str, gcp.sql.DatabaseInstance]:
    instances: dict[str, gcp.sql.DatabaseInstance] = {}
    for svc in BOUNDED_CONTEXTS:
        inst = gcp.sql.DatabaseInstance(
            f"{svc}-pg",
            name=f"{svc}-pg-{ENV}",
            region=REGION,
            database_version="POSTGRES_15",
            deletion_protection=True,
            settings=gcp.sql.DatabaseInstanceSettingsArgs(
                tier="db-custom-2-7680",  # 2 vCPU / 7.5 GiB — small prod-shaped
                availability_type="REGIONAL",
                disk_type="PD_SSD",
                disk_size=20,
                disk_autoresize=True,
                user_labels=LABELS,
                ip_configuration=gcp.sql.DatabaseInstanceSettingsIpConfigurationArgs(
                    ipv4_enabled=False,  # private IP only — no public endpoint
                    private_network=vpc.id,
                    require_ssl=True,
                ),
                backup_configuration=gcp.sql.DatabaseInstanceSettingsBackupConfigurationArgs(
                    enabled=True,
                    point_in_time_recovery_enabled=True,
                    start_time="02:00",
                    transaction_log_retention_days=7,
                ),
                insights_config=gcp.sql.DatabaseInstanceSettingsInsightsConfigArgs(
                    query_insights_enabled=True,
                    query_string_length=1024,
                    record_application_tags=True,
                    record_client_address=False,
                ),
                maintenance_window=gcp.sql.DatabaseInstanceSettingsMaintenanceWindowArgs(
                    day=7,
                    hour=3,
                    update_track="stable",
                ),
                database_flags=[
                    gcp.sql.DatabaseInstanceSettingsDatabaseFlagsArgs(
                        name="log_min_duration_statement",
                        value="500",
                    ),
                    gcp.sql.DatabaseInstanceSettingsDatabaseFlagsArgs(
                        name="log_checkpoints",
                        value="on",
                    ),
                ],
            ),
            opts=pulumi.ResourceOptions(depends_on=[pr_conn]),
        )

        gcp.sql.Database(
            f"{svc}-db",
            name=f"{svc}_db",
            instance=inst.name,
        )

        gcp.sql.User(
            f"{svc}-user",
            name=svc,
            instance=inst.name,
            # Password is stored in Secret Manager and injected at Cloud Run
            # runtime; IAM DB auth is the preferred follow-up.
            password=pulumi.Output.secret(f"PLACEHOLDER-rotate-via-secret-manager-{svc}"),
        )

        instances[svc] = inst
    return instances


# ---------------------------------------------------------------------------
# Pub/Sub — topic + subscription + DLQ per event family
# ---------------------------------------------------------------------------


def _pubsub() -> dict[str, gcp.pubsub.Topic]:
    topics: dict[str, gcp.pubsub.Topic] = {}
    for family in EVENT_FAMILIES:
        topic = gcp.pubsub.Topic(
            family,
            name=family,
            labels=LABELS,
            message_retention_duration="604800s",  # 7 days
        )
        dlq = gcp.pubsub.Topic(
            f"{family}-dlq",
            name=f"{family}-dlq",
            labels={**LABELS, "role": "dlq"},
            message_retention_duration="604800s",
        )

        gcp.pubsub.Subscription(
            f"{family}-sub",
            name=f"{family}-sub",
            topic=topic.name,
            ack_deadline_seconds=60,
            message_retention_duration="604800s",
            expiration_policy=gcp.pubsub.SubscriptionExpirationPolicyArgs(ttl=""),
            dead_letter_policy=gcp.pubsub.SubscriptionDeadLetterPolicyArgs(
                dead_letter_topic=dlq.id,
                max_delivery_attempts=5,
            ),
            retry_policy=gcp.pubsub.SubscriptionRetryPolicyArgs(
                minimum_backoff="10s",
                maximum_backoff="600s",
            ),
            labels=LABELS,
        )

        # A pull subscription on the DLQ itself so operators can drain it
        # (matches the `make replay-dlq` flow in the root repo).
        gcp.pubsub.Subscription(
            f"{family}-dlq-sub",
            name=f"{family}-dlq-sub",
            topic=dlq.name,
            ack_deadline_seconds=60,
            labels={**LABELS, "role": "dlq"},
        )

        topics[family] = topic
    return topics


# ---------------------------------------------------------------------------
# Cloud Storage — raw 834 / CSV bucket with versioning + lifecycle
# ---------------------------------------------------------------------------


def _storage() -> gcp.storage.Bucket:
    return gcp.storage.Bucket(
        "files",
        name=f"{PROJECT}-eligibility-files-{ENV}",
        location="ASIA-SOUTH1",
        force_destroy=False,
        uniform_bucket_level_access=True,
        public_access_prevention="enforced",
        versioning=gcp.storage.BucketVersioningArgs(enabled=True),
        lifecycle_rules=[
            gcp.storage.BucketLifecycleRuleArgs(
                action=gcp.storage.BucketLifecycleRuleActionArgs(
                    type="SetStorageClass",
                    storage_class="NEARLINE",
                ),
                condition=gcp.storage.BucketLifecycleRuleConditionArgs(age=30),
            ),
            gcp.storage.BucketLifecycleRuleArgs(
                action=gcp.storage.BucketLifecycleRuleActionArgs(
                    type="SetStorageClass",
                    storage_class="COLDLINE",
                ),
                condition=gcp.storage.BucketLifecycleRuleConditionArgs(age=180),
            ),
            gcp.storage.BucketLifecycleRuleArgs(
                action=gcp.storage.BucketLifecycleRuleActionArgs(type="Delete"),
                condition=gcp.storage.BucketLifecycleRuleConditionArgs(age=2555),  # 7y
            ),
        ],
        labels=LABELS,
    )


# ---------------------------------------------------------------------------
# Cloud Run — one v2 service per FastAPI service + BFF
# ---------------------------------------------------------------------------


def _cloud_run(
    registry: gcp.artifactregistry.Repository,
    subnet: gcp.compute.Subnetwork,
    files_bucket: gcp.storage.Bucket,
) -> dict[str, gcp.cloudrunv2.Service]:
    services: dict[str, gcp.cloudrunv2.Service] = {}

    for name, port in CLOUD_RUN_SERVICES:
        image = pulumi.Output.concat(
            registry.location,
            "-docker.pkg.dev/",
            PROJECT,
            "/",
            registry.repository_id,
            "/",
            name,
            ":",
            IMAGE_TAG,
        )

        envs: list[gcp.cloudrunv2.ServiceTemplateContainerEnvArgs] = [
            gcp.cloudrunv2.ServiceTemplateContainerEnvArgs(name="ENV", value=ENV),
            gcp.cloudrunv2.ServiceTemplateContainerEnvArgs(name="GCP_PROJECT", value=PROJECT),
            gcp.cloudrunv2.ServiceTemplateContainerEnvArgs(name="FILES_BUCKET", value=files_bucket.name),
        ]

        # Bounded-context services get their DATABASE_URL from the matching
        # Secret Manager entry; BFF does not talk to a DB directly.
        if name in BOUNDED_CONTEXTS:
            envs.append(
                gcp.cloudrunv2.ServiceTemplateContainerEnvArgs(
                    name="DATABASE_URL",
                    value_source=gcp.cloudrunv2.ServiceTemplateContainerEnvValueSourceArgs(
                        secret_key_ref=gcp.cloudrunv2.ServiceTemplateContainerEnvValueSourceSecretKeyRefArgs(
                            secret=f"{name}-db-password",
                            version="latest",
                        ),
                    ),
                )
            )

        svc = gcp.cloudrunv2.Service(
            name,
            name=f"{name}-{ENV}",
            location=REGION,
            ingress="INGRESS_TRAFFIC_ALL" if name == "bff" else "INGRESS_TRAFFIC_INTERNAL_ONLY",
            template=gcp.cloudrunv2.ServiceTemplateArgs(
                scaling=gcp.cloudrunv2.ServiceTemplateScalingArgs(
                    min_instance_count=1,
                    max_instance_count=10,
                ),
                vpc_access=gcp.cloudrunv2.ServiceTemplateVpcAccessArgs(
                    egress="PRIVATE_RANGES_ONLY",
                    network_interfaces=[
                        gcp.cloudrunv2.ServiceTemplateVpcAccessNetworkInterfaceArgs(
                            network=subnet.network,
                            subnetwork=subnet.id,
                        ),
                    ],
                ),
                containers=[
                    gcp.cloudrunv2.ServiceTemplateContainerArgs(
                        image=image,
                        ports=[
                            gcp.cloudrunv2.ServiceTemplateContainerPortArgs(
                                container_port=port,
                            ),
                        ],
                        resources=gcp.cloudrunv2.ServiceTemplateContainerResourcesArgs(
                            limits={"memory": "1Gi", "cpu": "1"},
                            cpu_idle=True,
                        ),
                        envs=envs,
                        startup_probe=gcp.cloudrunv2.ServiceTemplateContainerStartupProbeArgs(
                            initial_delay_seconds=5,
                            timeout_seconds=3,
                            period_seconds=5,
                            failure_threshold=6,
                            http_get=gcp.cloudrunv2.ServiceTemplateContainerStartupProbeHttpGetArgs(
                                path="/livez",
                                port=port,
                            ),
                        ),
                        liveness_probe=gcp.cloudrunv2.ServiceTemplateContainerLivenessProbeArgs(
                            period_seconds=30,
                            timeout_seconds=3,
                            http_get=gcp.cloudrunv2.ServiceTemplateContainerLivenessProbeHttpGetArgs(
                                path="/livez",
                                port=port,
                            ),
                        ),
                    ),
                ],
            ),
            traffics=[
                gcp.cloudrunv2.ServiceTrafficArgs(
                    type="TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST",
                    percent=100,
                ),
            ],
            labels=LABELS,
        )
        services[name] = svc

    return services


# ---------------------------------------------------------------------------
# Wire everything up
# ---------------------------------------------------------------------------

vpc, subnet, pr_conn = _network()
registry = _artifact_registry()
secrets = _secrets()
sql_instances = _cloud_sql(vpc, pr_conn)
topics = _pubsub()
files_bucket = _storage()
run_services = _cloud_run(registry, subnet, files_bucket)

# ---------------------------------------------------------------------------
# Exports — consumed by CI/CD and the smoke-test harness
# ---------------------------------------------------------------------------

pulumi.export("project", PROJECT)
pulumi.export("region", REGION)
pulumi.export("vpc", vpc.id)
pulumi.export("registry", registry.name)
pulumi.export("files_bucket", files_bucket.name)
pulumi.export("bff_url", run_services["bff"].uri)
pulumi.export(
    "service_urls",
    {name: svc.uri for name, svc in run_services.items()},
)
pulumi.export(
    "sql_connection_names",
    {name: inst.connection_name for name, inst in sql_instances.items()},
)
pulumi.export("topics", {name: t.name for name, t in topics.items()})
