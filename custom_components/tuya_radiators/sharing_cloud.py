"""Borrowed-manager wrapper.

Tuya's sharing-flow auth has issues with running multiple HA integrations
against the same account — fresh tokens get rejected with `sign invalid`
even though pre-existing tuya / xtend_tuya managers continue to work
(observed 2026-05-16).

So rather than authenticating ourselves, we borrow the already-loaded
tuya_sharing.Manager from one of the other Tuya integrations on this
HAOS install:

  * `tuya` (official HA core integration) — preferred when present;
     plain `tuya_sharing.Manager` on `entry.runtime_data.manager`.
  * `xtend_tuya` (Xtend Tuya custom integration) — fallback; subclasses
     `Manager` as `MultiManager`, stored on
     `entry.runtime_data.multi_manager`.

This means we never create a second sign-in, never run our own MQTT,
and never manage tokens — the host integration does all of that. We
just adapt its API to dp_id-keyed reads/writes that the rest of the
integration thinks in.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_HOST_DOMAIN, CONF_HOST_ENTRY_ID
from .models import ModelProfile, profile_for_product

# Tuya category codes for heating devices. wk = heating; qn = electric heater.
# Used as a fallback when product_id isn't in our known-models list.
_HEATING_CATEGORIES = frozenset({"wk", "qn"})

_LOGGER = logging.getLogger(__name__)

# Domain -> attribute path on entry.runtime_data that yields the Manager.
HOST_PRIORITY: list[tuple[str, tuple[str, ...]]] = [
    ("tuya", ("manager",)),
    ("xtend_tuya", ("multi_manager",)),
]


class SharingCloudError(Exception):
    """Borrowed-manager call failed."""


class SharingCloudAuthError(SharingCloudError):
    """Host integration's manager is unavailable; user must re-auth there."""


def find_host(
    hass: HomeAssistant,
) -> tuple[str, str] | None:
    """Return (domain, entry_id) of the first loaded host integration, or None."""
    for domain, _path in HOST_PRIORITY:
        for entry in hass.config_entries.async_entries(domain):
            if entry.state.recoverable or str(entry.state) == "ConfigEntryState.LOADED":
                # `entry.state` is an enum; loaded check via repr to avoid importing it
                pass
            if entry.state.value == "loaded" and getattr(entry, "runtime_data", None):
                return domain, entry.entry_id
    return None


def list_radiator_devices(hass: HomeAssistant) -> list[dict[str, Any]]:
    """List heating-class devices visible to any loaded Tuya host integration.

    Filtering rule: a device is included if (a) its Tuya `product_id` is
    in our known-models map, OR (b) its Tuya `category` is a heating
    category (`wk` / `qn`). Non-heating devices (lights, plugs, etc.)
    are skipped — they belong to the host integration, not us.
    """
    seen: dict[str, dict[str, Any]] = {}
    for domain, path in HOST_PRIORITY:
        for entry in hass.config_entries.async_entries(domain):
            if entry.state.value != "loaded":
                continue
            manager = _resolve_manager(entry, path)
            if manager is None:
                continue
            for dev_id, device in (getattr(manager, "device_map", {}) or {}).items():
                if dev_id in seen:
                    continue
                product_id = getattr(device, "product_id", "") or ""
                category = getattr(device, "category", "") or ""
                if (
                    profile_for_product(product_id) is None
                    and category not in _HEATING_CATEGORIES
                ):
                    continue
                local_key = getattr(device, "local_key", "") or ""
                ip = getattr(device, "ip", "") or ""
                seen[dev_id] = {
                    "id": dev_id,
                    "name": getattr(device, "name", "") or dev_id,
                    "product_id": product_id,
                    "category": category,
                    "local_key": local_key,
                    "ip": ip,
                    "host_domain": domain,
                    "host_entry_id": entry.entry_id,
                }
    return list(seen.values())


def _resolve_manager(entry: ConfigEntry, path: tuple[str, ...]) -> Any | None:
    obj = getattr(entry, "runtime_data", None)
    for attr in path:
        if obj is None:
            return None
        obj = getattr(obj, attr, None)
    return obj


