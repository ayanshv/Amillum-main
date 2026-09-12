import unittest
from io import BytesIO
from PIL import Image
from core.mascot import ROWS, SIZE, frame, png, strip


class MascotAssetsTests(unittest.TestCase):
    def test_all_states_have_visible_transparent_frames(self):
        for state,(centres,*_) in ROWS.items():
            for index in range(len(centres)):
                with self.subTest(state=state,index=index):
                    image=frame(state,index)
                    self.assertEqual(image.size,SIZE)
                    alpha=image.getchannel('A')
                    self.assertIsNotNone(alpha.getbbox())
                    self.assertEqual(alpha.getpixel((0,0)),0)
                    self.assertLess(sum(alpha.histogram()[1:]),SIZE[0]*SIZE[1]*.65)
                    self.assertGreater(sum(alpha.histogram()[1:]),250)

    def test_browser_strip_matches_native_frame_sequence(self):
        for state in ROWS:
            image=Image.open(BytesIO(strip(state)))
            self.assertEqual(image.size,(SIZE[0]*len(ROWS[state][0]),SIZE[1]))
            for i in range(len(ROWS[state][0])):
                self.assertEqual(image.crop((i*80,0,(i+1)*80,96)).tobytes(),
                                 Image.open(BytesIO(png(state,i))).tobytes())
