# tests/test_providers.py: Unit tests for providers module

import sys
import unittest
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.providers import _normalize_mime_type


class TestNormalizeMimeType(unittest.TestCase):
    """Tests for _normalize_mime_type function."""

    def test_video_quicktime_maps_to_mov(self):
        """video/quicktime should map to video/mov."""
        result = _normalize_mime_type("video/quicktime")
        self.assertEqual(result, "video/mov")

    def test_video_x_quicktime_maps_to_mov(self):
        """video/x-quicktime should map to video/mov."""
        result = _normalize_mime_type("video/x-quicktime")
        self.assertEqual(result, "video/mov")

    def test_case_insensitive_mapping(self):
        """Mapping should be case-insensitive."""
        result = _normalize_mime_type("VIDEO/QUICKTIME")
        self.assertEqual(result, "video/mov")
        
        result = _normalize_mime_type("Video/QuickTime")
        self.assertEqual(result, "video/mov")

    def test_supported_mime_types_pass_through(self):
        """Already supported MIME types should pass through unchanged."""
        supported_types = [
            "image/png",
            "image/jpeg",
            "image/gif",
            "image/webp",
            "application/pdf",
            "audio/mpeg",
            "audio/wav",
            "audio/ogg",
            "video/mp4",
            "video/mpeg",
            "video/mov",
            "video/webm",
            "text/plain",
        ]
        
        for mime_type in supported_types:
            result = _normalize_mime_type(mime_type)
            self.assertEqual(result, mime_type, f"{mime_type} should pass through unchanged")

    def test_unknown_mime_types_pass_through(self):
        """Unknown MIME types should pass through unchanged."""
        unknown_types = [
            "application/octet-stream",
            "application/zip",
            "application/x-custom",
            "video/x-custom",
            "image/x-custom",
        ]
        
        for mime_type in unknown_types:
            result = _normalize_mime_type(mime_type)
            self.assertEqual(result, mime_type, f"{mime_type} should pass through unchanged")

    def test_empty_string_passes_through(self):
        """Empty string should pass through unchanged."""
        result = _normalize_mime_type("")
        self.assertEqual(result, "")


if __name__ == "__main__":
    unittest.main()