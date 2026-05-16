"""Constants for the Tuya Radiators (Hybrid) integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "tuya_radiators"

# Borrowed-manager mode: we reuse an already-loaded Tuya integration's
# Manager instead of doing our own sign-in. Entry data records which one.
CONF_HOST_DOMAIN: Final = "host_domain"
CONF_HOST_ENTRY_ID: Final = "host_entry_id"
CONF_DEVICES: Final = "devices"

# Per-device (entries in CONF_DEVICES list)
CONF_DEVICE_ID: Final = "device_id"
CONF_HOST: Final = "host"
CONF_LOCAL_KEY: Final = "local_key"
CONF_MODEL: Final = "model"
CONF_NAME: Final = "name"
CONF_PROTOCOL: Final = "protocol"
CONF_PRODUCT_ID: Final = "product_id"

DEFAULT_PROTOCOL: Final = "3.3"
SUPPORTED_PROTOCOLS: Final = ("3.3", "3.4")

# Local TCP behaviour
HEARTBEAT_INTERVAL_S: Final = 9.0
SOCKET_READ_TIMEOUT_S: Final = 8.0
INITIAL_RECONNECT_DELAY_S: Final = 1.0
MAX_RECONNECT_DELAY_S: Final = 30.0
RECONNECT_BACKOFF_FACTOR: Final = 2.0
COMMAND_RETRY_LIMIT: Final = 2

# Cloud behaviour
RECONCILE_INTERVAL_S: Final = 30.0
CLOUD_WRITE_CONFIRM_DELAY_S: Final = 2.0

# Reliability tuning (v0.5)
OPTIMISTIC_GUARD_S: Final = 30.0  # how long the reconcile loop honours an optimistic write
WRITE_RETRY_DELAY_S: Final = 2.0  # backoff before retrying a failed cloud write once
STALE_RECONCILE_S: Final = 90.0   # entities go unavailable if cloud reconcile hasn't run for this long
FAILURE_THRESHOLD: Final = 3       # consecutive failures (writes OR reconciles) before raising a repair issue

DEVICE_ID_LENGTH: Final = 22
LOCAL_KEY_LENGTH: Final = 16
