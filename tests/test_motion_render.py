"""Check the actual renderer emits motion and keeps media inputs compatible."""
import unittest
import numpy as np
from PIL import Image
from animation_utils import build_animated_clip
from tech_video_creator import create_tech_slide, create_points_slide, TECH_THEMES


class MotionRenderTests(unittest.TestCase):
    def test_diagram_moves_after_text_settles(self):
        slide = create_tech_slide('Local AI', 'Create on your computer.', TECH_THEMES['ai'])
        clip = build_animated_clip(slide, 8, animate=False)
        try:
            a, b = clip.get_frame(3), clip.get_frame(4)
            self.assertEqual(a.shape, (720, 1280, 3))
            self.assertGreater(np.count_nonzero(a[160:595, 804:1216] != b[160:595, 804:1216]), 100)
        finally:
            clip.close()

    def test_five_points_reveal_and_image_input(self):
        slide = create_points_slide('Key ideas', ['A point to remember'] * 5, TECH_THEMES['ai'])
        early, late = slide.scene.frame(.1), slide.scene.frame(3)
        self.assertGreater(np.count_nonzero(early[550:635] != late[550:635]), 100)
        photo = Image.new('RGB', (300, 200), 'blue')
        scene = create_tech_slide('Title', 'Explanation', TECH_THEMES['ai'], image=photo)
        self.assertEqual(scene.scene.frame(2).shape, (720, 1280, 3))


class KidsMotionTests(unittest.TestCase):
    def test_kids_motion_with_and_without_photo(self):
        from video_creator import create_slide, THEMES
        for photo in (None, Image.new('RGB', (300, 200), 'orange')):
            slide = create_slide('Hello explorers', 'Discover a new animal today.', THEMES['animals'], image=photo)
            clip = build_animated_clip(slide, 8, animate=False)
            try:
                a, b = clip.get_frame(2), clip.get_frame(3)
                self.assertEqual(a.shape, (720, 1280, 3))
                self.assertGreater(np.count_nonzero(a[150:620, 800:1220] != b[150:620, 800:1220]), 100)
                # Settled text remains still while the illustration moves.
                np.testing.assert_array_equal(a[140:620, 50:750], b[140:620, 50:750])
            finally:
                clip.close()


if __name__ == '__main__':
    unittest.main()
