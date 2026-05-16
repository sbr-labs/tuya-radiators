"""Child-lock switch."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
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
    entities: list[SwitchEntity] = []
    for c in account.all_coordinators():
        entities.append(PowerSwitch(c))
        entities.append(ChildLockSwitch(c))
    async_add_entities(entities)


class PowerSwitch(RadiatorEntity, SwitchEntity):
    _attr_translation_key = "power"

    def __init__(self, coordinator: RadiatorCoordinator) -> None:
        super().__init__(coordinator, suffix="power")

    @property
    def icon(self) -> str:
        return "mdi:radiator" if self.is_on else "mdi:radiator-off"

    @property
    def is_on(self) -> bool | None:
        raw = self._dps(self._coordinator.profile.power.dp)
        return None if raw is None else bool(raw)

    async def async_turn_on(self, **_: Any) -> None:
        await self._coordinator.async_set_dps(
            self._coordinator.profile.power.dp, True
        )

    async def async_turn_off(self, **_: Any) -> None:
        await self._coordinator.async_set_dps(
            self._coordinator.profile.power.dp, False
        )


class ChildLockSwitch(RadiatorEntity, SwitchEntity):
    _attr_translation_key = "child_lock"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:lock"

    def __init__(self, coordinator: RadiatorCoordinator) -> None:
        super().__init__(coordinator, suffix="child_lock")

    @property
    def is_on(self) -> bool | None:
        raw = self._dps(self._coordinator.profile.child_lock.dp)
        return None if raw is None else bool(raw)

    async def async_turn_on(self, **_: Any) -> None:
        await self._coordinator.async_set_dps(
            self._coordinator.profile.child_lock.dp, True
        )

    async def async_turn_off(self, **_: Any) -> None:
        await self._coordinator.async_set_dps(
            self._coordinator.profile.child_lock.dp, False
        )
