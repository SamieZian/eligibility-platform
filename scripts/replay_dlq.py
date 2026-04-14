"""Replay a DLQ topic: pulls messages and republishes to the original topic.

Usage: python scripts/replay_dlq.py --topic enrollment.events.dlq
"""
from __future__ import annotations

import argparse
import os

from google.cloud import pubsub_v1


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--topic", required=True, help="DLQ topic (e.g. enrollment.events.dlq)")
    p.add_argument("--project", default=os.environ.get("PUBSUB_PROJECT_ID", "local-eligibility"))
    ns = p.parse_args()

    dlq = ns.topic
    if not dlq.endswith(".dlq"):
        raise SystemExit(f"not a DLQ topic: {dlq}")
    target = dlq[:-4]

    sub_client = pubsub_v1.SubscriberClient()
    pub = pubsub_v1.PublisherClient()
    sub_path = sub_client.subscription_path(ns.project, f"replay-{dlq}")

    try:
        sub_client.create_subscription(
            request={"name": sub_path, "topic": sub_client.topic_path(ns.project, dlq)}
        )
    except Exception:
        pass

    resp = sub_client.pull(request={"subscription": sub_path, "max_messages": 100}, timeout=10)
    count = 0
    acks: list[str] = []
    for rmsg in resp.received_messages:
        m = rmsg.message
        pub.publish(pub.topic_path(ns.project, target), m.data, **dict(m.attributes)).result(30)
        acks.append(rmsg.ack_id)
        count += 1
    if acks:
        sub_client.acknowledge(request={"subscription": sub_path, "ack_ids": acks})
    print(f"replayed {count} messages from {dlq} → {target}")


if __name__ == "__main__":
    main()
