"""Tests for Solar Mind price adapter."""
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from custom_components.solar_mind.ha.price_adapter import PriceAdapter


def _make_state(state: str, attributes: dict | None = None) -> MagicMock:
    """Create a mock State-like object."""
    s = MagicMock()
    s.state = state
    s.attributes = attributes or {}
    return s


def _make_hass_mock(time_zone: str = "Europe/Prague") -> MagicMock:
    """Create a mock Home Assistant instance with config."""
    hass = MagicMock()
    hass.config.time_zone = time_zone
    return hass


class TestPriceAdapter:
    """Test price adapter parsing."""

    def test_parse_current_price(self) -> None:
        """State value is current price."""
        hass = _make_hass_mock()
        adapter = PriceAdapter(hass)
        state = _make_state("1.25", {"unit_of_measurement": "CZK/kWh"})
        result = adapter.parse_price_data(state)
        assert result.current_price == 1.25

    def test_parse_invalid_state(self) -> None:
        """Invalid state value sets current_price to None."""
        hass = _make_hass_mock()
        adapter = PriceAdapter(hass)
        state = _make_state("unknown", {})
        result = adapter.parse_price_data(state)
        assert result.current_price is None

    def test_parse_hourly_prices_from_attributes(self) -> None:
        """Hourly prices are parsed from datetime-keyed attributes."""
        hass = _make_hass_mock()
        adapter = PriceAdapter(hass)
        
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        attrs = {
            today_start.isoformat(): 0.50,
            (today_start.replace(hour=1)).isoformat(): 0.45,
            (today_start.replace(hour=2)).isoformat(): 0.40,
            "unit_of_measurement": "CZK/kWh",
            "friendly_name": "Spot Price",
        }
        state = _make_state("0.50", attrs)
        result = adapter.parse_price_data(state)
        
        assert result.current_price == 0.50
        assert len(result.today) >= 1

    def test_parse_prices_with_sequence_values(self) -> None:
        """Price values in sequences are extracted correctly."""
        hass = _make_hass_mock()
        adapter = PriceAdapter(hass)
        
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        attrs = {
            today_start.isoformat(): [1.23, "additional_data"],
            "unit_of_measurement": "CZK/kWh",
        }
        state = _make_state("1.23", attrs)
        result = adapter.parse_price_data(state)
        
        assert result.current_price == 1.23
        assert len(result.today) >= 1
        if result.today:
            assert result.today[0].price == 1.23

    def test_today_prices_sorted(self) -> None:
        """Today's prices are sorted by time."""
        hass = _make_hass_mock()
        adapter = PriceAdapter(hass)
        
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        attrs = {
            (today_start.replace(hour=5)).isoformat(): 0.55,
            (today_start.replace(hour=2)).isoformat(): 0.40,
            (today_start.replace(hour=8)).isoformat(): 0.60,
        }
        state = _make_state("0.50", attrs)
        result = adapter.parse_price_data(state)
        
        for i in range(1, len(result.today)):
            assert result.today[i].start >= result.today[i - 1].start
