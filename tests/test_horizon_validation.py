"""Horizon files must either produce a valid profile or a useful error."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from custom_components.open_meteo_solar_forecast.coordinator import checkHorizonFile


class HorizonValidationTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "horizon.txt"

    def check(self, text):
        self.path.write_text(text)
        return checkHorizonFile(str(self.path))

    def test_valid_profile_preserves_fractional_and_negative_elevations(self):
        profile, message = self.check(
            "# Azimuth\televation\n\n0\t-2.5\n180.25\t30.5 # obstruction\n360\t0\n"
        )
        self.assertEqual(profile, ((0.0, -2.5), (180.25, 30.5), (360.0, 0.0)))
        self.assertEqual(message, "")

    def test_invalid_shapes_and_numbers_return_errors(self):
        for text in (
            "", "# empty\n", "0\t0\n", "0\n360\n",
            "0\t0\n180\t10\t20\n360\t0\n",
            "0,0\n360,0\n", "0\ttext\n360\t0\n",
            "0\t0\n360\t\n", "0\tnan\n360\t0\n",
            "0\t0\ninf\t0\n", "0\t-inf\n360\t0\n",
        ):
            with self.subTest(text=text):
                profile, message = self.check(text)
                self.assertIsNone(profile)
                self.assertTrue(message.startswith("Invalid horizon file:"))

    def test_invalid_angles_and_order_return_errors(self):
        for text in (
            "0.5\t0\n360\t0\n", "0\t0\n360.5\t0\n",
            "-1\t0\n360\t0\n", "0\t0\n361\t0\n",
            "0\t0\n180\t0\n180\t10\n360\t0\n",
            "0\t0\n270\t0\n90\t0\n360\t0\n",
            "0\t120\n360\t0\n", "0\t-91\n360\t0\n",
        ):
            with self.subTest(text=text):
                profile, message = self.check(text)
                self.assertIsNone(profile)
                self.assertTrue(message.startswith("Invalid horizon file:"))

    def test_missing_file_and_directory_return_errors(self):
        for path in (self.path, self.path.parent):
            with self.subTest(path=path.name):
                profile, message = checkHorizonFile(str(path))
                self.assertIsNone(profile)
                self.assertTrue(message.startswith("Invalid horizon file:"))

    def test_permission_and_encoding_errors_are_handled(self):
        with patch("builtins.open", side_effect=PermissionError()):
            profile, message = checkHorizonFile(str(self.path))
        self.assertIsNone(profile)
        self.assertIn("read", message)
        self.path.write_bytes(b"\xff\xfe\x00\x00")
        profile, message = checkHorizonFile(str(self.path))
        self.assertIsNone(profile)
        self.assertTrue(message.startswith("Invalid horizon file:"))
