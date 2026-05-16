"""Tuya Radiators (Hybrid) integration entry point."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

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
]


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
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    account: TuyaRadiatorAccount | None = hass.data.get(DOMAIN, {}).pop(
        entry.entry_id, None
    )
    if account is not None:
        await account.async_stop()
    return unload_ok
