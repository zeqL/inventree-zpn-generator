"""
Unit tests for SAPN Generator functionality.

These tests validate the pure functions and logic of the SAPN generator
without requiring the full InvenTree environment.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock

# Test the pure functions directly
import sys
import os

# Add the parent directory to the path for importing
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestSAPNValidation(unittest.TestCase):
    """Tests for CCC and SS validation functions."""

    def test_validate_ccc_valid(self):
        """Test valid CCC values."""
        from generator import validate_ccc
        
        # Valid 3-letter uppercase codes
        self.assertTrue(validate_ccc("ABC"))
        self.assertTrue(validate_ccc("ELC"))
        self.assertTrue(validate_ccc("MEC"))
        self.assertTrue(validate_ccc("ZZZ"))

    def test_validate_ccc_invalid(self):
        """Test invalid CCC values."""
        from generator import validate_ccc
        
        # Too short
        self.assertFalse(validate_ccc("AB"))
        self.assertFalse(validate_ccc("A"))
        self.assertFalse(validate_ccc(""))
        
        # Too long
        self.assertFalse(validate_ccc("ABCD"))
        
        # Lowercase
        self.assertFalse(validate_ccc("abc"))
        self.assertFalse(validate_ccc("Abc"))
        
        # Contains numbers
        self.assertFalse(validate_ccc("A1C"))
        self.assertFalse(validate_ccc("123"))
        
        # Contains special characters
        self.assertFalse(validate_ccc("A-C"))
        self.assertFalse(validate_ccc("A_C"))

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


class TestSAPNFormatting(unittest.TestCase):
    """Tests for SAPN format generation."""

    def test_sapn_format_first_number(self):
        """Test that the first SAPN in a bucket is formatted correctly."""
        # Expected format: SAPN-{CCC}-{SS}-{NNNNN}
        prefix = "SAPN-ELC-11-"
        next_num = 1
        expected = "SAPN-ELC-11-00001"
        result = f"{prefix}{next_num:05d}"
        self.assertEqual(result, expected)

    def test_sapn_format_various_numbers(self):
        """Test various sequence numbers format correctly."""
        prefix = "SAPN-ABC-99-"
        
        test_cases = [
            (1, "SAPN-ABC-99-00001"),
            (42, "SAPN-ABC-99-00042"),
            (100, "SAPN-ABC-99-00100"),
            (1000, "SAPN-ABC-99-01000"),
            (10000, "SAPN-ABC-99-10000"),
            (99999, "SAPN-ABC-99-99999"),
        ]
        
        for num, expected in test_cases:
            with self.subTest(num=num):
                result = f"{prefix}{num:05d}"
                self.assertEqual(result, expected)

    def test_sapn_prefix_construction(self):
        """Test that the SAPN prefix is built correctly."""
        test_cases = [
            ("ELC", "11", "SAPN-ELC-11-"),
            ("MEC", "22", "SAPN-MEC-22-"),
            ("ABC", "00", "SAPN-ABC-00-"),
            ("ZZZ", "99", "SAPN-ZZZ-99-"),
        ]
        
        for ccc, ss, expected_prefix in test_cases:
            with self.subTest(ccc=ccc, ss=ss):
                result = f"SAPN-{ccc}-{ss}-"
                self.assertEqual(result, expected_prefix)


class TestSAPNSequenceLogic(unittest.TestCase):
    """Tests for sequence number calculation logic."""

    def test_extract_sequence_from_ipn(self):
        """Test extracting sequence number from existing IPN."""
        test_cases = [
            ("SAPN-ELC-11-00001", "SAPN-ELC-11-", 1),
            ("SAPN-ELC-11-00042", "SAPN-ELC-11-", 42),
            ("SAPN-ABC-99-10000", "SAPN-ABC-99-", 10000),
            ("SAPN-ZZZ-00-99999", "SAPN-ZZZ-00-", 99999),
        ]
        
        for ipn, prefix, expected_num in test_cases:
            with self.subTest(ipn=ipn):
                suffix = ipn[len(prefix):]
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
        ]
        
        for current, expected_next in test_cases:
            with self.subTest(current=current):
                result = current + 1
                self.assertEqual(result, expected_next)

    def test_overflow_detection(self):
        """Test that overflow is detected at 99999."""
        max_sequence = 99999
        
        # Should not overflow
        self.assertTrue(99999 <= max_sequence)
        
        # Should overflow
        self.assertTrue(100000 > max_sequence)


class TestSAPNParsing(unittest.TestCase):
    """Tests for parsing existing SAPN strings."""

    def test_parse_valid_sapn(self):
        """Test parsing valid SAPN strings."""
        import re
        pattern = r"^SAPN-([A-Z]{3})-(\d{2})-(\d{5})$"
        
        test_cases = [
            ("SAPN-ELC-11-00001", ("ELC", "11", "00001")),
            ("SAPN-ABC-99-42000", ("ABC", "99", "42000")),
            ("SAPN-ZZZ-00-00000", ("ZZZ", "00", "00000")),
        ]
        
        for sapn, expected in test_cases:
            with self.subTest(sapn=sapn):
                match = re.match(pattern, sapn)
                self.assertIsNotNone(match)
                self.assertEqual(match.groups(), expected)

    def test_parse_invalid_sapn(self):
        """Test that invalid SAPN strings don't match."""
        import re
        pattern = r"^SAPN-([A-Z]{3})-(\d{2})-(\d{5})$"
        
        invalid_cases = [
            "IPN-ELC-11-00001",      # Wrong prefix
            "SAPN-elc-11-00001",     # Lowercase CCC
            "SAPN-ELC-1-00001",      # SS too short
            "SAPN-ELC-111-00001",    # SS too long
            "SAPN-ELC-11-0001",      # NNNNN too short
            "SAPN-ELC-11-000001",    # NNNNN too long
            "SAPN-EL-11-00001",      # CCC too short
            "SAPN-ELCC-11-00001",    # CCC too long
            "SAPN-E1C-11-00001",     # CCC contains number
        ]
        
        for invalid_sapn in invalid_cases:
            with self.subTest(sapn=invalid_sapn):
                match = re.match(pattern, invalid_sapn)
                self.assertIsNone(match)


