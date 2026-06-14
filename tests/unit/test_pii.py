from __future__ import annotations

import pytest

from config.settings import PiiConfig
from security.pii import PiiScrubber


def make_scrubber(enabled: bool = True, patterns=None, replacement: str = "[REDACTED]") -> PiiScrubber:
    return PiiScrubber(PiiConfig(
        enabled=enabled,
        patterns=patterns or ["email", "phone", "ssn", "credit_card", "ip_address"],
        replacement=replacement,
    ))


class TestPiiScrubber:
    def test_disabled_is_noop(self):
        scrubber = make_scrubber(enabled=False)
        text = "Contact me at user@example.com"
        assert scrubber.scrub(text) == text

    def test_scrubs_email(self):
        scrubber = make_scrubber(patterns=["email"])
        assert scrubber.scrub("Email me at user@example.com please") == "Email me at [REDACTED] please"

    def test_scrubs_ssn(self):
        scrubber = make_scrubber(patterns=["ssn"])
        assert scrubber.scrub("My SSN is 123-45-6789.") == "My SSN is [REDACTED]."

    def test_scrubs_us_phone(self):
        scrubber = make_scrubber(patterns=["phone"])
        result = scrubber.scrub("Call me at 555-867-5309")
        assert "[REDACTED]" in result

    def test_scrubs_ip_address(self):
        scrubber = make_scrubber(patterns=["ip_address"])
        assert scrubber.scrub("Server IP: 192.168.1.1") == "Server IP: [REDACTED]"

    def test_custom_replacement_token(self):
        scrubber = make_scrubber(patterns=["email"], replacement="***")
        assert scrubber.scrub("hi user@test.com") == "hi ***"

    def test_multiple_patterns_in_one_string(self):
        scrubber = make_scrubber(patterns=["email", "ssn"])
        text = "Email user@example.com, SSN 123-45-6789"
        result = scrubber.scrub(text)
        assert "user@example.com" not in result
        assert "123-45-6789" not in result
        assert result.count("[REDACTED]") == 2

    def test_no_match_returns_unchanged(self):
        scrubber = make_scrubber(patterns=["email"])
        text = "No PII here at all."
        assert scrubber.scrub(text) == text

    def test_empty_string(self):
        scrubber = make_scrubber()
        assert scrubber.scrub("") == ""

    def test_only_active_patterns_applied(self):
        scrubber = make_scrubber(patterns=["ssn"])  # email not in list
        text = "Email user@test.com SSN 123-45-6789"
        result = scrubber.scrub(text)
        assert "user@test.com" in result  # email left alone
        assert "123-45-6789" not in result
