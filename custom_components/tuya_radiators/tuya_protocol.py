"""LAN protocol client for one Tuya radiator.

Wraps tinytuya with a long-lived background thread that:
  * holds a persistent TCP socket
  * heartbeats every 9 s (Tuya devices drop idle sockets after ~10 s)
  * receives push DPS updates the moment the device sends them
  * auto-reconnects with exponential backoff on any failure

The thread never raises out of its run-loop; every failure path leads
to a clean reconnect attempt. Public API is async-safe: callers stay on
the HA event loop, the thread does the blocking I/O.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections.abc import Callable
from typing import Any

import tinytuya

from .const import (
    COMMAND_RETRY_LIMIT,
    HEARTBEAT_INTERVAL_S,
    INITIAL_RECONNECT_DELAY_S,
    MAX_RECONNECT_DELAY_S,
    RECONNECT_BACKOFF_FACTOR,
    SOCKET_READ_TIMEOUT_S,
)

_LOGGER = logging.getLogger(__name__)


class TuyaRadiatorClient:
    """One persistent connection to one radiator."""

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        device_id: str,
        host: str,
        local_key: str,
        protocol: str,
        on_state: Callable[[dict[int, Any]], None],
        on_connection: Callable[[bool], None],
    ) -> None:
        self._loop = loop
        self._device_id = device_id
        self._host = host
        self._local_key = local_key
        self._protocol = protocol
        self._on_state = on_state
        self._on_connection = on_connection

        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._device: tinytuya.OutletDevice | None = None
        self._device_lock = threading.Lock()
        self._connected = False
        self._state: dict[int, Any] = {}
        self._state_lock = threading.Lock()

    @property
    def state(self) -> dict[int, Any]:
        with self._state_lock:
            return dict(self._state)

    @property
    def connected(self) -> bool:
        return self._connected

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            name=f"tuya_radiator_{self._device_id[:8]}",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        with self._device_lock:
            if self._device is not None:
                try:
                    self._device.close()
                except Exception:  # noqa: BLE001
                    pass
                self._device = None
        thread = self._thread
        if thread is not None:
            thread.join(timeout=5.0)

    async def async_set_dps(self, dp: int, value: Any) -> bool:
        """Set a single DPS value. Returns True on success."""
        return await self._loop.run_in_executor(None, self._set_dps_blocking, dp, value)

    def _set_dps_blocking(self, dp: int, value: Any) -> bool:
        for attempt in range(COMMAND_RETRY_LIMIT + 1):
            with self._device_lock:
                device = self._device
            if device is None:
                _LOGGER.debug(
                    "set_dps %s=%s: not connected (attempt %d)", dp, value, attempt
                )
                time.sleep(0.5)
                continue
            try:
                response = device.set_value(dp, value, nowait=False)
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("set_dps %s=%s failed: %s", dp, value, err)
                self._mark_disconnected()
                time.sleep(0.5)
                continue
            if response is None:
                continue
            if isinstance(response, dict) and response.get("Error"):
                _LOGGER.warning("Device returned error setting %s=%s: %s", dp, value, response)
                return False
            self._merge_state(response)
            return True
        return False

    def _run(self) -> None:
        delay = INITIAL_RECONNECT_DELAY_S
        while not self._stop.is_set():
            try:
                if not self._open():
                    self._sleep_with_stop(delay)
                    delay = min(delay * RECONNECT_BACKOFF_FACTOR, MAX_RECONNECT_DELAY_S)
                    continue
                delay = INITIAL_RECONNECT_DELAY_S
                self._poll_loop()
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("run-loop exception (will reconnect): %s", err)
            finally:
                self._mark_disconnected()
            self._sleep_with_stop(delay)
            delay = min(delay * RECONNECT_BACKOFF_FACTOR, MAX_RECONNECT_DELAY_S)

    def _open(self) -> bool:
        try:
            device = tinytuya.OutletDevice(
                dev_id=self._device_id,
                address=self._host,
                local_key=self._local_key,
                version=float(self._protocol),
            )
            device.set_socketPersistent(True)
            device.set_socketTimeout(SOCKET_READ_TIMEOUT_S)
            device.set_socketRetryLimit(0)
            device.set_socketRetryDelay(1)
            initial = device.status()
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("connect failed for %s: %s", self._host, err)
            return False
        if not isinstance(initial, dict) or "dps" not in initial:
            _LOGGER.debug("connect to %s returned no dps payload: %s", self._host, initial)
            try:
                device.close()
            except Exception:  # noqa: BLE001
                pass
            return False
        with self._device_lock:
            self._device = device
        self._merge_state(initial)
        self._mark_connected()
        return True

    def _poll_loop(self) -> None:
        last_heartbeat = time.monotonic()
        while not self._stop.is_set():
            with self._device_lock:
                device = self._device
            if device is None:
                return
            now = time.monotonic()
            if now - last_heartbeat >= HEARTBEAT_INTERVAL_S:
                try:
                    device.heartbeat(nowait=True)
                except Exception as err:  # noqa: BLE001
                    _LOGGER.debug("heartbeat failed: %s", err)
                    return
                last_heartbeat = now
            try:
                event = device.receive()
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("receive failed: %s", err)
                return
            if event is None:
                continue
            if isinstance(event, dict):
                if event.get("Error"):
                    _LOGGER.debug("device pushed error frame: %s", event)
                    if event.get("Err") in ("905", "914"):
                        return
                    continue
                self._merge_state(event)

    def _merge_state(self, payload: dict[str, Any]) -> None:
        dps = payload.get("dps")
        if not isinstance(dps, dict):
            return
        normalised: dict[int, Any] = {}
        for key, value in dps.items():
            try:
                normalised[int(key)] = value
            except (TypeError, ValueError):
                continue
        if not normalised:
            return
        with self._state_lock:
            self._state.update(normalised)
            snapshot = dict(self._state)
        self._loop.call_soon_threadsafe(self._on_state, snapshot)

    def _mark_connected(self) -> None:
        if not self._connected:
            self._connected = True
            self._loop.call_soon_threadsafe(self._on_connection, True)

    def _mark_disconnected(self) -> None:
        with self._device_lock:
            if self._device is not None:
                try:
                    self._device.close()
                except Exception:  # noqa: BLE001
                    pass
                self._device = None
        if self._connected:
            self._connected = False
            self._loop.call_soon_threadsafe(self._on_connection, False)

    def _sleep_with_stop(self, seconds: float) -> None:
        end = time.monotonic() + seconds
        while not self._stop.is_set():
            remaining = end - time.monotonic()
            if remaining <= 0:
                return
            self._stop.wait(min(remaining, 1.0))
