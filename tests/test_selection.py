import unittest

from native.selection import Display, Phase, Point, Rect, Selection
from native.macos.mascot_anchor import MascotAnchor


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.selection = Selection()
        self.display = Display(1, Rect(-1920, -300, 1920, 1080), 2)
        self.selection.activate()

    def test_drag_in_all_four_directions(self):
        for end in (Point(-200, 500), Point(-400, 500), Point(-200, 300), Point(-400, 300)):
            self.selection.cancel()
            self.selection.activate()
            self.selection.begin(self.display, Point(-300, 400))
            self.assertTrue(self.selection.finish(end))
            self.assertEqual(self.selection.rect, Rect(min(-300, end.x), min(400, end.y), 100, 100))

    def test_drag_is_clamped_to_original_display(self):
        self.selection.begin(self.display, Point(-100, 0))
        self.selection.move(Point(900, 2000))
        self.assertEqual(self.selection.rect, Rect(-100, 0, 100, 780))
        self.assertEqual(self.selection.display.scale, 2)

    def test_tiny_selection_can_be_retried(self):
        self.selection.begin(self.display, Point(-100, 0))
        self.assertFalse(self.selection.finish(Point(-99, 1)))
        self.assertEqual(self.selection.phase, Phase.SELECTING)
        self.assertIsNone(self.selection.rect)
        self.assertTrue(self.selection.begin(self.display, Point(-100, 0)))
        self.assertTrue(self.selection.finish(Point(-80, 20)))

    def test_repeated_activation_does_not_erase_selection(self):
        self.selection.begin(self.display, Point(-100, 0))
        self.selection.finish(Point(-80, 20))
        self.assertFalse(self.selection.activate())
        self.assertFalse(self.selection.begin(self.display, Point(-50, 0)))
        self.selection.move(Point(0, 500))
        self.assertEqual(self.selection.rect, Rect(-100, 0, 20, 20))

    def test_cancel_at_every_phase_clears_all_geometry(self):
        for prepare in (lambda: None,
                        lambda: self.selection.begin(self.display, Point(-100, 0)),
                        lambda: (self.selection.begin(self.display, Point(-100, 0)), self.selection.finish(Point(-50, 50)))):
            self.selection.cancel()
            self.selection.activate()
            prepare()
            self.selection.cancel()
            self.selection.cancel()
            self.assertEqual(self.selection.phase, Phase.IDLE)
            self.assertIsNone(self.selection.rect)
            self.assertIsNone(self.selection.origin)
            self.assertIsNone(self.selection.display)
            self.selection.finish(Point(100, 100))
            self.assertEqual(self.selection.phase, Phase.IDLE)

    def test_anchor_only_tracks_lower_border_geometry(self):
        anchor = MascotAnchor()
        anchor.update(Rect(-200, 80, 100, 60))
        self.assertEqual(anchor.position, Point(-150, 80))
        anchor.update(None)
        self.assertIsNone(anchor.position)


if __name__ == '__main__':
    unittest.main()

