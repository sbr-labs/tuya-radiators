"""Sanity checks on the Ecostrad iQ Ceramic profile."""

from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1] / "custom_components"
sys.path.insert(0, str(ROOT))

from tuya_radiators.models import get_profile, list_profiles  # noqa: E402
from tuya_radiators.models.ecostrad_iqceramic import ECOSTRAD_IQCERAMIC  # noqa: E402


def test_profile_registered() -> None:
    keys = [p.key for p in list_profiles()]
    assert ECOSTRAD_IQCERAMIC.key in keys
    assert get_profile(ECOSTRAD_IQCERAMIC.key) is ECOSTRAD_IQCERAMIC


def test_temperature_scaling() -> None:
    p = ECOSTRAD_IQCERAMIC
    assert p.target_temp.from_raw(225) == 22.5
    assert p.target_temp.to_raw(22.5) == 225
    assert p.current_temp.from_raw(210) == 21.0


def test_calibration_round_trips() -> None:
    p = ECOSTRAD_IQCERAMIC
    assert p.calibration.from_raw(-3) == -3.0
    assert p.calibration.to_raw(-3) == -3


def test_preset_round_trips() -> None:
    p = ECOSTRAD_IQCERAMIC
    assert p.preset is not None
    assert p.preset.to_preset("hot") == "comfort"
    assert p.preset.to_raw("comfort") == "hot"
    assert "comfort" in p.preset.presets()
    # Front-panel "Radiator" mode = cloud "only_inside"
    assert p.preset.to_preset("only_inside") == "radiator"
    assert p.preset.to_raw("radiator") == "only_inside"


def test_surface_max_temp_field_present_and_scales_correctly() -> None:
    p = ECOSTRAD_IQCERAMIC
    assert p.surface_max_temp is not None
    assert p.surface_max_temp.dp == 57
    assert p.surface_max_temp.code == "cool_set_temp"
    # Cloud reports 600 → 60 °C
    assert p.surface_max_temp.from_raw(600) == 60.0
    assert p.surface_max_temp.to_raw(60) == 600
    # Bounds
    assert p.surface_min_temp_c == 30.0
    assert p.surface_max_temp_c == 70.0


def test_surface_max_temp_in_all_fields() -> None:
    p = ECOSTRAD_IQCERAMIC
    dps = [f.dp for f in p.all_fields()]
    assert 57 in dps  # surface_max_temp must be in the read path
    # Code-to-dp mapping works both directions
    assert p.dp_for_code("cool_set_temp") == 57
    assert p.code_for_dp(57) == "cool_set_temp"