class SharingCloud:
    """Thin adapter over a borrowed Tuya Manager from another integration."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self._hass = hass
        self._entry = entry
        self._host_domain: str = entry.data.get(CONF_HOST_DOMAIN, "")
        self._host_entry_id: str = entry.data.get(CONF_HOST_ENTRY_ID, "")
        # Serializes every signed API call we make through the borrowed
        # manager. tuya_sharing signs each request with a per-request
        # timestamp/nonce and refreshes its token lazily — none of that is
        # concurrency-safe, so overlapping calls make all-but-one come back
        # `sign invalid`. One SharingCloud is shared by all of an account's
        # radiator coordinators, so this instance lock serializes them all.
        self._call_lock = asyncio.Lock()

    def _manager(self) -> Any:
        """Resolve the current borrowed Manager, or raise SharingCloudAuthError."""
        path = next(
            (p for d, p in HOST_PRIORITY if d == self._host_domain),
            None,
        )
        if path is None:
            # Stored host_domain unknown — try priority list afresh.
            host = find_host(self._hass)
            if host is None:
                raise SharingCloudAuthError(
                    "No loaded Tuya integration available to borrow from"
                )
            self._host_domain, self._host_entry_id = host
            path = next(p for d, p in HOST_PRIORITY if d == self._host_domain)
        entry = self._hass.config_entries.async_get_entry(self._host_entry_id)
        if entry is None or entry.state.value != "loaded":
            # Host entry was removed/disabled; try any other loaded host.
            host = find_host(self._hass)
            if host is None:
                raise SharingCloudAuthError(
                    "Host Tuya integration is not loaded"
                )
            self._host_domain, self._host_entry_id = host
            entry = self._hass.config_entries.async_get_entry(self._host_entry_id)
            path = next(p for d, p in HOST_PRIORITY if d == self._host_domain)
        manager = _resolve_manager(entry, path)
        if manager is None:
            raise SharingCloudAuthError(
                f"Host integration {self._host_domain} has no manager"
            )
        return manager

    async def async_refresh_devices(self) -> None:
        """Refresh the host manager's device cache (best-effort)."""
        manager = self._manager()
        try:
            async with self._call_lock:
                await self._hass.async_add_executor_job(manager.update_device_cache)
        except Exception as err:  # noqa: BLE001
            raise self._wrap(err) from err

    async def async_force_token_refresh(self) -> bool:
        """Nudge the borrowed manager to refresh its access token.

        A `sign invalid` rejection means the token the host integration
        handed us is stale — often invalidated server-side (e.g. by another
        login on the account) without the SDK noticing. tuya_sharing only
        auto-refreshes when it believes the token is near expiry, so we
        reset the cached expiry to force a refresh on the next request.

        Best-effort and version-tolerant: silently no-ops (returns False)
        if the borrowed manager's internals aren't shaped as expected, so a
        future SDK change degrades to "manual reload still works" rather
        than crashing the write path.
        """
        try:
            manager = self._manager()
        except SharingCloudError:
            return False
        api = getattr(manager, "customer_api", None) or getattr(manager, "api", None)
        token_info = getattr(api, "token_info", None)
        if token_info is None or not hasattr(token_info, "expire_time"):
            _LOGGER.debug(
                "token-refresh nudge: borrowed %s manager has no resettable token",
                self._host_domain,
            )
            return False
        try:
            token_info.expire_time = 0
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("token-refresh nudge failed: %s", err)
            return False
        _LOGGER.debug("forced token-expiry reset on borrowed %s manager", self._host_domain)
        return True

    def device(self, device_id: str) -> Any | None:
        manager = self._manager()
        return (manager.device_map or {}).get(device_id)

    def all_devices(self) -> list:
        return list(self._manager().device_map.values())

    def is_device_online(self, device_id: str) -> bool | None:
        """Cloud's view of whether the radiator is currently reachable.

        Different from `available` (which is "have we ever talked to
        cloud") — this tracks the device's own WiFi connection. None
        if we don't have the device in our map at all.
        """
        device = self.device(device_id)
        if device is None:
            return None
        return bool(getattr(device, "online", False))

    async def async_get_status_by_dp(
        self, device_id: str, profile: ModelProfile
    ) -> dict[int, Any]:
        manager = self._manager()
        device = manager.device_map.get(device_id)
        if device is None:
            return {}
        status = getattr(device, "status", {}) or {}
        _LOGGER.debug(
            "device %s raw status keys=%s, mapped: %s",
            device_id[:8],
            list(status.keys()),
            {k: v for k, v in status.items()},
        )
        out: dict[int, Any] = {}
        for code, value in status.items():
            dp = profile.dp_for_code(code)
            if dp is None:
                continue
            out[dp] = value
        return out

    async def async_send_dps(
        self,
        device_id: str,
        profile: ModelProfile,
        dps: dict[int, Any],
    ) -> bool:
        commands: list[dict[str, Any]] = []
        for dp, value in dps.items():
            code = profile.code_for_dp(dp)
            if code is None:
                _LOGGER.warning(
                    "no code mapped for dp_id %s on profile %s — dropping",
                    dp,
                    profile.key,
                )
                continue
            commands.append({"code": code, "value": value})
        if not commands:
            return False
        manager = self._manager()
        try:
            # Serialize: never sign two requests through the borrowed
            # manager at once (see _call_lock docstring).
            async with self._call_lock:
                result = await self._hass.async_add_executor_job(
                    manager.send_commands, device_id, commands
                )
        except Exception as err:  # noqa: BLE001
            raise self._wrap(err) from err
        _LOGGER.debug(
            "send_commands device=%s cmds=%s result=%r",
            device_id[:8], commands, result,
        )
        # Return-value semantics across the two SDKs we borrow from:
        #   * official tuya_sharing.DeviceRepository.send_commands has NO
        #     return statement — always returns None (it just calls
        #     api.post and discards the response). It also has a 10 s
        #     dedup filter that silently drops repeated identical
        #     commands. So None means "no exception raised; treat as
        #     success" because we have no other signal.
        #   * xtend_tuya's MultiManager.send_commands returns a bool.
        # We therefore only treat an explicit False as failure.
        if result is False:
            return False
        if isinstance(result, dict):
            return bool(result.get("success", True))
        return True

    async def async_close(self) -> None:
        # We don't own the manager; nothing to tear down.
        return None

    @staticmethod
    def _wrap(err: Exception) -> SharingCloudError:
        msg = str(err)
        lower = msg.lower()
        if any(s in lower for s in ("token", "invalid", "expired", "1010", "1011")):
            return SharingCloudAuthError(msg)
        return SharingCloudError(msg)
