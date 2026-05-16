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
