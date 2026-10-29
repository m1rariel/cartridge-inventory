import os
import unittest
from unittest.mock import patch

from cartridge_app.adaptivity import bind_wraplength, configure_window, fit_dialog
from cartridge_app.visual import COLORS, GLASS, prefers_reduced_motion, transition_label


class FakeWindow:
    def __init__(self, width=1280, height=800, x=0, y=0):
        self.screen_width, self.screen_height = width, height
        self.x, self.y = x, y
        self.width, self.height = width, height
        self.bindings = {}
        self.geometry_value = None
        self.minimum = None
        self.state_value = None

    def winfo_screenwidth(self): return self.screen_width
    def winfo_screenheight(self): return self.screen_height
    def winfo_rootx(self): return self.x
    def winfo_rooty(self): return self.y
    def winfo_width(self): return self.width
    def winfo_height(self): return self.height
    def geometry(self, value): self.geometry_value = value
    def minsize(self, width, height): self.minimum = (width, height)
    def state(self, value): self.state_value = value
    def transient(self, parent): self.parent = parent

    def bind(self, sequence, callback, add=None):
        self.bindings[sequence] = callback
        return 'binding-1'


class FakeLabel:
    def __init__(self):
        self.values = {}

    def configure(self, **values): self.values.update(values)


class VisualAdaptivityTests(unittest.TestCase):
    def test_window_geometry_clamps_to_small_display(self):
        root = FakeWindow(400, 300)
        width, height = configure_window(root, initial=(1080, 720), minimum=(640, 480))
        self.assertLessEqual(width, root.screen_width)
        self.assertLessEqual(height, root.screen_height)
        self.assertLessEqual(root.minimum[0], width)
        self.assertLessEqual(root.minimum[1], height)

    def test_dialog_is_centered_and_fits_display(self):
        root = FakeWindow(800, 600, x=100, y=80)
        root.width, root.height = 700, 500
        dialog = FakeWindow()
        width, height = fit_dialog(dialog, root)
        self.assertEqual(dialog.geometry_value, f'{width}x{height}+155+135')
        self.assertEqual(dialog.parent, root)

    def test_wraplength_tracks_resizing_for_current_labels(self):
        root = FakeWindow(900, 700)
        first, second = FakeLabel(), FakeLabel()
        bind_wraplength(root, first, inset=64, minimum=240, maximum=820)
        bind_wraplength(root, second, inset=64, minimum=240, maximum=820)
        root.width = 520
        root.bindings['<Configure>'](type('Event', (), {'width': 520})())
        self.assertEqual(first.values['wraplength'], 456)
        self.assertEqual(second.values['wraplength'], 456)

    def test_glass_declares_readable_fallback_on_tk(self):
        self.assertFalse(GLASS['tk_backdrop_blur_supported'])
        self.assertFalse(GLASS['tk_alpha_supported'])
        self.assertEqual(len(COLORS['surface']), 7)

    def test_reduced_motion_setting_skips_transition(self):
        root, label = FakeWindow(), FakeLabel()
        with patch.dict(os.environ, {'CARTRIDGE_REDUCED_MOTION': '1'}):
            self.assertTrue(prefers_reduced_motion())
            transition_label(root, label, 'Склад', 'Title.TLabel')
        self.assertEqual(label.values, {'text': 'Склад', 'style': 'Title.TLabel'})
        self.assertEqual(root.bindings, {})


if __name__ == '__main__':
    unittest.main()
