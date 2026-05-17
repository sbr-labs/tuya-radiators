"""Read-only sensors for radiator DPs that the cloud refuses to accept writes for.

Tuya's cloud /commands endpoint returns error code 2008 ("bad request /
invalid parameter") when we attempt to write certain DPs even though the
cloud reports the current value happily. The Ecostrad iQ Ceramic's
`cool_set_temp` (the radiator-mode surface-temperature cap, DP 57) is
one such — it's set on the device's physical control panel and is only
readable via cloud.

We surface it as a read-only sensor so users can monitor each radiator's
configured cap without HA trying — and failing — to write it.
"""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
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
    entities: list[SensorEntity] = []
    for c in account.all_coordinators():
        if c.profile.surface_max_temp is not None:
            entities.append(SurfaceMaxTempSensor(c))
    async_add_entities(entities)


class SurfaceMaxTempSensor(RadiatorEntity, SensorEntity):
    """Cloud-readable, cloud-unwritable cap on element temperature."""

    _attr_translation_key = "surface_max_temp"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_icon = "mdi:radiator"

    def __init__(self, coordinator: RadiatorCoordinator) -> None:
        super().__init__(coordinator, suffix="surface_max_temp")
        self._attr_suggested_object_id = "surface_max_temp"

    @property
    def native_value(self) -> float | None:
        assert self._coordinator.profile.surface_max_temp is not None
        return self._coordinator.profile.surface_max_temp.from_raw(
            self._dps(self._coordinator.profile.surface_max_temp.dp)
        )
