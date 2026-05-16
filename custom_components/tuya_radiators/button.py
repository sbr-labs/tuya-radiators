"""Per-radiator refresh button.

Pressing the button forces an immediate cloud reconcile for that one
radiator — useful when you've changed something in the Tuya app and
don't want to wait up to 30 s for the next reconcile tick, or after a
brief cloud outage to confirm everything is back in sync.
"""

from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .account import TuyaRadiatorAccount
from .const import DOMAIN
from .coordinator import RadiatorCoordinator
from .entity import RadiatorEntity
from .sharing_cloud import SharingCloudError

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    account: TuyaRadiatorAccount = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [RefreshButton(c) for c in account.all_coordinators()]
    )


class RefreshButton(RadiatorEntity, ButtonEntity):
    _attr_translation_key = "refresh"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:cloud-refresh"

    def __init__(self, coordinator: RadiatorCoordinator) -> None:
        super().__init__(coordinator, suffix="refresh")

    @property
    def available(self) -> bool:
        # Always pressable — point of the button is to recover from a
        # bad state, so it should still work when the entity itself is
        # showing unavailable.
        return True

    async def async_press(self) -> None:
        coord = self._coordinator
        try:
            state = await coord.cloud.async_get_status_by_dp(
                coord.device_id, coord.profile
            )
        except SharingCloudError as err:
            _LOGGER.warning(
                "%s refresh failed: %s", coord.name, err
            )
            return
        if state:
            coord.merge_cloud_state(state)
