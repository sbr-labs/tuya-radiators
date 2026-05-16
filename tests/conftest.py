"""Shared test fixtures.

These tests exercise pure logic (state merging, dp/code mapping, host
discovery) without booting Home Assistant. We stub the few `homeassistant.*`
imports our integration touches so importing the modules under test
doesn't fail in a vanilla Python env.

If you need richer fixtures later (full HA event loop, real ConfigEntry
lifecycle), switch to `pytest-homeassistant-custom-component`. For now
the lightweight shim is enough and keeps CI fast.
"""

from __future__ import annotations

import pathlib
import sys
import types
from unittest.mock import MagicMock

ROOT = pathlib.Path(__file__).resolve().parents[1] / "custom_components"
sys.path.insert(0, str(ROOT))


def _stub(name: str, **attrs):
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules[name] = mod
    return mod


# --- minimal homeassistant shims ---------------------------------------

if "homeassistant" not in sys.modules:
    _stub("homeassistant")
    _stub("homeassistant.config_entries", ConfigEntry=MagicMock, SOURCE_REAUTH="reauth",
          ConfigFlow=object, ConfigFlowResult=dict)

    def _callback(fn):
        return fn

    _stub("homeassistant.core", HomeAssistant=MagicMock, callback=_callback)
    _stub("homeassistant.const", ATTR_TEMPERATURE="temperature",
          Platform=types.SimpleNamespace(
              CLIMATE="climate", SWITCH="switch", NUMBER="number",
              SELECT="select", BINARY_SENSOR="binary_sensor",
          ),
          UnitOfTemperature=types.SimpleNamespace(CELSIUS="°C"))
    _stub("homeassistant.exceptions",
          ConfigEntryAuthFailed=type("ConfigEntryAuthFailed", (Exception,), {}),
          ConfigEntryNotReady=type("ConfigEntryNotReady", (Exception,), {}))
    _stub("homeassistant.helpers")
    _stub("homeassistant.helpers.issue_registry",
          async_create_issue=MagicMock(),
          async_delete_issue=MagicMock(),
          IssueSeverity=types.SimpleNamespace(ERROR="error", WARNING="warning"))
    _stub("homeassistant.helpers.entity",
          Entity=type("Entity", (), {}),
          EntityCategory=types.SimpleNamespace(CONFIG="config", DIAGNOSTIC="diagnostic"))
    _stub("homeassistant.helpers.entity_platform", AddEntitiesCallback=MagicMock)
    _stub("homeassistant.helpers.device_registry",
          DeviceInfo=lambda **kw: kw,
          async_get=MagicMock())
    _stub("homeassistant.helpers.selector",
          QrCodeSelector=MagicMock, QrCodeSelectorConfig=MagicMock,
          QrErrorCorrectionLevel=types.SimpleNamespace(QUARTILE="Q"),
          SelectSelector=MagicMock, SelectSelectorConfig=MagicMock,
          SelectSelectorMode=types.SimpleNamespace(LIST="list", DROPDOWN="dropdown"),
          TextSelector=MagicMock, TextSelectorConfig=MagicMock,
          TextSelectorType=types.SimpleNamespace(TEXT="text", PASSWORD="password"))
    _stub("homeassistant.components")
    _stub("homeassistant.components.switch", SwitchEntity=type("SwitchEntity", (), {}))
    _stub("homeassistant.components.number",
          NumberEntity=type("NumberEntity", (), {}),
          NumberMode=types.SimpleNamespace(BOX="box", SLIDER="slider"))
    _stub("homeassistant.components.select", SelectEntity=type("SelectEntity", (), {}))
    _stub("homeassistant.components.binary_sensor",
          BinarySensorEntity=type("BinarySensorEntity", (), {}),
          BinarySensorDeviceClass=types.SimpleNamespace(CONNECTIVITY="connectivity"))
    _stub("homeassistant.components.climate",
          ClimateEntity=type("ClimateEntity", (), {}),
          ClimateEntityFeature=types.SimpleNamespace(
              TARGET_TEMPERATURE=1, PRESET_MODE=2, TURN_ON=4, TURN_OFF=8),
          HVACMode=types.SimpleNamespace(OFF="off", HEAT="heat"),
          HVACAction=types.SimpleNamespace(OFF="off", HEATING="heating", IDLE="idle"))


# Stubs for third-party deps that our modules import at module-load
# time but that we don't exercise in pure-logic tests.
if "tinytuya" not in sys.modules:
    _stub("tinytuya", Device=MagicMock, OutletDevice=MagicMock,
          set_debug=lambda *a, **k: None)
if "voluptuous" not in sys.modules:
    vol = _stub("voluptuous")
    vol.Schema = lambda *a, **k: a[0] if a else {}
    vol.Required = lambda *a, **k: a[0] if a else None
    vol.Optional = lambda *a, **k: a[0] if a else None
if "tuya_sharing" not in sys.modules:
    _stub("tuya_sharing",
          Manager=MagicMock, CustomerDevice=MagicMock,
          SharingTokenListener=type("SharingTokenListener", (), {}),
          LoginControl=MagicMock)


# Now safe to import our package
from tuya_radiators.models import ECOSTRAD_IQCERAMIC  # noqa: E402,F401
