import datetime
from collections import defaultdict
from custom_components.solar_mind.mind.types import (
    Energy,
    Timeseries,
)
import requests

class ForecastSolarApiGenerationForecast:

    # forecast.solar URL: /:lat/:lon/:dec/:az/:kwp
    # dec = declination (tilt, 0-90), az = azimuth (-180..180, 0=South)
    URL = "https://api.forecast.solar/estimate/watthours/{latitude}/{longitude}/{declination}/{azimuth}/{max_peak_power_kw}"

    def __init__(self, latitude: float, longitude: float, azimuth: float, tilt: float, max_peak_power_kw: float = 10.0):
        self.latitude = latitude
        self.longitude = longitude
        self.azimuth = azimuth
        self.declination = tilt
        self.max_peak_power_kw = max_peak_power_kw

    def get_generation_forecast(self, now: datetime.datetime | None = None) -> Timeseries[Energy]:
        """
        Get the generation forecast for a given date.
        """
        response = self._send_request()
        return self._handle_response(response, now=now)

    def _handle_response(self, response: dict, now: datetime.datetime | None = None) -> Timeseries[Energy]:
        """
        Return timeseries of timestamps from now till the end of the next day with absolute generation values per hour in Wh.
        """
        if response.get("message", {}).get("type") != "success":
            raise ValueError(response)

        if now is None:
            now = datetime.datetime.now()

        result: dict[str, Energy] = response.get("result", {})

        # Parse timestamps and cumulative values, group by day
        days: dict[datetime.date, list[tuple[datetime.datetime, float]]] = defaultdict(list)
        for ts_str, cum_value in result.items():
            dt = datetime.datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
            days[dt.date()].append((dt, cum_value))

        # Compute per-hour deltas from cumulative values
        hourly: dict[datetime.datetime, float] = {}
        for day_entries in days.values():
            day_entries.sort(key=lambda x: x[0])
            for i in range(len(day_entries) - 1):
                dt_start, cum_start = day_entries[i]
                cum_end = day_entries[i + 1][1]
                delta = cum_end - cum_start
                # Floor start timestamp to the hour
                hour_key = dt_start.replace(minute=0, second=0, microsecond=0)
                hourly[hour_key] = hourly.get(hour_key, 0) + delta

        # Build timeseries from now (floored to hour) to end of next day (23:00)
        start_hour = now.replace(minute=0, second=0, microsecond=0)
        next_day = (now + datetime.timedelta(days=1)).date()
        end_hour = datetime.datetime.combine(next_day, datetime.time(23, 0))

        points: list[tuple[datetime.datetime, float]] = []
        current = start_hour
        while current <= end_hour:
            points.append((current, hourly.get(current, 0.0)))
            current += datetime.timedelta(hours=1)

        return Timeseries(points=points)

    def _send_request(self) -> dict:
        response = requests.get(self.URL.format(
            latitude=self.latitude,
            longitude=self.longitude,
            declination=self.declination,
            azimuth=self.azimuth,
            max_peak_power_kw=self.max_peak_power_kw,
        ))
        return response.json()