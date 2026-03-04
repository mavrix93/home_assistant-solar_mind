"""Price adapter to normalize different price data sources."""

import logging
import zoneinfo
from datetime import datetime, timezone
from typing import Any

from homeassistant.core import HomeAssistant, State

from custom_components.solar_mind.mind.models import HourlyPrice, PriceData

_LOGGER = logging.getLogger(__name__)

_SKIP_KEYS = frozenset((
    "unit_of_measurement", "device_class", "friendly_name",
    "icon", "state_class", "attribution",
    "raw_today", "raw_tomorrow", "tomorrow_valid",
))


class PriceAdapter:


    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass

    def _local_date_today(self) -> datetime:
        """Return today's date in the HA-configured timezone."""
        local_tz = zoneinfo.ZoneInfo(self.hass.config.time_zone)
        return datetime.now(timezone.utc).astimezone(local_tz).date()

    @staticmethod
    def _parse_timestamp(key: str | datetime) -> datetime | None:
        """Parse an attribute key into a timezone-aware datetime, or None."""
        if isinstance(key, datetime):
            return key
        if isinstance(key, str):
            try:
                return datetime.fromisoformat(key.replace("Z", "+00:00"))
            except ValueError:
                return None
        return None

    @staticmethod
    def _parse_price_value(value: Any) -> float | None:
        """Extract a numeric price from a scalar or sequence."""
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, (list, tuple)) and len(value) > 0:
            try:
                return float(value[0])
            except (ValueError, TypeError):
                return None
        return None

    def _classify_price(
        self,
        dt: datetime,
        price: float,
        today_local: datetime,
        local_tz: zoneinfo.ZoneInfo,
        price_data: PriceData,
    ) -> None:
        """Append an HourlyPrice to the correct day bucket in price_data."""
        # Convert the timestamp to the local timezone before comparing dates
        local_dt = dt.astimezone(local_tz) if dt.tzinfo else dt
        hourly_price = HourlyPrice(start=dt, price=price)

        if local_dt.date() == today_local:
            price_data.today.append(hourly_price)
        elif local_dt.date() > today_local:
            price_data.tomorrow.append(hourly_price)
            price_data.tomorrow_available = True

    def parse_price_data(self, state: State) -> PriceData:

        price_data = PriceData()

        # Current price from state
        try:
            price_data.current_price = float(state.state)
        except (ValueError, TypeError):
            _LOGGER.warning("Could not parse current price from state: %s", state.state)
            price_data.current_price = None

        local_tz = zoneinfo.ZoneInfo(self.hass.config.time_zone)
        today_local = self._local_date_today()

        # Parse hourly prices from attributes (timestamp -> price)
        for key, value in state.attributes.items():
            if key in _SKIP_KEYS:
                continue

            dt = self._parse_timestamp(key)
            if dt is None:
                continue

            price = self._parse_price_value(value)
            if price is None:
                _LOGGER.debug("Could not parse price entry %s: %s", key, value)
                continue

            self._classify_price(dt, price, today_local, local_tz, price_data)

        # Sort by time
        price_data.today.sort(key=lambda x: x.start)
        price_data.tomorrow.sort(key=lambda x: x.start)

        return price_data
