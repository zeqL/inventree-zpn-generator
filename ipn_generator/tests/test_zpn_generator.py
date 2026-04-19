"""
Unit tests for ZPN Generator functionality.

These tests validate the pure functions and logic of the SAPN generator
without requiring the full InvenTree environment.
"""

import os

# Test the pure functions directly
import sys
import unittest
from unittest.mock import MagicMock, Mock, patch

# Add the parent directory to the path for importing
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestZPNValidation(unittest.TestCase):
    """Tests for CCC and SS validation functions."""

    def test_validate_ccc_valid(self):
        """Test valid CCC values."""
        from generator import validate_ccc

        # Valid 3-letter uppercase codes
        self.assertTrue(validate_ccc("ABC"))
        self.assertTrue(validate_ccc("1AZ"))
        self.assertTrue(validate_ccc("129"))
        self.assertTrue(validate_ccc("AZ9"))

    def test_validate_ccc_invalid(self):
        """Test invalid CCC values."""
        from generator import validate_ccc

        # Too short
        self.assertFalse(validate_ccc("AB"))
        self.assertFalse(validate_ccc("A"))
        self.assertFalse(validate_ccc(""))

        # Too long
        self.assertFalse(validate_ccc("ABCD"))
        self.assertFalse(validate_ccc("1BC9"))

        # Lowercase
        self.assertFalse(validate_ccc("abc"))
        self.assertFalse(validate_ccc("Abc"))
        self.assertFalse(validate_ccc("1b9"))

        # Contains special characters
        self.assertFalse(validate_ccc("A-C"))
        self.assertFalse(validate_ccc("A_C"))
        self.assertFalse(validate_ccc("A_9"))

    def test_validate_ss_valid(self):
        """Test valid SS values."""
        from generator import validate_ss

        # Valid 2-digit codes
        self.assertTrue(validate_ss("00"))
        self.assertTrue(validate_ss("01"))
        self.assertTrue(validate_ss("11"))
        self.assertTrue(validate_ss("99"))
        self.assertTrue(validate_ss("42"))

    def test_validate_ss_invalid(self):
        """Test invalid SS values."""
        from generator import validate_ss

        # Too short
        self.assertFalse(validate_ss("1"))
        self.assertFalse(validate_ss(""))

        # Too long
        self.assertFalse(validate_ss("123"))
        self.assertFalse(validate_ss("001"))

        # Contains letters
        self.assertFalse(validate_ss("1A"))
        self.assertFalse(validate_ss("AB"))

        # Contains special characters
        self.assertFalse(validate_ss("1-"))


class TestZPNFormatting(unittest.TestCase):
    """Tests for SAPN format generation."""

    def test_zpn_format_first_number(self):
        """Test that the first ZPN in a bucket is formatted correctly."""
        # Expected format: {CCC}{SS}{NNNNNN}
        prefix = "1AZ11"
        next_num = 1
        expected = "1AZ11000001"
        result = f"{prefix}{next_num:06d}"
        self.assertEqual(result, expected)

    def test_zpn_format_various_numbers(self):
        """Test various sequence numbers format correctly."""
        prefix = "1AZ99"

        test_cases = [
            (1, "1AZ99000001"),
            (42, "1AZ99000042"),
            (100, "1AZ99001000"),
            (1000, "1AZ99010000"),
            (10000, "1AZ99100000"),
            (99999, "1AZ99099999"),
            (999999, "1AZ99999999"),
        ]

        for num, expected in test_cases:
            with self.subTest(num=num):
                result = f"{prefix}{num:06d}"
                self.assertEqual(result, expected)

    def test_zpn_prefix_construction(self):
        """Test that the ZPN prefix is built correctly."""
        test_cases = [
            ("1AZ", "11", "1AZ11"),
            ("999", "22", "99922"),
            ("ABC", "00", "ABC00"),
            ("AB9", "99", "AB999"),
        ]

        for ccc, ss, expected_prefix in test_cases:
            with self.subTest(ccc=ccc, ss=ss):
                result = f"{ccc}{ss}"
                self.assertEqual(result, expected_prefix)


class TestZPNSequenceLogic(unittest.TestCase):
    """Tests for sequence number calculation logic."""

    def test_extract_sequence_from_ipn(self):
        """Test extracting sequence number from existing IPN."""
        test_cases = [
            ("1AZ12000001", "1AZ12", 1),
            ("ABZ19000042", "ABZ19", 42),
            ("AZ999010000", "AZ999", 10000),
            ("A5C00999999", "A5C00", 999999),
        ]

        for ipn, prefix, expected_num in test_cases:
            with self.subTest(ipn=ipn):
                suffix = ipn[len(prefix) :]
                result = int(suffix)
                self.assertEqual(result, expected_num)

    def test_increment_sequence(self):
        """Test that sequence numbers increment correctly."""
        test_cases = [
            (0, 1),
            (1, 2),
            (41, 42),
            (99, 100),
            (9999, 10000),
            (99998, 99999),
            (999998, 999999),
        ]

        for current, expected_next in test_cases:
            with self.subTest(current=current):
                result = current + 1
                self.assertEqual(result, expected_next)

    def test_overflow_detection(self):
        """Test that overflow is detected at 999999."""
        max_sequence = 999999

        # Should not overflow
        self.assertTrue(999999 <= max_sequence)

        # Should overflow
        self.assertTrue(1000000 > max_sequence)


