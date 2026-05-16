"""Open-window detection select."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
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
    entities = [
        WindowDetectionSelect(c)
        for c in account.all_coordinators()
        if c.profile.window_detection_dps is not None
    ]
    async_add_entities(entities)


class WindowDetectionSelect(RadiatorEntity, SelectEntity):
    _attr_translation_key = "window_detection"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:window-open-variant"

    def __init__(self, coordinator: RadiatorCoordinator) -> None:
        super().__init__(coordinator, suffix="window_detection")
        profile = coordinator.profile
        self._raw_to_option: dict[str, str] = dict(profile.window_detection_options)
        # The profile may list multiple raw values per HA option (cloud
        # canonical + legacy fallbacks). First-occurrence-wins on writes,
        # and we dedupe options for the HA picker.
        self._option_to_raw: dict[str, str] = {}
        for raw, opt in self._raw_to_option.items():
            self._option_to_raw.setdefault(opt, raw)
        self._attr_options = list(dict.fromkeys(self._raw_to_option.values()))

    @property
    def current_option(self) -> str | None:
        raw = self._dps(self._coordinator.profile.window_detection_dps.dp)
        if raw is None:
            return None
        return self._raw_to_option.get(str(raw))

    async def async_select_option(self, option: str) -> None:
        raw = self._option_to_raw.get(option)
        if raw is None:
            return
        await self._coordinator.async_set_dps(
            self._coordinator.profile.window_detection_dps.dp, raw
        )
