"""Tests for the datetime utility functions."""

from datetime import datetime
from zoneinfo import ZoneInfo

from django.http import HttpRequest
from django.test import RequestFactory, TestCase
from django.utils import timezone

from the_flip.apps.core.datetime import apply_browser_timezone, parse_datetime_with_browser_timezone


class ApplyBrowserTimezoneTests(TestCase):
    """Tests for apply_browser_timezone function."""

    def setUp(self):
        self.factory = RequestFactory()

    def _make_request_with_timezone(self, tz_name: str) -> HttpRequest:
        """Create a POST request with browser_timezone field."""
        return self.factory.post("/", {"browser_timezone": tz_name})

    def test_none_datetime_returns_none(self):
        """None input returns None."""
        request = self._make_request_with_timezone("America/Los_Angeles")
        result = apply_browser_timezone(None, request)
        self.assertIsNone(result)

    def test_missing_browser_timezone_returns_original(self):
        """Missing browser_timezone returns original datetime unchanged."""
        request = self.factory.post("/", {})
        dt = timezone.now()
        result = apply_browser_timezone(dt, request)
        self.assertEqual(result, dt)

    def test_empty_browser_timezone_returns_original(self):
        """Empty browser_timezone returns original datetime unchanged."""
        request = self.factory.post("/", {"browser_timezone": ""})
        dt = timezone.now()
        result = apply_browser_timezone(dt, request)
        self.assertEqual(result, dt)

    def test_invalid_browser_timezone_returns_original(self):
        """Invalid timezone name returns original datetime unchanged."""
        request = self.factory.post("/", {"browser_timezone": "Invalid/Timezone"})
        dt = timezone.now()
        result = apply_browser_timezone(dt, request)
        self.assertEqual(result, dt)

    def test_utc_timezone(self):
        """UTC timezone preserves the time."""
        request = self._make_request_with_timezone("UTC")
        # Create a datetime that Django would parse as UTC
        dt = datetime(2024, 12, 31, 14, 30, tzinfo=ZoneInfo("UTC"))

        result = apply_browser_timezone(dt, request)

        # Should have same naive time but in UTC timezone
        self.assertEqual(result.hour, 14)
        self.assertEqual(result.minute, 30)
        self.assertEqual(result.tzinfo, ZoneInfo("UTC"))

    def test_us_pacific_timezone(self):
        """US Pacific timezone applies correctly.

        America/Los_Angeles is UTC-8 in winter (PST) and UTC-7 in summer (PDT).
        """
        request = self._make_request_with_timezone("America/Los_Angeles")
        # User entered 2:30 PM in their browser (Pacific time)
        # Django parsed it as 2:30 PM UTC (wrong)
        dt = datetime(2024, 12, 31, 14, 30, tzinfo=ZoneInfo("UTC"))

        result = apply_browser_timezone(dt, request)

        # Result should be 2:30 PM in Pacific time
        self.assertEqual(result.hour, 14)
        self.assertEqual(result.minute, 30)
        self.assertEqual(result.tzinfo, ZoneInfo("America/Los_Angeles"))

    def test_european_timezone(self):
        """European timezone applies correctly.

        Europe/Paris is UTC+1 in winter (CET) and UTC+2 in summer (CEST).
        """
        request = self._make_request_with_timezone("Europe/Paris")
        # User entered 2:30 PM in their browser (Paris time)
        dt = datetime(2024, 12, 31, 14, 30, tzinfo=ZoneInfo("UTC"))

        result = apply_browser_timezone(dt, request)

        # Result should be 2:30 PM in Paris time
        self.assertEqual(result.hour, 14)
        self.assertEqual(result.minute, 30)
        self.assertEqual(result.tzinfo, ZoneInfo("Europe/Paris"))

    def test_preserves_date_components(self):
        """All date components (year, month, day) are preserved."""
        request = self._make_request_with_timezone("America/New_York")
        dt = datetime(2024, 6, 15, 9, 45, tzinfo=ZoneInfo("UTC"))

        result = apply_browser_timezone(dt, request)

        self.assertEqual(result.year, 2024)
        self.assertEqual(result.month, 6)
        self.assertEqual(result.day, 15)
        self.assertEqual(result.hour, 9)
        self.assertEqual(result.minute, 45)

    def test_dst_aware_summer_date(self):
        """Timezone handles DST correctly for summer dates.

        When entering a June date in America/Los_Angeles, it should use PDT (UTC-7).
        """
        request = self._make_request_with_timezone("America/Los_Angeles")
        # June 6, 2025 at 6:06 AM - summer, so PDT applies
        dt = datetime(2025, 6, 6, 6, 6, tzinfo=ZoneInfo("UTC"))

        result = apply_browser_timezone(dt, request)

        self.assertEqual(result.hour, 6)
        self.assertEqual(result.minute, 6)
        # The timezone is DST-aware, so offset should be -7 hours in June
        self.assertEqual(result.tzinfo, ZoneInfo("America/Los_Angeles"))
        # Verify UTC conversion reflects PDT (UTC-7)
        utc_time = result.astimezone(ZoneInfo("UTC"))
        self.assertEqual(utc_time.hour, 13)  # 6 AM PDT = 1 PM UTC

    def test_dst_aware_winter_date(self):
        """Timezone handles DST correctly for winter dates.

        When entering a December date in America/Los_Angeles, it should use PST (UTC-8).
        """
        request = self._make_request_with_timezone("America/Los_Angeles")
        # December 31, 2024 at 2:30 PM - winter, so PST applies
        dt = datetime(2024, 12, 31, 14, 30, tzinfo=ZoneInfo("UTC"))

        result = apply_browser_timezone(dt, request)

        self.assertEqual(result.hour, 14)
        self.assertEqual(result.minute, 30)
        # The timezone is DST-aware, so offset should be -8 hours in December
        self.assertEqual(result.tzinfo, ZoneInfo("America/Los_Angeles"))
        # Verify UTC conversion reflects PST (UTC-8)
        utc_time = result.astimezone(ZoneInfo("UTC"))
        self.assertEqual(utc_time.hour, 22)  # 2:30 PM PST = 10:30 PM UTC