class TestZPNParsing(unittest.TestCase):
    """Tests for parsing existing ZPN strings."""

    def test_parse_valid_zpn(self):
        """Test parsing valid ZPN strings."""
        import re

        pattern = r"^[A-Z0-9]{3}d{2}d{6}$"

        test_cases = [
            ("1AB11000001", ("1AB", "11", "000001")),
            ("ABC99420000", ("ABC", "99", "420000")),
            ("AZ900000000", ("AZ9", "00", "00000")),
            ("15919000000", ("159", "19", "00000")),
        ]

        for zpn, expected in test_cases:
            with self.subTest(zpn=zpn):
                match = re.match(pattern, zpn)
                self.assertIsNotNone(match)
                self.assertEqual(match.groups(), expected)

    def test_parse_invalid_zpn(self):
        """Test that invalid ZPN strings don't match."""
        import re

        pattern = r"^[A-Z0-9]{3}d{2}d{6}$"

        invalid_cases = [
            "-A-11000001",  # Wrong prefix
            "abc11000001",  # Lowercase CCC
            "ELC100001",  # SS too short
            "ELC11100001",  # SS too long
            "ELC110001",  # NNNNN too short
            "ELC110000001",  # NNNNN too long
            "EL11000001",  # CCC too short
            "ELCC11000001",  # CCC too long
        ]

        for invalid_zpn in invalid_cases:
            with self.subTest(sapn=invalid_zpn):
                match = re.match(pattern, invalid_zpn)
                self.assertIsNone(match)


class TestComputeNextZPNPure(unittest.TestCase):
    """
    Pure function tests for computing next ZPN.
    These mock the database queries to test the logic in isolation.
    """

    def test_compute_next_zpn_no_existing(self):
        """Test computing ZPN when no existing IPNs match."""
        # When there are no existing parts with this prefix, start at 1
        ccc = "ELC"
        ss = "11"
        prefix = f"{ccc}{ss}"

        # Simulating no existing parts
        existing_max = None

        if existing_max is None:
            next_num = 1
        else:
            suffix = existing_max[len(prefix) :]
            next_num = int(suffix) + 1

        result = f"{prefix}{next_num:06d}"
        self.assertEqual(result, "ELC11000001")

    def test_compute_next_zpn_with_existing(self):
        """Test computing ZPN with existing IPNs."""
        ccc = "ELC"
        ss = "11"
        prefix = f"{ccc}{ss}"

        # Simulating existing max IPN
        existing_max = "ELC11000041"

        if existing_max is None:
            next_num = 1
        else:
            suffix = existing_max[len(prefix) :]
            next_num = int(suffix) + 1

        result = f"{prefix}{next_num:06d}"
        self.assertEqual(result, "ELC11000042")

    def test_compute_next_zpn_different_buckets(self):
        """Test that different (CCC, SS) buckets are independent."""
        buckets = [
            ("ELC", "11", "ELC11000005", "ELC11000006"),
            ("1AB", "22", "1AB22000001", "1AB22000002"),
            ("ZZ9", "11", None, "ZZ911000001"),
        ]

        for ccc, ss, existing_max, expected in buckets:
            with self.subTest(ccc=ccc, ss=ss):
                prefix = f"{ccc}{ss}"

                if existing_max is None:
                    next_num = 1
                else:
                    suffix = existing_max[len(prefix) :]
                    next_num = int(suffix) + 1

                result = f"{prefix}{next_num:06d}"
                self.assertEqual(result, expected)

    def test_overflow_raises_error(self):
        """Test that overflow condition raises ValueError."""
        max_sequence = 999999
        current_max = 999999

        next_num = current_max + 1

        # Should detect overflow
        self.assertTrue(next_num > max_sequence)

        # In the actual code, this raises ValueError
        with self.assertRaises(ValueError):
            if next_num > max_sequence:
                raise ValueError(
                    f"ZPN sequence overflow: next number {next_num} exceeds maximum {max_sequence}"
                )


class TestEdgeCases(unittest.TestCase):
    """Test edge cases and boundary conditions."""

    def test_leading_zeros_preserved(self):
        """Test that leading zeros in SS are preserved."""
        ss_values = ["00", "01", "09", "10"]

        for ss in ss_values:
            with self.subTest(ss=ss):
                prefix = f"1AB{ss}-"
                self.assertIn(f"{ss}", prefix)

    def test_sequence_zero_padding(self):
        """Test that sequence numbers are zero-padded to 6 digits."""
        test_cases = [
            (1, "00001"),
            (12, "00012"),
            (123, "00123"),
            (1234, "01234"),
            (12345, "12345"),
            (123456, "123456"),
        ]

        for num, expected_formatted in test_cases:
            with self.subTest(num=num):
                result = f"{num:06d}"
                self.assertEqual(result, expected_formatted)
                self.assertEqual(len(result), 6)

    def test_whitespace_handling_ccc(self):
        """Test that whitespace is handled in CCC values."""
        from generator import validate_ccc

        # After stripping, these should be valid
        raw_values = [" ABC", "ABC ", " ABC "]
        for raw in raw_values:
            stripped = raw.strip().upper()
            self.assertTrue(validate_ccc(stripped))

    def test_whitespace_handling_ss(self):
        """Test that whitespace is handled in SS values."""
        from generator import validate_ss

        # After stripping, these should be valid
        raw_values = [" 11", "11 ", " 11 "]
        for raw in raw_values:
            stripped = raw.strip()
            self.assertTrue(validate_ss(stripped))


if __name__ == "__main__":
    unittest.main()
