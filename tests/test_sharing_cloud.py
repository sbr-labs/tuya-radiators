"""Tests for the borrowed-manager cloud adapter.

These exercise the pure mapping logic and the return-value
interpretation that bit us in field-testing (Tuya SDK's send_commands
silently returns None, with a hidden 10 s dedup filter).
"""

from __future__ import annotations

import asyncio
import types
from typing import Any
from unittest.mock import MagicMock

import pytest

from tuya_radiators.models import ECOSTRAD_IQCERAMIC
from tuya_radiators.sharing_cloud import (
    SharingCloud,
    SharingCloudAuthError,
    SharingCloudError,
    list_radiator_devices,
)


def _fake_device(**kw) -> Any:
    """Light stand-in for tuya_sharing.CustomerDevice (SimpleNamespace)."""
    defaults = dict(
        id="bf" + "x" * 20,
        name="Test",
        local_key="k" * 16,
        ip="192.0.2.1",
        product_id="7vmieyhabmukishx",
        category="wk",
        status={},
    )
    defaults.update(kw)
    return types.SimpleNamespace(**defaults)


def _fake_manager(devices: dict[str, Any]):
    m = MagicMock()
    m.device_map = devices
    return m


def _make_cloud(manager, hass=None, entry=None):
    """Build a SharingCloud whose _manager() returns the given manager."""
    cloud = SharingCloud.__new__(SharingCloud)
    cloud._hass = hass or MagicMock()
    cloud._entry = entry or MagicMock()
    cloud._host_domain = "tuya"
    cloud._host_entry_id = "test"
    cloud._call_lock = asyncio.Lock()
    cloud._manager = lambda: manager
    return cloud


# ---- status mapping --------------------------------------------------


def test_get_status_by_dp_translates_codes_to_dp_ids():
    """Cloud reports status keyed by code; we must return dp_id-keyed dict."""
    device = _fake_device(status={
        "switch": False,
        "temp_set": 225,
        "temp_current": 210,
        "child_lock": True,
        "Open_Window": "Off",
        "mode": "only_inside",
    })
    cloud = _make_cloud(_fake_manager({"dev1": device}))
    async def _exec(fn, *a):
        return fn(*a)
    cloud._hass.async_add_executor_job = _exec
    out = asyncio.run(cloud.async_get_status_by_dp("dev1", ECOSTRAD_IQCERAMIC))
    assert out[1] is False       # power dp = 1
    assert out[16] == 225        # target_temp dp = 16
    assert out[24] == 210        # current_temp dp = 24
    assert out[40] is True       # child_lock dp = 40
    assert out[108] == "Off"     # Open_Window dp = 108
    assert out[2] == "only_inside"  # mode dp = 2


def test_get_status_unknown_codes_are_ignored():
    """Codes the profile doesn't know about must not pollute the output."""
    device = _fake_device(status={
        "switch": True,
        "week_program8": "AAAA",         # unmapped
        "boost_time": 0,                  # unmapped
        "xt_device_event_notify": "{}",   # unmapped
    })
    cloud = _make_cloud(_fake_manager({"dev1": device}))
    async def _exec(fn, *a):
        return fn(*a)
    cloud._hass.async_add_executor_job = _exec
    out = asyncio.run(cloud.async_get_status_by_dp("dev1", ECOSTRAD_IQCERAMIC))
    assert out == {1: True}


def test_get_status_missing_device_returns_empty():
    cloud = _make_cloud(_fake_manager({}))  # no devices
    out = asyncio.run(cloud.async_get_status_by_dp("missing", ECOSTRAD_IQCERAMIC))
    assert out == {}


# ---- device-online flag (used by binary_sensor.online) --------------


def test_is_device_online_reflects_cloud_flag():
    """The binary_sensor.online must track the cloud's per-device flag,
    not just whether we've ever talked to cloud."""
    online_dev = _fake_device(online=True)
    offline_dev = _fake_device(id="other", online=False)
    cloud = _make_cloud(_fake_manager({"on": online_dev, "off": offline_dev}))
    assert cloud.is_device_online("on") is True
    assert cloud.is_device_online("off") is False
    assert cloud.is_device_online("missing") is None


