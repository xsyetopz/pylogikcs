"""Tests for pylogikcs - Logic Pro .logikcs read/write library.

Uses stdlib unittest (no external test dependencies).
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import plistlib

from pylogikcs import ColorMap, KeyBinding, ShortNameMap, load

FIXTURE = os.path.join(os.path.dirname(__file__), "..", "assets", "Default.logikcs")


# ---------------------------------------------------------------------------
# KeyBinding unit tests
# ---------------------------------------------------------------------------


class TestKeyBinding(unittest.TestCase):
    def test_from_bytes_valid(self):
        data = b"\x0b\x00\x00\x2c\xf7\x00"
        kb = KeyBinding.from_bytes(data)
        self.assertEqual(kb.command_index, 11)
        self.assertEqual(kb.value, 0x2C00)
        self.assertEqual(kb.key_code, 0x2C)
        self.assertEqual(kb.flags, 0x00)

    def test_from_bytes_bad_length(self):
        with self.assertRaisesRegex(ValueError, "must be 6 bytes"):
            KeyBinding.from_bytes(b"\xf7\x00")

    def test_from_bytes_bad_terminator(self):
        with self.assertRaisesRegex(ValueError, "terminator mismatch"):
            KeyBinding.from_bytes(b"\x0b\x00\x00\x2c\xab\xcd")

    def test_to_bytes_roundtrip(self):
        data = b"\x0b\x00\x00\x2c\xf7\x00"
        kb = KeyBinding.from_bytes(data)
        self.assertEqual(kb.to_bytes(), data)

    def test_key_code_setter(self):
        kb = KeyBinding(command_index=1, value=0)
        kb.key_code = 0x42
        self.assertEqual(kb.key_code, 0x42)
        self.assertEqual(kb.flags, 0)
        self.assertTrue(kb.is_modified)

    def test_key_code_setter_range_high(self):
        kb = KeyBinding(command_index=1, value=0)
        with self.assertRaises(ValueError):
            kb.key_code = 256

    def test_key_code_setter_range_low(self):
        kb = KeyBinding(command_index=1, value=0)
        with self.assertRaises(ValueError):
            kb.key_code = -1

    def test_flags_setter(self):
        kb = KeyBinding(command_index=1, value=0x0600)
        kb.flags = 0x08
        self.assertEqual(kb.flags, 0x08)
        self.assertEqual(kb.key_code, 0x06)

    def test_flags_setter_range(self):
        kb = KeyBinding(command_index=1, value=0)
        with self.assertRaises(ValueError):
            kb.flags = 256

    def test_mark_clean(self):
        kb = KeyBinding(command_index=1, value=0)
        kb.key_code = 0x42
        self.assertTrue(kb.is_modified)
        kb.mark_clean()
        self.assertFalse(kb.is_modified)


# ---------------------------------------------------------------------------
# ColorMap / ShortNameMap unit tests
# ---------------------------------------------------------------------------


class TestColorMap(unittest.TestCase):
    def test_set_get(self):
        cm = ColorMap()
        cm["100"] = 3
        self.assertEqual(cm["100"], 3)

    def test_invalid_value_type(self):
        cm = ColorMap()
        with self.assertRaises(TypeError):
            cm["100"] = "red"

    def test_key_coercion(self):
        cm = ColorMap()
        cm[100] = 5
        self.assertEqual(cm["100"], 5)


class TestShortNameMap(unittest.TestCase):
    def test_set_get(self):
        sm = ShortNameMap()
        sm["1012"] = "ReadOff"
        self.assertEqual(sm["1012"], "ReadOff")

    def test_invalid_value_type(self):
        sm = ShortNameMap()
        with self.assertRaises(TypeError):
            sm["1012"] = 42


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


class TestLoadDefault(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.preset = load(FIXTURE)

    def test_content_type(self):
        self.assertEqual(self.preset.content, "com.apple.logic.keycommand")

    def test_version(self):
        self.assertEqual(self.preset.version, "12.3.0")

    def test_colors_count(self):
        self.assertEqual(len(self.preset.colors), 61)

    def test_short_names_count(self):
        self.assertEqual(len(self.preset.short_names), 33)

    def test_bindings_count(self):
        self.assertEqual(len(self.preset.bindings), 201)

    def test_bindings_have_offsets(self):
        for kb in self.preset.bindings:
            self.assertGreaterEqual(kb._offset, 0)

    def test_bindings_not_modified_on_load(self):
        for kb in self.preset.bindings:
            self.assertFalse(kb.is_modified)


class TestRoundTrip(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.preset = load(FIXTURE)

    def test_no_modifications(self):
        with tempfile.NamedTemporaryFile(suffix=".logikcs", delete=False) as tf:
            tmp_path = tf.name

        try:
            self.preset.save(tmp_path)
            with open(FIXTURE, "rb") as f:
                orig = plistlib.load(f)
            with open(tmp_path, "rb") as f:
                rted = plistlib.load(f)

            self.assertEqual(orig["LogicBinaryPreferences"], rted["LogicBinaryPreferences"])
            self.assertEqual(orig["TouchBarAssignments"], rted["TouchBarAssignments"])
            self.assertEqual(orig.get("KeyCommandColors"), rted.get("KeyCommandColors"))
            self.assertEqual(orig.get("KeyCommandShortNames"), rted.get("KeyCommandShortNames"))
            self.assertEqual(orig.get("Version"), rted.get("Version"))
            self.assertEqual(orig.get("Content"), rted.get("Content"))
        finally:
            os.unlink(tmp_path)

    def test_reload_after_noop_save(self):
        with tempfile.NamedTemporaryFile(suffix=".logikcs", delete=False) as tf:
            tmp_path = tf.name

        try:
            self.preset.save(tmp_path)
            reloaded = load(tmp_path)
            self.assertEqual(len(reloaded.bindings), len(self.preset.bindings))
            self.assertEqual(len(reloaded.colors), len(self.preset.colors))
            self.assertEqual(len(reloaded.short_names), len(self.preset.short_names))
        finally:
            os.unlink(tmp_path)


class TestMutation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.preset = load(FIXTURE)

    def setUp(self):
        """Reset the fixture preset to clean state before each test."""
        self.preset = load(FIXTURE)

    def test_modify_binding_persists(self):
        with tempfile.NamedTemporaryFile(suffix=".logikcs", delete=False) as tf:
            tmp_path = tf.name

        try:
            orig_val_3 = self.preset.bindings[3].value
            orig_val_5 = self.preset.bindings[5].value

            self.preset.bindings[4].key_code = 0x06
            self.preset.bindings[4].flags = 0x08
            self.assertTrue(self.preset.bindings[4].is_modified)

            self.preset.save(tmp_path)
            reloaded = load(tmp_path)

            self.assertEqual(reloaded.bindings[4].key_code, 0x06)
            self.assertEqual(reloaded.bindings[4].flags, 0x08)
            # Adjacent bindings untouched
            self.assertEqual(reloaded.bindings[3].value, orig_val_3)
            self.assertEqual(reloaded.bindings[5].value, orig_val_5)
        finally:
            os.unlink(tmp_path)

    def test_modify_color_persists(self):
        with tempfile.NamedTemporaryFile(suffix=".logikcs", delete=False) as tf:
            tmp_path = tf.name

        try:
            self.preset.colors["1012"] = 7
            self.preset.save(tmp_path)

            reloaded = load(tmp_path)
            self.assertEqual(reloaded.colors["1012"], 7)
        finally:
            os.unlink(tmp_path)

    def test_modify_short_name_persists(self):
        with tempfile.NamedTemporaryFile(suffix=".logikcs", delete=False) as tf:
            tmp_path = tf.name

        try:
            self.preset.short_names["1012"] = "Rd/Off"
            self.preset.save(tmp_path)

            reloaded = load(tmp_path)
            self.assertEqual(reloaded.short_names["1012"], "Rd/Off")
        finally:
            os.unlink(tmp_path)

    def test_add_color_persists(self):
        with tempfile.NamedTemporaryFile(suffix=".logikcs", delete=False) as tf:
            tmp_path = tf.name

        try:
            self.preset.colors["9999"] = 3
            self.preset.save(tmp_path)

            reloaded = load(tmp_path)
            self.assertEqual(reloaded.colors["9999"], 3)
        finally:
            os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases(unittest.TestCase):
    def test_empty_file(self):
        with self.assertRaises(FileNotFoundError):
            load("/nonexistent/path.logikcs")

    def test_keybinding_repr(self):
        kb = KeyBinding(command_index=42, value=0x2C00)
        r = repr(kb)
        self.assertIn("42", r)
        self.assertIn("11264", r)  # value shown as decimal in repr


if __name__ == "__main__":
    unittest.main()
