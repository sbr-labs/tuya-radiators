"""Tests for the per-radiator coordinator.

Covers the two pieces of logic that were rewritten the most during
field-testing: optimistic-merge writes and the reconcile write-guard.
"""

from __future__ import annotations

import asyncio
import time
import types
from unittest.mock import MagicMock

import pytest

from tuya_radiators.coordinator import RadiatorCoordinator
from tuya_radiators.models import ECOSTRAD_IQCERAMIC
from tuya_radiators.sharing_cloud import SharingCloudError


def _make_coordinator(*, send_result=True, send_raises=None):
    """Build a RadiatorCoordinator with a fully-stubbed cloud + LAN client."""
    hass = MagicMock()
    hass.loop.call_later = MagicMock()
    hass.async_add_executor_job = MagicMock(
        side_effect=lambda fn, *a: fn(*a)
    )

    cloud = MagicMock()
    if send_raises is not None:
        async def _raise(*_a, **_k):
            raise send_raises
        cloud.async_send_dps = _raise
    else:
        async def _send(*_a, **_k):
            return send_result
        cloud.async_send_dps = _send

    # Avoid spinning up tuya_protocol's real socket
    coord = RadiatorCoordinator.__new__(RadiatorCoordinator)
    coord.hass = hass
    coord.entry = MagicMock()
    coord.profile = ECOSTRAD_IQCERAMIC
    coord.device_id = "dev1"
    coord.host = "1.2.3.4"
    coord.name = "Test Rad"
    coord._cloud = cloud
    coord._listeners = []
    coord._state = {}
    coord._optimistic_guard = {}
    coord._local_connected = False
    coord._cloud_alive = True
    coord._last_local_push = 0.0
    coord._last_cloud_poll = 0.0
    coord.client = MagicMock()
    return coord


# ---- optimistic merge ------------------------------------------------


def test_set_dps_writes_state_before_awaiting_cloud():
    """Optimistic-first: state must reflect the new value as soon as
    async_set_dps yields, not when the cloud round-trip completes."""
    coord = _make_coordinator()
    notifications: list[dict] = []
    coord._listeners.append(lambda: notifications.append(dict(coord._state)))
    ok = asyncio.run(coord.async_set_dps(1, True))
    assert ok is True
    assert coord._state[1] is True
    # First notify happens BEFORE the cloud await returns — verified by
    # the listener observing the new state.
    assert notifications and notifications[0][1] is True


def test_set_dps_reverts_on_cloud_failure():
    """If cloud explicitly rejects (returns False), revert local state."""
    coord = _make_coordinator(send_result=False)
    coord._state[1] = False  # prior known state
    notifications: list[dict] = []
    coord._listeners.append(lambda: notifications.append(dict(coord._state)))
    ok = asyncio.run(coord.async_set_dps(1, True))
    assert ok is False
    assert coord._state[1] is False  # reverted
    # We should have notified twice: optimistic merge, then revert.
    assert [n[1] for n in notifications] == [True, False]


def test_set_dps_reverts_on_cloud_exception():
    """Network error from cloud must also revert."""
    coord = _make_coordinator(send_raises=SharingCloudError("network"))
    coord._state[40] = True
    ok = asyncio.run(coord.async_set_dps(40, False))
    assert ok is False
    assert coord._state[40] is True  # reverted to True


def test_set_dps_revert_removes_dp_if_not_previously_set():
    """If we didn't have the dp before, revert should DELETE it, not leave
    it set to None."""
    coord = _make_coordinator(send_result=False)
    assert 1 not in coord._state
    asyncio.run(coord.async_set_dps(1, True))
    assert 1 not in coord._state


# ---- write-guard against reconcile -----------------------------------


def test_optimistic_guard_blocks_stale_cloud_overwrite():
    """The bug we hit on 2026-05-16: 30s reconcile fetches Tuya cloud
    before our write has propagated, sees the OLD value, and overwrites
    our optimistic flip. Guard must prevent this."""
    coord = _make_coordinator()
    asyncio.run(coord.async_set_dps(1, True))
    assert coord._state[1] is True
    assert 1 in coord._optimistic_guard

    # Reconcile arrives with stale cloud state (still says False)
    coord.merge_cloud_state({1: False})
    # Guard must have protected our optimistic value
    assert coord._state[1] is True
    assert 1 in coord._optimistic_guard


def test_optimistic_guard_drops_when_cloud_catches_up():
    """When the cloud reflects our written value, the guard is satisfied
    and dropped (so a subsequent external change can be detected normally)."""
    coord = _make_coordinator()
    asyncio.run(coord.async_set_dps(1, True))
    coord.merge_cloud_state({1: True})
    # Cloud matches our write -> guard satisfied, dropped
    assert 1 not in coord._optimistic_guard
    assert coord._state[1] is True


def test_optimistic_guard_expires_after_window():
    """Guard must not be eternal — after the window, cloud wins again
    so an external Tuya-app change can still be picked up even if it
    happens to be the same value as our prior write."""
    coord = _make_coordinator()
    asyncio.run(coord.async_set_dps(1, True))
    # Simulate guard expiration by rewinding the deadline
    deadline, expected = coord._optimistic_guard[1]
    coord._optimistic_guard[1] = (time.monotonic() - 1.0, expected)

    coord.merge_cloud_state({1: False})
    # Guard expired -> cloud value accepted
    assert coord._state[1] is False
    assert 1 not in coord._optimistic_guard


def test_merge_cloud_state_no_op_for_empty_state():
    """An empty status dict from the SDK must not flap our state."""
    coord = _make_coordinator()
    coord._state = {1: True, 40: False}
    coord.merge_cloud_state({})
    assert coord._state == {1: True, 40: False}


def test_merge_cloud_state_updates_unwritten_dps_normally():
    """Dps without an active guard should be updated by reconcile —
    this is how external Tuya-app changes get reflected in HA."""
    coord = _make_coordinator()
    coord._state = {1: False}
    coord.merge_cloud_state({1: True, 24: 215})
    assert coord._state == {1: True, 24: 215}


# ---- read-side basics ------------------------------------------------


def test_get_dps_returns_state_value():
    coord = _make_coordinator()
    coord._state[16] = 225
    assert coord.get_dps(16) == 225
    assert coord.get_dps(999) is None


def test_available_reflects_cloud_or_local():
    coord = _make_coordinator()
    coord._local_connected = False
    coord._cloud_alive = False
    assert coord.available is False
    coord._cloud_alive = True
    assert coord.available is True
    coord._cloud_alive = False
    coord._local_connected = True
    assert coord.available is True
