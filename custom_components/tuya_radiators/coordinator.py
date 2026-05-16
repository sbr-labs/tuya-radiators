"""Per-radiator coordinator (hybrid: local read, cloud write).

Owns one TuyaRadiatorClient (LAN telemetry tap) and a reference to the
account-level TuyaCloudClient (for writes). State is push-driven:

  * Local TCP frames arrive every ~1 s with the live DPS map. We merge
    them into _state and notify listeners — this is the fast path that
    keeps current_temperature live regardless of cloud health.
  * Cloud writes are issued via the /commands API. The firmware silently
    drops any local DPS writes, so cloud is the only viable path. After
    a write we schedule a short cloud poll to confirm the change.
  * The account's reconcile loop calls merge_cloud_state() every 30 s
    to catch changes made in the Tuya app.

`available` reflects EITHER local-push reachability OR successful cloud
poll. The user sees an unavailable entity only when both paths are dead.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback

from .const import CLOUD_WRITE_CONFIRM_DELAY_S, DOMAIN
from .models import ModelProfile
from .sharing_cloud import SharingCloud, SharingCloudError
from .tuya_protocol import TuyaRadiatorClient

_LOGGER = logging.getLogger(__name__)


class RadiatorCoordinator:
    """Single radiator: local-push read + cloud write."""

    def __init__(
        self,
        *,
        hass: HomeAssistant,
        entry: ConfigEntry,
        profile: ModelProfile,
        device_id: str,
        host: str,
        local_key: str,
        name: str,
        protocol: str,
        cloud: SharingCloud,
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.profile = profile
        self.device_id = device_id
        self.host = host
        self.name = name
        self._cloud = cloud

        self._listeners: list[Callable[[], None]] = []
        self._state: dict[int, Any] = {}
        # dp -> (deadline_monotonic, expected_cloud_value) for DPs we
        # just wrote and are waiting on Tuya cloud to propagate. While
        # a guard is active, merge_cloud_state ignores stale cloud reads
        # for that DP — otherwise the 30 s reconcile would clobber our
        # optimistic value before Tuya catches up (1–10 s latency typical).
        self._optimistic_guard: dict[int, tuple[float, Any]] = {}
        self._local_connected = False
        self._cloud_alive = False
        self._last_local_push: float = 0.0
        self._last_cloud_poll: float = 0.0

        self.client = TuyaRadiatorClient(
            loop=hass.loop,
            device_id=device_id,
            host=host,
            local_key=local_key,
            protocol=protocol,
            on_state=self._handle_local_state,
            on_connection=self._handle_local_connection,
        )

    # ---- read API for entities ---------------------------------------

    @property
    def state(self) -> dict[int, Any]:
        return dict(self._state)

    @property
    def available(self) -> bool:
        return self._local_connected or self._cloud_alive

    @property
    def unique_id(self) -> str:
        return f"{DOMAIN}_{self.device_id}"

    @property
    def last_local_push_age_s(self) -> float | None:
        if self._last_local_push == 0.0:
            return None
        return time.monotonic() - self._last_local_push

    def get_dps(self, dp: int) -> Any:
        return self._state.get(dp)

    # ---- write API for entities --------------------------------------

    async def async_set_dps(self, dp: int, value: Any) -> bool:
        """Write a DPS via Tuya cloud. Always cloud — firmware drops local writes.

        Optimistic-first: flip local state and notify listeners *before*
        the cloud round-trip so the UI responds in <100 ms, then revert
        if the cloud write fails. This matches the HA switch/light/climate
        convention and avoids the 1–10 s Tuya-API latency leaking into
        the user-perceived response time.
        """
        previous = self._state.get(dp)
        had_value = dp in self._state
        _LOGGER.debug(
            "%s set_dps dp=%s value=%s previous=%s", self.name, dp, value, previous
        )
        self._state[dp] = value
        # Mark the DP as "recently written" so reconcile won't clobber
        # our optimistic value with stale cloud state. Drop the guard
        # when cloud catches up OR after 30 s (whichever is first).
        self._optimistic_guard[dp] = (time.monotonic() + 30.0, value)
        self._notify()
        t0 = time.monotonic()
        try:
            ok = await self._cloud.async_send_dps(
                self.device_id, self.profile, {dp: value}
            )
        except SharingCloudError as err:
            _LOGGER.warning(
                "%s cloud write %s=%s failed: %s", self.name, dp, value, err
            )
            ok = False
        _LOGGER.debug(
            "%s set_dps dp=%s value=%s -> ok=%s in %.0f ms",
            self.name, dp, value, ok, (time.monotonic() - t0) * 1000,
        )
        if not ok:
            self._optimistic_guard.pop(dp, None)
            if had_value:
                self._state[dp] = previous
            else:
                self._state.pop(dp, None)
            self._notify()
            return False
        return True

    # ---- merging from account reconcile loop -------------------------

    @callback
    def merge_cloud_state(self, state: dict[int, Any]) -> None:
        """Merge a cloud-side DPS snapshot into local state.

        Skips any DP currently under an optimistic write-guard, unless
        the cloud value matches what we wrote (in which case the guard
        is satisfied and dropped). This prevents reconcile from clobbering
        a fresh optimistic update before Tuya has propagated it.
        """
        if not state:
            return
        now = time.monotonic()
        # Drop expired guards
        self._optimistic_guard = {
            dp: (deadline, expected)
            for dp, (deadline, expected) in self._optimistic_guard.items()
            if deadline > now
        }
        changed = False
        for dp, cloud_value in state.items():
            guard = self._optimistic_guard.get(dp)
            if guard is not None:
                _deadline, expected = guard
                if cloud_value == expected:
                    # Cloud caught up to our write — guard satisfied.
                    self._optimistic_guard.pop(dp, None)
                    if self._state.get(dp) != cloud_value:
                        self._state[dp] = cloud_value
                        changed = True
                # else: cloud is still stale, keep our optimistic value.
                continue
            if self._state.get(dp) != cloud_value:
                self._state[dp] = cloud_value
                changed = True
        self._last_cloud_poll = time.monotonic()
        if not self._cloud_alive:
            self._cloud_alive = True
            changed = True
        if changed:
            self._notify()

    # ---- lifecycle ---------------------------------------------------

    def async_start(self) -> None:
        self.client.start()

    async def async_stop(self) -> None:
        await self.hass.async_add_executor_job(self.client.stop)

    # ---- listener wiring ---------------------------------------------

    @callback
    def async_add_listener(
        self, update_callback: Callable[[], None]
    ) -> Callable[[], None]:
        self._listeners.append(update_callback)

        @callback
        def remove_listener() -> None:
            if update_callback in self._listeners:
                self._listeners.remove(update_callback)

        return remove_listener

    @callback
    def _handle_local_state(self, state: dict[int, Any]) -> None:
        # local push wins on overlap because it's the freshest signal
        self._state.update(state)
        self._last_local_push = time.monotonic()
        self._notify()

    @callback
    def _handle_local_connection(self, connected: bool) -> None:
        if connected == self._local_connected:
            return
        self._local_connected = connected
        _LOGGER.debug("%s local push connected=%s", self.name, connected)
        self._notify()

    @callback
    def _notify(self) -> None:
        for listener in list(self._listeners):
            try:
                listener()
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Listener for %s raised", self.name)
