"""Shared entity base."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .coordinator import RadiatorCoordinator


class RadiatorEntity(Entity):
    """Common bits for every entity bound to a single radiator."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self, coordinator: RadiatorCoordinator, suffix: str | None = None
    ) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = (
            f"{coordinator.unique_id}_{suffix}" if suffix else coordinator.unique_id
        )
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.device_id)},
            name=coordinator.name,
            manufacturer=coordinator.profile.manufacturer,
            model=coordinator.profile.display_name,
            configuration_url=f"http://{coordinator.host}",
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            self._coordinator.async_add_listener(self._handle_update)
        )

    def _handle_update(self) -> None:
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        return self._coordinator.available

    def _dps(self, dp: int) -> Any:
        return self._coordinator.get_dps(dp)