# ---- write path / send_commands result interpretation ---------------


def test_send_dps_treats_none_as_success():
    """tuya_sharing.DeviceRepository.send_commands has NO return statement;
    it always returns None even on success. We must not treat None as failure
    (that was the source of the 'state bounces back' bug)."""
    manager = _fake_manager({"d": _fake_device()})
    manager.send_commands = MagicMock(return_value=None)
    cloud = _make_cloud(manager)
    async def _exec(fn, *a):
        return fn(*a)
    cloud._hass.async_add_executor_job = _exec
    ok = asyncio.run(cloud.async_send_dps("d", ECOSTRAD_IQCERAMIC, {1: True}))
    assert ok is True


def test_send_dps_treats_explicit_false_as_failure():
    """xtend_tuya's MultiManager.send_commands returns bool. False = real failure."""
    manager = _fake_manager({"d": _fake_device()})
    manager.send_commands = MagicMock(return_value=False)
    cloud = _make_cloud(manager)
    async def _exec(fn, *a):
        return fn(*a)
    cloud._hass.async_add_executor_job = _exec
    ok = asyncio.run(cloud.async_send_dps("d", ECOSTRAD_IQCERAMIC, {1: True}))
    assert ok is False


def test_send_dps_translates_dp_to_code():
    """Our entities think in dp_id; cloud /commands API wants code strings."""
    manager = _fake_manager({"d": _fake_device()})
    captured = {}

    def capture(device_id, commands):
        captured["device_id"] = device_id
        captured["commands"] = commands
        return None

    manager.send_commands = capture
    cloud = _make_cloud(manager)
    async def _exec(fn, *a):
        return fn(*a)
    cloud._hass.async_add_executor_job = _exec
    asyncio.run(cloud.async_send_dps(
        "d", ECOSTRAD_IQCERAMIC, {1: True, 16: 225}
    ))
    assert captured["device_id"] == "d"
    # Order isn't important, but both must be present, code-keyed
    by_code = {c["code"]: c["value"] for c in captured["commands"]}
    assert by_code == {"switch": True, "temp_set": 225}


def test_send_dps_drops_unmapped_dps():
    """If a dp has no Tuya code in the profile, we skip it rather than
    sending a bogus command."""
    manager = _fake_manager({"d": _fake_device()})
    manager.send_commands = MagicMock(return_value=None)
    cloud = _make_cloud(manager)
    async def _exec(fn, *a):
        return fn(*a)
    cloud._hass.async_add_executor_job = _exec
    # dp 999 has no code in the Ecostrad profile
    ok = asyncio.run(cloud.async_send_dps("d", ECOSTRAD_IQCERAMIC, {999: 1}))
    assert ok is False
    manager.send_commands.assert_not_called()


# ---- error wrapping --------------------------------------------------


def test_send_dps_wraps_token_errors_as_auth_error():
    """An exception with 'token' or 'invalid' in the message must surface
    as SharingCloudAuthError so the entry-setup path can raise
    ConfigEntryAuthFailed and trigger reauth."""
    manager = _fake_manager({"d": _fake_device()})
    manager.send_commands = MagicMock(side_effect=Exception("token expired"))
    cloud = _make_cloud(manager)
    async def _exec(fn, *a):
        return fn(*a)
    cloud._hass.async_add_executor_job = _exec
    with pytest.raises(SharingCloudAuthError):
        asyncio.run(cloud.async_send_dps("d", ECOSTRAD_IQCERAMIC, {1: True}))


def test_send_dps_wraps_generic_errors_as_cloud_error():
    manager = _fake_manager({"d": _fake_device()})
    manager.send_commands = MagicMock(side_effect=Exception("network down"))
    cloud = _make_cloud(manager)
    async def _exec(fn, *a):
        return fn(*a)
    cloud._hass.async_add_executor_job = _exec
    with pytest.raises(SharingCloudError):
        asyncio.run(cloud.async_send_dps("d", ECOSTRAD_IQCERAMIC, {1: True}))


