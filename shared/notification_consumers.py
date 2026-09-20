"""Notification queue consumers: explicit provisioning, then bind-only workers.

The legacy consumers remain untouched. Start after their contiguous ACK floor,
not their delivered sequence: in-flight messages are still owed. Limits/file
retention and complete retained history are prerequisites for the migration.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

from nats.js.api import AckPolicy, ConsumerConfig, DeliverPolicy, RetentionPolicy, StorageType
from nats.js.errors import NotFoundError

import nats

STREAM = "sahool"
ACK_WAIT = 120
SUBSCRIPTIONS = [
    ("sahool.tenant.*.satellite.*.computed", "notif_satellite"),
    ("sahool.alerts.weather", "notif_weather"),
    ("sahool.pest.alert", "notif_pest"),
    ("sahool.irrigation.recommendation", "notif_irrigation"),
    ("sahool.fertilizer.recommendation", "notif_fertilizer"),
    ("sahool.inventory.low_stock", "notif_stock"),
    ("sahool.task.assigned", "notif_task"),
    ("sahool.economic.analysis", "notif_economic"),
    # Tenant-scoped live domain events published by the platform outbox.
    ("sahool.events.>", "notif_domain_events"),
]


def queue_name(legacy: str) -> str:
    return f"{legacy}_queue_v1"


def queue_config(subject: str, legacy: str, start: int, created: str) -> ConsumerConfig:
    name = queue_name(legacy)
    return ConsumerConfig(
        durable_name=name,
        description=f"notification-queue-v1:{legacy}:{created}",
        filter_subject=subject,
        deliver_subject=f"_INBOX.sahool.notification.{name}",
        deliver_group=name,
        deliver_policy=DeliverPolicy.BY_START_SEQUENCE,
        opt_start_seq=start,
        ack_policy=AckPolicy.EXPLICIT,
        ack_wait=ACK_WAIT,
        max_deliver=-1,
        max_ack_pending=128,
    )


def validate_queue(config: ConsumerConfig, subject: str, legacy: str) -> None:
    """Never bind a differently configured consumer or silently change its cursor."""
    expected = queue_config(subject, legacy, 1, "")
    for key in (
        "durable_name",
        "filter_subject",
        "deliver_subject",
        "deliver_group",
        "deliver_policy",
        "ack_policy",
        "ack_wait",
        "max_deliver",
        "max_ack_pending",
    ):
        if getattr(config, key) != getattr(expected, key):
            raise ValueError(f"queue_config_mismatch:{legacy}:{key}")
    if not config.opt_start_seq or config.opt_start_seq < 1:
        raise ValueError("queue_start_sequence_missing")
    if not (config.description or "").startswith(expected.description):
        raise ValueError("queue_migration_provenance_missing")
    if any(
        getattr(config, key, None)
        for key in (
            "filter_subjects",
            "headers_only",
            "flow_control",
            "rate_limit_bps",
            "inactive_threshold",
            "backoff",
        )
    ):
        raise ValueError("queue_delivery_semantics_mismatch")


def validate_stream(info) -> None:
    config = info.config
    if config.retention != RetentionPolicy.LIMITS or config.storage != StorageType.FILE:
        raise ValueError("migration_requires_limits_file_stream")
    if (
        config.max_age
        or config.allow_msg_ttl
        or any(
            getattr(config, key, -1) not in (-1, None)
            for key in ("max_msgs", "max_bytes", "max_msgs_per_subject")
        )
    ):
        raise ValueError("migration_requires_unlimited_retention")
    # A conservative proof: reject any missing history, including manual purges.
    if info.state.messages != info.state.last_seq:
        raise ValueError("migration_requires_complete_stream_history")


def validate_legacy(info, subject: str, legacy: str) -> None:
    config = info.config
    if (
        config.durable_name != legacy
        or config.filter_subject != subject
        or config.deliver_group
        or not config.deliver_subject
        or config.ack_policy != AckPolicy.EXPLICIT
        or config.filter_subjects
    ):
        raise ValueError(f"legacy_config_mismatch:{legacy}")


async def build_plan(js) -> dict:
    stream = await js.stream_info(STREAM)
    validate_stream(stream)
    entries = []
    for subject, legacy in SUBSCRIPTIONS:
        info = await js.consumer_info(STREAM, legacy)
        validate_legacy(info, subject, legacy)
        entries.append(
            {
                "subject": subject,
                "legacy": legacy,
                "legacy_created": info.created.isoformat(),
                "start_sequence": info.ack_floor.stream_seq + 1,
            }
        )
    return {"version": 1, "stream_created": stream.created.isoformat(), "consumers": entries}


async def apply_plan(nc, plan: dict) -> list[str]:
    """Create only; never update/delete a consumer, including on retries/races."""
    version = nc.connected_server_version
    if (version.major, version.minor, version.patch) < (2, 15, 0) or version.prerelease:
        raise ValueError("migration_requires_tested_nats_2_15_or_newer")
    js = nc.jetstream()
    stream = await js.stream_info(STREAM)
    validate_stream(stream)
    if plan.get("version") != 1 or plan.get("stream_created") != stream.created.isoformat():
        raise ValueError("migration_stream_identity_changed")
    entries = plan["consumers"]
    if [(e["subject"], e["legacy"]) for e in entries] != SUBSCRIPTIONS:
        raise ValueError("migration_subscription_set_mismatch")
    configs = []
    # Preflight every legacy before making the first write. Its ACK floor may
    # advance after planning; retaining the earlier start only adds safe replay.
    for entry in entries:
        subject, legacy = entry["subject"], entry["legacy"]
        info = await js.consumer_info(STREAM, legacy)
        validate_legacy(info, subject, legacy)
        start = entry["start_sequence"]
        if (
            info.created.isoformat() != entry["legacy_created"]
            or type(start) is not int
            or not 1 <= start <= info.ack_floor.stream_seq + 1
        ):
            raise ValueError(f"migration_checkpoint_invalid:{legacy}")
        config = queue_config(subject, legacy, start, entry["legacy_created"])
        try:
            existing = await js.consumer_info(STREAM, queue_name(legacy))
        except NotFoundError:
            configs.append(config)
        else:
            validate_queue(existing.config, subject, legacy)
            if (
                existing.config.opt_start_seq != start
                or existing.config.description != config.description
            ):
                raise ValueError(f"migration_existing_checkpoint_mismatch:{legacy}")
    for config in configs:
        # The public JetStream API's create action rejects existing consumers;
        # add_consumer is create-or-update and is unsafe for migration races.
        response = await nc.request(
            f"$JS.API.CONSUMER.CREATE.{STREAM}.{config.durable_name}",
            json.dumps(
                {"stream_name": STREAM, "config": config.as_dict(), "action": "create"}
            ).encode(),
            timeout=5,
        )
        if "error" in json.loads(response.data):
            raise RuntimeError(f"consumer_create_rejected:{config.durable_name}")
    return [queue_name(legacy) for _, legacy in SUBSCRIPTIONS]


async def _main(args) -> None:
    nc = await nats.connect(os.environ["NATS_URL"])
    try:
        if args.apply:
            names = await apply_plan(nc, json.loads(args.apply.read_text(encoding="utf-8")))
            print(json.dumps({"provisioned": names, "legacy_consumers_unchanged": True}))
        else:
            plan = await build_plan(nc.jetstream())
            args.plan.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
            print(f"Wrote migration plan: {args.plan}")
    finally:
        await nc.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", type=Path)
    mode.add_argument("--apply", type=Path)
    asyncio.run(_main(parser.parse_args()))
