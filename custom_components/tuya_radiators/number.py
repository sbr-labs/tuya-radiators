"""Temperature calibration number entity."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
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
        [CalibrationNumber(c) for c in account.all_coordinators()]
    )


class CalibrationNumber(RadiatorEntity, NumberEntity):
    _attr_translation_key = "calibration"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX
    _attr_icon = "mdi:thermometer-plus"

    def __init__(self, coordinator: RadiatorCoordinator) -> None:
        super().__init__(coordinator, suffix="calibration")
        self._attr_native_min_value = coordinator.profile.calibration_min
        self._attr_native_max_value = coordinator.profile.calibration_max

    @property
    def native_value(self) -> float | None:
        return self._coordinator.profile.calibration.from_raw(
            self._dps(self._coordinator.profile.calibration.dp)
        )

    async def async_set_native_value(self, value: float) -> None:
        profile = self._coordinator.profile
        clamped = max(profile.calibration_min, min(profile.calibration_max, float(value)))
        await self._coordinator.async_set_dps(
            profile.calibration.dp, profile.calibration.to_raw(clamped)
        )
