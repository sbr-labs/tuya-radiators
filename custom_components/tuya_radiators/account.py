"""Per-account state for the Tuya Radiators integration.

A single config entry corresponds to one signed-in Tuya / Smart Life
account. Each account owns:

  * a SharingCloud wrapper (tuya_sharing.Manager) for cloud reads/writes,
    with a token listener that persists refreshed tokens back into the
    config entry data
  * a RadiatorCoordinator per linked radiator (local TCP push + cloud
    write proxy)
  * a 30-second reconciliation task that pulls device status from the
    cloud and merges into each coordinator (catches changes made in the
    Tuya app outside HA)

Reads:   local TCP push (real-time) + cloud poll every 30 s.
Writes:  always via cloud /commands API (firmware drops local writes).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from .const import (
    CONF_DEVICES,
    DOMAIN,
    RECONCILE_INTERVAL_S,
)
from .coordinator import RadiatorCoordinator
from .models import get_profile
from .sharing_cloud import (
    SharingCloud,
    SharingCloudAuthError,
    SharingCloudError,
)

_LOGGER = logging.getLogger(__name__)


class TuyaRadiatorAccount:
    """One signed-in Tuya account plus its radiator coordinators."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.cloud = SharingCloud(hass, entry)
        self.coordinators: dict[str, RadiatorCoordinator] = {}
        self._reconcile_task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        self._auth_issue_active = False

    @property
    def devices(self) -> list[dict[str, Any]]:
        return list(self.entry.data.get(CONF_DEVICES, []))

    async def async_start(self) -> None:
        """Spin up coordinators and kick off reconcile.

        We don't need to refresh the device cache ourselves — the host
        integration we borrow from already keeps its device_map fresh.
        We just need a healthy reference to its Manager.
        """
        try:
            # Touch the borrowed manager so any wiring error surfaces now
            # rather than on the first reconcile tick.
            self.cloud.all_devices()
        except SharingCloudAuthError as err:
            self._raise_auth_issue(err)
            raise
        for spec in self.devices:
            await self._add_coordinator(spec)
        # First reconcile inline so entities have state by the time HA
        # registers them — otherwise users stare at "unavailable" for up
        # to RECONCILE_INTERVAL_S after every reload.
        await self._reconcile_once()
        self._reconcile_task = self.hass.loop.create_task(
            self._reconcile_loop(), name=f"{DOMAIN}_reconcile"
        )

    async def async_stop(self) -> None:
        self._stop_event.set()
        if self._reconcile_task is not None:
            self._reconcile_task.cancel()
            try:
                await self._reconcile_task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        for coordinator in list(self.coordinators.values()):
            await coordinator.async_stop()
        self.coordinators.clear()
        await self.cloud.async_close()

    async def _add_coordinator(self, spec: dict[str, Any]) -> None:
        try:
            profile = get_profile(spec["model"])
        except KeyError:
            _LOGGER.error(
                "Skipping device %s: unknown model '%s'",
                spec.get("device_id"),
                spec.get("model"),
            )
            return
        coordinator = RadiatorCoordinator(
            hass=self.hass,
            entry=self.entry,
            profile=profile,
            device_id=spec["device_id"],
            host=spec["host"],
            local_key=spec["local_key"],
            name=spec.get("name") or spec["device_id"],
            protocol=spec.get("protocol") or profile.protocol,
            cloud=self.cloud,
        )
        coordinator.async_start()
        self.coordinators[spec["device_id"]] = coordinator

    async def _reconcile_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(), timeout=RECONCILE_INTERVAL_S
                )
                return
            except asyncio.TimeoutError:
                pass
            await self._reconcile_once()

    async def _reconcile_once(self) -> None:
        for device_id, coordinator in list(self.coordinators.items()):
            try:
                state = await self.cloud.async_get_status_by_dp(
                    device_id, coordinator.profile
                )
            except SharingCloudAuthError as err:
                self._raise_auth_issue(err)
                return
            except SharingCloudError as err:
                _LOGGER.debug("reconcile %s failed: %s", device_id, err)
                continue
            except Exception:  # noqa: BLE001
                _LOGGER.exception("reconcile %s crashed", device_id)
                continue
            if state:
                coordinator.merge_cloud_state(state)
                self._clear_auth_issue()

    def _raise_auth_issue(self, err: SharingCloudError) -> None:
        if self._auth_issue_active:
            return
        self._auth_issue_active = True
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            f"auth_{self.entry.entry_id}",
            is_fixable=True,
            severity=ir.IssueSeverity.ERROR,
            translation_key="reauth_required",
            translation_placeholders={"error": str(err)},
            data={"entry_id": self.entry.entry_id},
        )

    def _clear_auth_issue(self) -> None:
        if not self._auth_issue_active:
            return
        self._auth_issue_active = False
        ir.async_delete_issue(self.hass, DOMAIN, f"auth_{self.entry.entry_id}")

    def all_coordinators(self) -> Iterable[RadiatorCoordinator]:
        return self.coordinators.values()
