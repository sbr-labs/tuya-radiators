"""Per-radiator coordinator (borrowed-manager cloud writes).

State machine:

  * Cloud reconcile (every 30 s via TuyaRadiatorAccount) pulls fresh
    state from the borrowed Manager and calls merge_cloud_state().
  * Writes go via async_set_dps:
      - Idempotent — same value already set? No cloud round-trip.
      - Optimistic-first — local state + notify happen synchronously,
        cloud round-trip on a background task.
      - One retry with backoff if the first cloud write fails.
      - After FAILURE_THRESHOLD consecutive failures on the same DP,
        raise a HA repair issue so the user actually finds out.
  * Optimistic write-guard prevents reconcile from clobbering our value
    while Tuya cloud is still propagating it.
  * available returns False if reconcile hasn't succeeded recently —
    so the UI shows truth, not stale state from 10 minutes ago.

The local-LAN telemetry tap (TuyaRadiatorClient) is wired up but
currently unused for FLS-118C radiators (cloud reports public WAN IPs
that we can't reach from inside HAOS). Left in place because future
hardware profiles may benefit.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir

from .const import (
    DOMAIN,
    FAILURE_THRESHOLD,
    OPTIMISTIC_GUARD_S,
    RECONCILE_INTERVAL_S,
    STALE_RECONCILE_S,
    WRITE_RETRY_DELAY_S,
)
from .models import ModelProfile
from .sharing_cloud import SharingCloud, SharingCloudError
from .tuya_protocol import TuyaRadiatorClient

_LOGGER = logging.getLogger(__name__)


class RadiatorCoordinator:
    """Single radiator: cloud writes with optimistic-merge + retry + revert."""

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
        # just wrote and are waiting on Tuya cloud to propagate.
        self._optimistic_guard: dict[int, tuple[float, Any]] = {}
        # dp -> consecutive-failure count for the persistent-notification path
        self._consecutive_failures: dict[int, int] = {}
        self._failure_issue_active: set[int] = set()
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
    def cloud(self) -> SharingCloud:
        return self._cloud

    @property
    def state(self) -> dict[int, Any]:
        return dict(self._state)

    @property
    def available(self) -> bool:
        """True if local push is connected OR cloud reconcile has run recently.

        Goes False if cloud hasn't responded for > STALE_RECONCILE_S
        (default 90 s, i.e. 3 missed reconcile cycles). Showing stale
        state as if it were live is worse than showing unavailable —
        unavailable at least tells the user something is wrong.
        """
        if self._local_connected:
            return True
        if not self._cloud_alive:
            return False
        if self._last_cloud_poll == 0.0:
            return False
        return (time.monotonic() - self._last_cloud_poll) < STALE_RECONCILE_S

    @property
    def unique_id(self) -> str:
        return f"{DOMAIN}_{self.device_id}"

    @property
    def last_local_push_age_s(self) -> float | None:
        if self._last_local_push == 0.0:
            return None
        return time.monotonic() - self._last_local_push

    @property
    def last_cloud_poll_age_s(self) -> float | None:
        if self._last_cloud_poll == 0.0:
            return None
        return time.monotonic() - self._last_cloud_poll

    def get_dps(self, dp: int) -> Any:
        return self._state.get(dp)

    # ---- write API for entities --------------------------------------

    async def async_set_dps(self, dp: int, value: Any) -> bool:
        """Set a DPS via Tuya cloud (idempotent, optimistic, retried once).

        Returns immediately. UI flips before the cloud round-trip starts.
        The cloud write happens in a background task with one retry on
        failure. After FAILURE_THRESHOLD consecutive failures on this dp,
        a repair issue is raised so the user notices.
        """
        # Idempotent: same value already set with no in-flight guard? No-op.
        if self._state.get(dp) == value and dp not in self._optimistic_guard:
            _LOGGER.debug("%s set_dps dp=%s value=%s no-op", self.name, dp, value)
            return True

        previous = self._state.get(dp)
        had_value = dp in self._state
        self._state[dp] = value
        self._optimistic_guard[dp] = (time.monotonic() + OPTIMISTIC_GUARD_S, value)
        self._notify()
        self.hass.async_create_task(
            self._async_send_in_background(dp, value, previous, had_value),
            name=f"{DOMAIN}_send_{self.device_id[:8]}_{dp}",
        )
        return True

    async def _async_send_in_background(
        self, dp: int, value: Any, previous: Any, had_value: bool
    ) -> None:
        """Run the cloud write off the service-call critical path."""
        first_raised = False
        ok, raised = await self._try_send(dp, value)
        if raised:
            first_raised = True
        if not ok:
            # One retry after backoff (catches transient cloud blips).
            await asyncio.sleep(WRITE_RETRY_DELAY_S)
            ok, retry_raised = await self._try_send(dp, value)
            # If the FIRST attempt raised an explicit exception (real
            # Tuya rejection like error 2008), don't trust a None-returning
            # retry — that's the SDK's "no exception, no info" no-op
            # result, not a real success acknowledgement.
            if ok and first_raised and not retry_raised:
                ok = False
        if ok:
            self._consecutive_failures.pop(dp, None)
            self._clear_failure_issue(dp)
            return
        # Failed: revert + count + maybe alert.
        self._optimistic_guard.pop(dp, None)
        if had_value:
            self._state[dp] = previous
        else:
            self._state.pop(dp, None)
        self._notify()
        self._consecutive_failures[dp] = self._consecutive_failures.get(dp, 0) + 1
        if self._consecutive_failures[dp] >= FAILURE_THRESHOLD:
            self._raise_failure_issue(dp, value)

    async def _try_send(self, dp: int, value: Any) -> tuple[bool, bool]:
        """Return (ok, raised_exception)."""
        try:
            ok = await self._cloud.async_send_dps(
                self.device_id, self.profile, {dp: value}
            )
            return ok, False
        except SharingCloudError as err:
            _LOGGER.warning(
                "%s cloud write dp=%s value=%s failed: %s",
                self.name, dp, value, err,
            )
            return False, True

    def _raise_failure_issue(self, dp: int, value: Any) -> None:
        if dp in self._failure_issue_active:
            return
        self._failure_issue_active.add(dp)
        code = self.profile.code_for_dp(dp) or f"dp_{dp}"
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            f"write_fail_{self.device_id}_{dp}",
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="write_failures",
            translation_placeholders={
                "name": self.name,
                "field": code,
                "count": str(self._consecutive_failures.get(dp, 0)),
            },
        )

    def _clear_failure_issue(self, dp: int) -> None:
        if dp not in self._failure_issue_active:
            return
        self._failure_issue_active.discard(dp)
        ir.async_delete_issue(
            self.hass, DOMAIN, f"write_fail_{self.device_id}_{dp}"
        )

    # ---- merging from account reconcile loop -------------------------

    @callback
    def merge_cloud_state(self, state: dict[int, Any]) -> None:
        """Merge a cloud-side DPS snapshot into local state.

        Skips any DP currently under an optimistic write-guard, unless
        the cloud value matches what we wrote (in which case the guard
        is satisfied and dropped).
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
                    self._optimistic_guard.pop(dp, None)
                    if self._state.get(dp) != cloud_value:
                        self._state[dp] = cloud_value
                        changed = True
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


# Re-export for tests + callers that imported RECONCILE_INTERVAL_S from here.
__all__ = ["RadiatorCoordinator", "RECONCILE_INTERVAL_S"]
