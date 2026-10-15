import tempfile
import unittest
from pathlib import Path
from PIL import Image
from thumbnail_utils import create_thumbnail
from video_creator import load_font


class ThumbnailTests(unittest.TestCase):
    def test_thumbnail_uses_artwork_and_fits_upload_dimensions(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = create_thumbnail(str(Path(tmp)/'lion.mp4'), 'Why Lions Live in Prides',
                                    [Image.new('RGB', (900, 900), 'red')], load_font)
            with Image.open(path) as image:
                self.assertEqual(image.size, (1280, 720))
                red, green, blue = image.getpixel((950, 360))
                self.assertGreater(red, 200)
                self.assertLess(green, 30)
            self.assertLess(Path(path).stat().st_size, 2*1024*1024)

    def test_text_only_thumbnail(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = create_thumbnail(str(Path(tmp)/'topic.mp4'), 'Retrieval Augmented Generation', [], load_font)
            self.assertTrue(Path(path).is_file())
