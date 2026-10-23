#!/bin/sh
# NATS reparses environment substitutions as config scalars. Quote only the
# broker's copy; clients must continue to authenticate with the original value.
set -eu
for name in NATS_PLATFORM_PASSWORD NATS_OUTBOX_WORKER_PASSWORD \
    NATS_PLUGIN_WORKER_PASSWORD NATS_MODEL_WORKER_PASSWORD \
    NATS_ACTUATOR_WORKER_PASSWORD NATS_RELAY_WORKER_PASSWORD \
    NATS_LEARNING_WORKER_PASSWORD NATS_NOTIFICATION_PASSWORD NATS_VEGETATION_PASSWORD
do
    value=$(printenv "$name") || value=
    # Client URLs interpolate these values directly: enforce URI-unreserved
    # bytes, also rejecting newlines before command substitution can trim them.
    if ! printenv "$name" | LC_ALL=C awk '
        NR != 1 || $0 !~ /^[A-Za-z0-9._~-]+$/ { bad=1 }
        END { exit (NR != 1 || bad) }
    '; then
        printf '%s\n' "NATS_PASSWORD_INVALID: $name must be nonempty and URI-unreserved" >&2
        exit 1
    fi
    export "$name=\"$value\""
done
exec "$@"