class ParseDatetimeWithBrowserTimezoneTests(TestCase):
    """Tests for parse_datetime_with_browser_timezone function."""

    def setUp(self):
        self.factory = RequestFactory()

    def _make_request_with_timezone(self, tz_name: str) -> HttpRequest:
        """Create a POST request with browser_timezone field."""
        return self.factory.post("/", {"browser_timezone": tz_name})

    def test_empty_value_returns_none(self):
        """Empty string returns None."""
        request = self._make_request_with_timezone("UTC")
        result = parse_datetime_with_browser_timezone("", request)
        self.assertIsNone(result)

    def test_none_value_returns_none(self):
        """None value returns None."""
        request = self._make_request_with_timezone("UTC")
        result = parse_datetime_with_browser_timezone(None, request)
        self.assertIsNone(result)

    def test_invalid_format_returns_none(self):
        """Invalid datetime format returns None."""
        request = self._make_request_with_timezone("UTC")
        result = parse_datetime_with_browser_timezone("not-a-date", request)
        self.assertIsNone(result)

    def test_parses_valid_datetime_local_format(self):
        """Parses standard datetime-local format (YYYY-MM-DDTHH:MM)."""
        request = self._make_request_with_timezone("UTC")
        result = parse_datetime_with_browser_timezone("2024-12-31T14:30", request)

        self.assertIsNotNone(result)
        self.assertEqual(result.year, 2024)
        self.assertEqual(result.month, 12)
        self.assertEqual(result.day, 31)
        self.assertEqual(result.hour, 14)
        self.assertEqual(result.minute, 30)

    def test_applies_browser_timezone(self):
        """Parses and applies browser timezone."""
        request = self._make_request_with_timezone("America/Los_Angeles")
        result = parse_datetime_with_browser_timezone("2024-12-31T14:30", request)

        self.assertIsNotNone(result)
        self.assertEqual(result.hour, 14)
        self.assertEqual(result.minute, 30)
        self.assertEqual(result.tzinfo, ZoneInfo("America/Los_Angeles"))

    def test_result_is_timezone_aware(self):
        """Result is always timezone-aware."""
        request = self._make_request_with_timezone("UTC")
        result = parse_datetime_with_browser_timezone("2024-12-31T14:30", request)

        self.assertIsNotNone(result)
        self.assertIsNotNone(result.tzinfo)

    def test_dst_transition_summer(self):
        """Parsing a summer date applies DST offset correctly."""
        request = self._make_request_with_timezone("America/Los_Angeles")
        # June 6 at 6:06 AM - during PDT (UTC-7)
        result = parse_datetime_with_browser_timezone("2025-06-06T06:06", request)

        self.assertIsNotNone(result)
        self.assertEqual(result.hour, 6)
        self.assertEqual(result.minute, 6)
        # Convert to UTC to verify DST was applied correctly
        utc_time = result.astimezone(ZoneInfo("UTC"))
        self.assertEqual(utc_time.hour, 13)  # 6:06 AM PDT = 1:06 PM UTC

    def test_dst_transition_winter(self):
        """Parsing a winter date applies standard time offset correctly."""
        request = self._make_request_with_timezone("America/Los_Angeles")
        # December 31 at 2:30 PM - during PST (UTC-8)
        result = parse_datetime_with_browser_timezone("2024-12-31T14:30", request)

        self.assertIsNotNone(result)
        self.assertEqual(result.hour, 14)
        self.assertEqual(result.minute, 30)
        # Convert to UTC to verify standard time was applied correctly
        utc_time = result.astimezone(ZoneInfo("UTC"))
        self.assertEqual(utc_time.hour, 22)  # 2:30 PM PST = 10:30 PM UTC
