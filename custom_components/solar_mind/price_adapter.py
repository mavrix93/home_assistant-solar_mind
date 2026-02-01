"""Price adapter to normalize different price data sources."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from homeassistant.core import HomeAssistant, State

from .const import PriceSource
from .models import HourlyPrice, PriceData

_LOGGER = logging.getLogger(__name__)


class PriceAdapter:
    """Adapter to normalize price data from different sources.
    
    Supports:
    - Czech OTE (cz_energy_spot_prices integration)
    - Nord Pool (nordpool integration)
    - Generic (manual configuration)
    """

    def __init__(self, hass: HomeAssistant, source: PriceSource) -> None:
        """Initialize the price adapter."""
        self.hass = hass
        self.source = source

    def parse_price_data(self, state: State) -> PriceData:
        """Parse price data from entity state based on source type.
        
        Args:
            state: The state object of the price sensor entity
            
        Returns:
            Normalized PriceData object
        """
        if self.source == PriceSource.CZECH_OTE:
            return self._parse_czech_ote(state)
        elif self.source == PriceSource.NORD_POOL:
            return self._parse_nord_pool(state)
        else:
            return self._parse_generic(state)

    def _parse_czech_ote(self, state: State) -> PriceData:
        """Parse Czech OTE (cz_energy_spot_prices) data.
        
        The Czech Energy Spot Prices integration provides:
        - State: current hour price
        - Attributes: dictionary with ISO timestamps as keys and prices as values
        """
        price_data = PriceData()
        
        # Current price from state
        try:
            price_data.current_price = float(state.state)
        except (ValueError, TypeError):
            _LOGGER.warning("Could not parse current price from state: %s", state.state)
            price_data.current_price = None
        
        # Get attributes - the Czech integration stores hourly prices as timestamp -> price dict
        attributes = state.attributes
        
        # Parse today's prices from attributes
        # The integration may store prices directly in attributes as timestamp keys
        today = datetime.now().date()
        tomorrow = today.replace(day=today.day + 1) if today.day < 28 else today  # Simplified
        
        for key, value in attributes.items():
            # Skip non-price attributes
            if key in ("unit_of_measurement", "device_class", "friendly_name", 
                       "icon", "state_class", "attribution"):
                continue
            
            try:
                # Try to parse as ISO timestamp
                if isinstance(key, str):
                    try:
                        dt = datetime.fromisoformat(key.replace("Z", "+00:00"))
                    except ValueError:
                        continue
                elif isinstance(key, datetime):
                    dt = key
                else:
                    continue
                
                price = float(value) if not isinstance(value, (list, tuple)) else float(value[0])
                hourly_price = HourlyPrice(start=dt, price=price)
                
                if dt.date() == today:
                    price_data.today.append(hourly_price)
                elif dt.date() > today:
                    price_data.tomorrow.append(hourly_price)
                    price_data.tomorrow_available = True
                    
            except (ValueError, TypeError, AttributeError) as e:
                _LOGGER.debug("Could not parse price entry %s: %s - %s", key, value, e)
                continue
        
        # Sort by time
        price_data.today.sort(key=lambda x: x.start)
        price_data.tomorrow.sort(key=lambda x: x.start)
        
        # If no prices were parsed from attributes, try raw_today format
        if not price_data.today:
            price_data = self._try_raw_format(state, price_data)
        
        return price_data

    def _parse_nord_pool(self, state: State) -> PriceData:
        """Parse Nord Pool data.
        
        The Nord Pool integration provides:
        - State: current hour price
        - Attributes: raw_today, raw_tomorrow (lists of {start, end, value})
        """
        price_data = PriceData()
        attributes = state.attributes
        
        # Current price from state
        try:
            price_data.current_price = float(state.state)
        except (ValueError, TypeError):
            _LOGGER.warning("Could not parse current price from state: %s", state.state)
        
        # Parse raw_today
        raw_today = attributes.get("raw_today", [])
        if isinstance(raw_today, list):
            for entry in raw_today:
                try:
                    start = entry.get("start")
                    value = entry.get("value")
                    
                    if isinstance(start, str):
                        start = datetime.fromisoformat(start.replace("Z", "+00:00"))
                    
                    if start and value is not None:
                        price_data.today.append(HourlyPrice(start=start, price=float(value)))
                except (ValueError, TypeError, AttributeError) as e:
                    _LOGGER.debug("Could not parse raw_today entry: %s - %s", entry, e)
        
        # Parse raw_tomorrow
        raw_tomorrow = attributes.get("raw_tomorrow", [])
        tomorrow_valid = attributes.get("tomorrow_valid", False)
        
        if isinstance(raw_tomorrow, list) and (tomorrow_valid or raw_tomorrow):
            for entry in raw_tomorrow:
                try:
                    start = entry.get("start")
                    value = entry.get("value")
                    
                    if isinstance(start, str):
                        start = datetime.fromisoformat(start.replace("Z", "+00:00"))
                    
                    if start and value is not None:
                        price_data.tomorrow.append(HourlyPrice(start=start, price=float(value)))
                        price_data.tomorrow_available = True
                except (ValueError, TypeError, AttributeError) as e:
                    _LOGGER.debug("Could not parse raw_tomorrow entry: %s - %s", entry, e)
        
        # Sort by time
        price_data.today.sort(key=lambda x: x.start)
        price_data.tomorrow.sort(key=lambda x: x.start)
        
        return price_data

    def _parse_generic(self, state: State) -> PriceData:
        """Parse generic price sensor data.
        
        Tries to detect the format automatically:
        1. First tries raw_today/raw_tomorrow format (Nord Pool style)
        2. Then tries timestamp -> price dict format (Czech OTE style)
        3. Falls back to just using current state as price
        """
        price_data = PriceData()
        attributes = state.attributes
        
        # Current price from state
        try:
            price_data.current_price = float(state.state)
        except (ValueError, TypeError):
            _LOGGER.warning("Could not parse current price from state: %s", state.state)
        
        # Try raw_today/raw_tomorrow format first
        if "raw_today" in attributes:
            return self._parse_nord_pool(state)
        
        # Try timestamp dict format
        price_data = self._try_raw_format(state, price_data)
        
        return price_data

    def _try_raw_format(self, state: State, price_data: PriceData) -> PriceData:
        """Try to parse prices from timestamp -> price dictionary format."""
        attributes = state.attributes
        today = datetime.now().date()
        
        for key, value in attributes.items():
            if key in ("unit_of_measurement", "device_class", "friendly_name", 
                       "icon", "state_class", "attribution", "raw_today", 
                       "raw_tomorrow", "tomorrow_valid"):
                continue
            
            try:
                # Try to parse key as datetime
                if isinstance(key, str):
                    try:
                        dt = datetime.fromisoformat(key.replace("Z", "+00:00"))
                    except ValueError:
                        continue
                elif isinstance(key, datetime):
                    dt = key
                else:
                    continue
                
                # Parse value
                if isinstance(value, (int, float)):
                    price = float(value)
                elif isinstance(value, (list, tuple)) and len(value) > 0:
                    price = float(value[0])
                else:
                    continue
                
                hourly_price = HourlyPrice(start=dt, price=price)
                
                if dt.date() == today:
                    price_data.today.append(hourly_price)
                elif dt.date() > today:
                    price_data.tomorrow.append(hourly_price)
                    price_data.tomorrow_available = True
                    
            except (ValueError, TypeError, AttributeError):
                continue
        
        # Sort by time
        price_data.today.sort(key=lambda x: x.start)
        price_data.tomorrow.sort(key=lambda x: x.start)
        
        return price_data


def create_price_adapter(hass: HomeAssistant, source: str | PriceSource) -> PriceAdapter:
    """Factory function to create a price adapter.
    
    Args:
        hass: Home Assistant instance
        source: Price source type (string or PriceSource enum)
        
    Returns:
        Configured PriceAdapter instance
    """
    if isinstance(source, str):
        source = PriceSource(source)
    return PriceAdapter(hass, source)
