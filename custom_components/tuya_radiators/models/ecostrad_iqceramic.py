"""Ecostrad iQ Ceramic (and same-platform OEM) profile.

Verified DPS layout from a 7vmieyhabmukishx-class device on protocol 3.3.
"""

from __future__ import annotations

from .base import DpsField, ModelProfile, PresetMap

ECOSTRAD_IQCERAMIC = ModelProfile(
    key="ecostrad_iqceramic",
    display_name="Ecostrad iQ Ceramic Radiator",
    manufacturer="Ecostrad",
    protocol="3.3",
    min_temp_c=7.0,
    max_temp_c=30.0,
    target_step_c=0.5,
    power=DpsField(dp=1, code="switch"),
    target_temp=DpsField(dp=16, code="temp_set", scale=10.0),
    current_temp=DpsField(dp=24, code="temp_current", scale=10.0),
    calibration=DpsField(dp=27, code="temp_correction"),
    calibration_min=-5.0,
    calibration_max=5.0,
    child_lock=DpsField(dp=40, code="child_lock"),
    preset_dps=DpsField(dp=2, code="mode"),
    preset=PresetMap(
        # Front-panel names → HA preset names. The Ecostrad fifth preset
        # is "Radiator" mode (direct element heating up to 70 °C, no
        # room thermostat) — the cloud calls this `only_inside`.
        raw_to_preset={
            "auto": "program",
            "eco": "eco",
            "hot": "comfort",
            "cold": "away",
            "only_inside": "radiator",
        }
    ),
    window_detection_dps=DpsField(dp=108, code="Open_Window"),
    # Tuya cloud returns capitalised enum strings like "Off" / "Open_60min"
    # / "Open_90min" for the FLS-118C. We map both the cloud-canonical
    # form and a few common legacy forms; the *first* entry per HA option
    # value is the one we write back to the cloud, so list canonical first.
    window_detection_options={
        "Off": "off",
        "Open_60min": "60_min",
        "Open_90min": "90_min",
        "0": "off",
        "60": "60_min",
        "90": "90_min",
    },
    # DP 57 = `cool_set_temp` in Tuya's confusingly-named schema, but it
    # actually caps the radiator element/surface temperature when the
    # radiator is in "Radiator" mode (front-panel) / `only_inside` mode
    # (cloud). Range 30-70 °C in 1 °C steps. Default 60 °C from factory.
    surface_max_temp=DpsField(dp=57, code="cool_set_temp", scale=10.0),
    surface_min_temp_c=30.0,
    surface_max_temp_c=70.0,
)

# Tuya product_ids that map to this profile.
PRODUCT_IDS: tuple[str, ...] = ("7vmieyhabmukishx",)