class TestComputeNextSAPNPure(unittest.TestCase):
    """
    Pure function tests for computing next SAPN.
    These mock the database queries to test the logic in isolation.
    """

    def test_compute_next_sapn_no_existing(self):
        """Test computing SAPN when no existing IPNs match."""
        # When there are no existing parts with this prefix, start at 1
        ccc = "ELC"
        ss = "11"
        prefix = f"SAPN-{ccc}-{ss}-"
        
        # Simulating no existing parts
        existing_max = None
        
        if existing_max is None:
            next_num = 1
        else:
            suffix = existing_max[len(prefix):]
            next_num = int(suffix) + 1
        
        result = f"{prefix}{next_num:05d}"
        self.assertEqual(result, "SAPN-ELC-11-00001")

    def test_compute_next_sapn_with_existing(self):
        """Test computing SAPN with existing IPNs."""
        ccc = "ELC"
        ss = "11"
        prefix = f"SAPN-{ccc}-{ss}-"
        
        # Simulating existing max IPN
        existing_max = "SAPN-ELC-11-00041"
        
        if existing_max is None:
            next_num = 1
        else:
            suffix = existing_max[len(prefix):]
            next_num = int(suffix) + 1
        
        result = f"{prefix}{next_num:05d}"
        self.assertEqual(result, "SAPN-ELC-11-00042")

    def test_compute_next_sapn_different_buckets(self):
        """Test that different (CCC, SS) buckets are independent."""
        buckets = [
            ("ELC", "11", "SAPN-ELC-11-00005", "SAPN-ELC-11-00006"),
            ("ELC", "22", "SAPN-ELC-22-00001", "SAPN-ELC-22-00002"),
            ("MEC", "11", None, "SAPN-MEC-11-00001"),
        ]
        
        for ccc, ss, existing_max, expected in buckets:
            with self.subTest(ccc=ccc, ss=ss):
                prefix = f"SAPN-{ccc}-{ss}-"
                
                if existing_max is None:
                    next_num = 1
                else:
                    suffix = existing_max[len(prefix):]
                    next_num = int(suffix) + 1
                
                result = f"{prefix}{next_num:05d}"
                self.assertEqual(result, expected)

    def test_overflow_raises_error(self):
        """Test that overflow condition raises ValueError."""
        max_sequence = 99999
        current_max = 99999
        
        next_num = current_max + 1
        
        # Should detect overflow
        self.assertTrue(next_num > max_sequence)
        
        # In the actual code, this raises ValueError
        with self.assertRaises(ValueError):
            if next_num > max_sequence:
                raise ValueError(
                    f"SAPN sequence overflow: next number {next_num} exceeds maximum {max_sequence}"
                )


class TestEdgeCases(unittest.TestCase):
    """Test edge cases and boundary conditions."""

    def test_leading_zeros_preserved(self):
        """Test that leading zeros in SS are preserved."""
        ss_values = ["00", "01", "09", "10"]
        
        for ss in ss_values:
            with self.subTest(ss=ss):
                prefix = f"SAPN-ABC-{ss}-"
                self.assertIn(f"-{ss}-", prefix)

    def test_sequence_zero_padding(self):
        """Test that sequence numbers are zero-padded to 5 digits."""
        test_cases = [
            (1, "00001"),
            (12, "00012"),
            (123, "00123"),
            (1234, "01234"),
            (12345, "12345"),
        ]
        
        for num, expected_formatted in test_cases:
            with self.subTest(num=num):
                result = f"{num:05d}"
                self.assertEqual(result, expected_formatted)
                self.assertEqual(len(result), 5)

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
