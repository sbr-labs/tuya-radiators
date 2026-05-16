"""Climate entity for a Tuya radiator."""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
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
    async_add_entities(
        [RadiatorClimate(c) for c in account.all_coordinators()]
    )


class RadiatorClimate(RadiatorEntity, ClimateEntity):
    """Heat/off climate with target+current temperature and presets."""

    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT]
    _attr_name = None  # use device name as entity friendly name
    _enable_turn_on_off_backwards_compatibility = False

    def __init__(self, coordinator: RadiatorCoordinator) -> None:
        super().__init__(coordinator)
        profile = coordinator.profile
        self._attr_min_temp = profile.min_temp_c
        self._attr_max_temp = profile.max_temp_c
        self._attr_target_temperature_step = profile.target_step_c

        features = (
            ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.TURN_ON
            | ClimateEntityFeature.TURN_OFF
        )
        if profile.preset and profile.preset_dps is not None:
            features |= ClimateEntityFeature.PRESET_MODE
            self._attr_preset_modes = profile.preset.presets()
        self._attr_supported_features = features

    @property
    def hvac_mode(self) -> HVACMode | None:
        raw = self._dps(self._coordinator.profile.power.dp)
        if raw is None:
            return None
        return HVACMode.HEAT if bool(raw) else HVACMode.OFF

    @property
    def hvac_action(self) -> HVACAction | None:
        if not self.available:
            return None
        if self.hvac_mode == HVACMode.OFF:
            return HVACAction.OFF
        target = self.target_temperature
        current = self.current_temperature
        if target is None or current is None:
            return HVACAction.IDLE
        if current + 0.1 < target:
            return HVACAction.HEATING
        return HVACAction.IDLE

    @property
    def current_temperature(self) -> float | None:
        return self._coordinator.profile.current_temp.from_raw(
            self._dps(self._coordinator.profile.current_temp.dp)
        )

    @property
    def target_temperature(self) -> float | None:
        return self._coordinator.profile.target_temp.from_raw(
            self._dps(self._coordinator.profile.target_temp.dp)
        )

    @property
    def preset_mode(self) -> str | None:
        profile = self._coordinator.profile
        if profile.preset is None or profile.preset_dps is None:
            return None
        return profile.preset.to_preset(self._dps(profile.preset_dps.dp))

    async def async_set_temperature(self, **kwargs: Any) -> None:
        target = kwargs.get(ATTR_TEMPERATURE)
        if target is None:
            return
        profile = self._coordinator.profile
        clamped = max(profile.min_temp_c, min(profile.max_temp_c, float(target)))
        await self._coordinator.async_set_dps(
            profile.target_temp.dp, profile.target_temp.to_raw(clamped)
        )

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        await self._coordinator.async_set_dps(
            self._coordinator.profile.power.dp, hvac_mode == HVACMode.HEAT
        )

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        profile = self._coordinator.profile
        if profile.preset is None or profile.preset_dps is None:
            return
        raw = profile.preset.to_raw(preset_mode)
        if raw is None:
            return
        await self._coordinator.async_set_dps(profile.preset_dps.dp, raw)

    async def async_turn_on(self) -> None:
        await self.async_set_hvac_mode(HVACMode.HEAT)

    async def async_turn_off(self) -> None:
        await self.async_set_hvac_mode(HVACMode.OFF)
