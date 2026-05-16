"""Config flow for Tuya Radiators (borrowed-manager mode).

We don't sign in to Tuya ourselves — Tuya's sharing-flow auth is
unreliable when more than one HA integration is signed in to the same
account (we saw fresh tokens rejected with `sign invalid` on 2026-05-16).

Instead we piggy-back on an already-loaded Tuya integration on this
HAOS install (`tuya` or `xtend_tuya`) and use its Manager to talk to
the cloud. So the flow is single-step:

  user/devices — confirms a host integration is present, lists its
                 radiator-class devices, user ticks the ones they want.

No credentials, no QR, no fields beyond the device picker.
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers import selector

from .const import (
    CONF_DEVICE_ID,
    CONF_DEVICES,
    CONF_HOST,
    CONF_HOST_DOMAIN,
    CONF_HOST_ENTRY_ID,
    CONF_LOCAL_KEY,
    CONF_MODEL,
    CONF_NAME,
    CONF_PRODUCT_ID,
    CONF_PROTOCOL,
    DEFAULT_PROTOCOL,
    DOMAIN,
)
from .models import list_profiles, profile_for_product
from .sharing_cloud import list_radiator_devices

_LOGGER = logging.getLogger(__name__)


def _default_model_key() -> str:
    profiles = list_profiles()
    return profiles[0].key if profiles else ""


class RadiatorConfigFlow(ConfigFlow, domain=DOMAIN):
    """Pick which Tuya radiators to control via the borrowed host manager."""

    VERSION = 4  # bumped: user_code+QR (v3) -> borrowed-manager (v4)

    def __init__(self) -> None:
        self._candidates: list[dict[str, Any]] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        candidates = list_radiator_devices(self.hass)
        if not candidates:
            # Could be "host integration not loaded" OR "no radiator-class
            # devices on the host". The former is the more common cause
            # when this is a fresh install, so we surface that.
            return self.async_abort(reason="no_host_integration")
        self._candidates = candidates
        return await self.async_step_devices(user_input=None)

    async def async_step_devices(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if not self._candidates:
            self._candidates = list_radiator_devices(self.hass)
        if not self._candidates:
            return self.async_abort(reason="no_radiators_found")

        errors: dict[str, str] = {}
        if user_input is not None:
            selected = user_input.get("selected", [])
            if not selected:
                errors["base"] = "no_selection"
            else:
                chosen = [s for s in self._candidates if s["id"] in selected]
                host_domain = chosen[0]["host_domain"]
                host_entry_id = chosen[0]["host_entry_id"]
                # Unique-id is the host entry id — one tuya_radiators entry
                # per host integration is enough; users can reconfigure to
                # tick more devices.
                await self.async_set_unique_id(f"borrow:{host_entry_id}")
                self._abort_if_unique_id_configured()
                devices_payload = [
                    {
                        CONF_DEVICE_ID: s["id"],
                        CONF_NAME: s["name"],
                        CONF_HOST: s["ip"],
                        CONF_LOCAL_KEY: s["local_key"],
                        CONF_PRODUCT_ID: s["product_id"],
                        CONF_MODEL: (
                            profile_for_product(s["product_id"]).key
                            if profile_for_product(s["product_id"])
                            else _default_model_key()
                        ),
                        CONF_PROTOCOL: DEFAULT_PROTOCOL,
                    }
                    for s in chosen
                ]
                return self.async_create_entry(
                    title=f"Tuya Radiators ({len(devices_payload)})",
                    data={
                        CONF_HOST_DOMAIN: host_domain,
                        CONF_HOST_ENTRY_ID: host_entry_id,
                        CONF_DEVICES: devices_payload,
                    },
                )
        options = [
            {
                "value": spec["id"],
                "label": f"{spec['name']} - {spec['ip'] or 'no LAN ip'} ({spec['id'][:8]})",
            }
            for spec in self._candidates
        ]
        default = [opt["value"] for opt in options]
        schema = vol.Schema(
            {
                vol.Required("selected", default=default): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=options,
                        mode=selector.SelectSelectorMode.LIST,
                        multiple=True,
                    )
                ),
            }
        )
        return self.async_show_form(
            step_id="devices", data_schema=schema, errors=errors
        )
