"""Tuya Radiators (Hybrid) integration entry point."""

from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv

from .account import TuyaRadiatorAccount
from .const import DOMAIN
from .sharing_cloud import SharingCloudAuthError, SharingCloudError

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.CLIMATE,
    Platform.SWITCH,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
]

SERVICE_REFRESH = "refresh"
REFRESH_SCHEMA = vol.Schema({vol.Optional("device_id"): cv.string})


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Bring one Tuya account online: cloud client + per-radiator coordinators."""
    account = TuyaRadiatorAccount(hass, entry)
    try:
        await account.async_start()
    except SharingCloudAuthError as err:
        await account.async_stop()
        raise ConfigEntryAuthFailed(str(err)) from err
    except SharingCloudError as err:
        await account.async_stop()
        raise ConfigEntryNotReady(str(err)) from err
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = account
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _async_register_services(hass)
    return True


def _async_register_services(hass: HomeAssistant) -> None:
    """Register integration-wide services. Idempotent."""
    if hass.services.has_service(DOMAIN, SERVICE_REFRESH):
        return

    async def _refresh(call: ServiceCall) -> None:
        target_id = call.data.get("device_id")
        accounts: dict[str, TuyaRadiatorAccount] = hass.data.get(DOMAIN, {})
        for account in accounts.values():
            for coord in account.all_coordinators():
                if target_id and coord.device_id != target_id:
                    continue
                try:
                    state = await coord.cloud.async_get_status_by_dp(
                        coord.device_id, coord.profile
                    )
                except SharingCloudError as err:
                    _LOGGER.warning(
                        "%s refresh failed: %s", coord.name, err
                    )
                    continue
                if state:
                    coord.merge_cloud_state(state)

    hass.services.async_register(DOMAIN, SERVICE_REFRESH, _refresh, schema=REFRESH_SCHEMA)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    account: TuyaRadiatorAccount | None = hass.data.get(DOMAIN, {}).pop(
        entry.entry_id, None
    )
    if account is not None:
        await account.async_stop()
    return unload_ok
