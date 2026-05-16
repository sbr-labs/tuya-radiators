"""Online/offline binary sensor.

Always-available so the user can see when a radiator can't be reached
(rather than the whole device just disappearing).
"""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .account import TuyaRadiatorAccount
from .const import DOMAIN
from .coordinator import RadiatorCoordinator
from .entity import RadiatorEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    account: TuyaRadiatorAccount = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [OnlineSensor(c) for c in account.all_coordinators()]
    )


class OnlineSensor(RadiatorEntity, BinarySensorEntity):
    _attr_translation_key = "online"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: RadiatorCoordinator) -> None:
        super().__init__(coordinator, suffix="online")

    @property
    def available(self) -> bool:
        return True

    @property
    def is_on(self) -> bool:
        return self._coordinator.available
