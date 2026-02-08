
import datetime
import json
import os

from custom_components.solar_mind.mind.generation_forecast import ForecastSolarApiGenerationForecast


def test_generation_forecast():
    """
    Test _handle_response converts cumulative forecast to per-hour absolute Wh timeseries.
    """
    response_path = os.path.join(os.path.dirname(__file__), "resources", "solar_forecast_response1.json")
    with open(response_path) as f:
        response = json.load(f)

    forecast = ForecastSolarApiGenerationForecast(latitude=49.1, longitude=16.1, azimuth=180, tilt=30)
    now = datetime.datetime(2026, 2, 8, 0, 0, 0)
    result = forecast._handle_response(response, now=now)

    # Build lookup from result
    values = {dt: val for dt, val in result.points}

    # Should span from 2026-02-08 00:00 through 2026-02-09 23:00 (48 hours)
    assert len(result.points) == 48

    # Expected per-hour deltas for 2026-02-08 (from cumulative diffs)
    expected_feb08 = {
        7: 250, 8: 1012, 9: 1587, 10: 1972, 11: 2153,
        12: 2115, 13: 1870, 14: 1446, 15: 883, 16: 364, 17: 6,
    }
    for hour in range(24):
        dt = datetime.datetime(2026, 2, 8, hour)
        expected = expected_feb08.get(hour, 0.0)
        assert values[dt] == expected, f"Feb 08 hour {hour}: expected {expected}, got {values[dt]}"

    # Expected per-hour deltas for 2026-02-09 (from cumulative diffs)
    expected_feb09 = {
        7: 270, 8: 1048, 9: 1634, 10: 2020, 11: 2200,
        12: 2161, 13: 1908, 14: 1475, 15: 905, 16: 426, 17: 13,
    }
    for hour in range(24):
        dt = datetime.datetime(2026, 2, 9, hour)
        expected = expected_feb09.get(hour, 0.0)
        assert values[dt] == expected, f"Feb 09 hour {hour}: expected {expected}, got {values[dt]}"