# ---- write serialization (the sign-invalid burst race fix) ----------


def test_concurrent_sends_are_serialized():
    """Overlapping writes through the borrowed manager must NOT run at the
    same time — concurrent request-signing is what produced `sign invalid`
    on all-but-one of a burst (field-confirmed 2026-05-27)."""
    manager = _fake_manager({"d": _fake_device()})
    overlap = {"current": 0, "max": 0}

    async def main():
        cloud = _make_cloud(manager)

        async def _exec(fn, *a):
            # Simulate the blocking SDK call: mark that we're "inside" the
            # signed call and yield, so any overlap would be observed.
            overlap["current"] += 1
            overlap["max"] = max(overlap["max"], overlap["current"])
            await asyncio.sleep(0)
            overlap["current"] -= 1
            return None

        cloud._hass.async_add_executor_job = _exec
        await asyncio.gather(*(
            cloud.async_send_dps("d", ECOSTRAD_IQCERAMIC, {16: 200 + i})
            for i in range(5)
        ))

    asyncio.run(main())
    assert overlap["max"] == 1, "writes overlapped — lock not serializing"


# ---- forced token refresh (the stale-token self-heal) ---------------


def test_force_token_refresh_resets_expiry():
    """On `sign invalid` we reset the borrowed token's cached expiry so the
    SDK refreshes on the next request instead of needing a manual reload."""
    manager = _fake_manager({"d": _fake_device()})
    manager.customer_api = types.SimpleNamespace(
        token_info=types.SimpleNamespace(expire_time=9_999_999_999)
    )
    cloud = _make_cloud(manager)
    did = asyncio.run(cloud.async_force_token_refresh())
    assert did is True
    assert manager.customer_api.token_info.expire_time == 0


def test_force_token_refresh_noops_when_no_token():
    """If the borrowed manager isn't shaped as expected, degrade quietly."""
    # Plain object (not MagicMock) so missing attrs really resolve to None.
    manager = types.SimpleNamespace(device_map={"d": _fake_device()})
    cloud = _make_cloud(manager)
    assert asyncio.run(cloud.async_force_token_refresh()) is False


# ---- host discovery / device filtering ------------------------------


def test_list_radiator_devices_filters_by_product_id():
    """Devices with a known FLS-118C product_id should always be listed."""
    hass = MagicMock()
    entry = MagicMock()
    entry.state.value = "loaded"
    entry.entry_id = "e1"
    entry.runtime_data = types.SimpleNamespace(manager=_fake_manager({
        "rad": _fake_device(product_id="7vmieyhabmukishx", category="wk",
                            name="Bedroom"),
        "plug": _fake_device(product_id="some_plug_id", category="kg"),
    }))
    hass.config_entries.async_entries = lambda d: [entry] if d == "tuya" else []
    out = list_radiator_devices(hass)
    assert len(out) == 1
    assert out[0]["name"] == "Bedroom"
    assert out[0]["host_domain"] == "tuya"


def test_list_radiator_devices_includes_heating_categories():
    """Devices without a known product_id but in the wk/qn heating
    categories should also be offered."""
    hass = MagicMock()
    entry = MagicMock()
    entry.state.value = "loaded"
    entry.entry_id = "e2"
    entry.runtime_data = types.SimpleNamespace(manager=_fake_manager({
        "unknown_rad": _fake_device(product_id="never_seen", category="wk",
                                    name="Unknown Heater"),
    }))
    hass.config_entries.async_entries = lambda d: [entry] if d == "tuya" else []
    out = list_radiator_devices(hass)
    assert len(out) == 1
    assert out[0]["name"] == "Unknown Heater"


def test_list_radiator_devices_skips_unloaded_hosts():
    """An entry that isn't fully loaded must not be borrowed from."""
    hass = MagicMock()
    entry = MagicMock()
    entry.state.value = "setup_in_progress"  # not loaded
    entry.runtime_data = None
    hass.config_entries.async_entries = lambda d: [entry] if d == "tuya" else []
    out = list_radiator_devices(hass)
    assert out == []
