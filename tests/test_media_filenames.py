import tempfile
import unittest
from pathlib import Path
import numpy as np
from moviepy import AudioClip, ColorClip, VideoFileClip
from filename_utils import video_slug
from latest_topic_pipeline import slugify


class MediaFilenameTests(unittest.TestCase):
    def test_all_topics_get_safe_consistent_slugs(self):
        for title in ['Ramayanam: Dharma, Love, Victory', '../../Outside', 'AI / ML: What?', 'రామాయణం', 'x'*400]:
            slug = video_slug(title)
            self.assertEqual(slugify(title), slug)
            self.assertNotIn(':', slug)
            self.assertNotIn('/', slug)
            self.assertNotIn('.', slug)
            self.assertLessEqual(len(slug.encode('utf8')), 180)
        self.assertEqual(video_slug('Ramayanam: Dharma, Love, Victory'), 'ramayanam_dharma_love_victory')

    def test_encode_topic_with_colon_and_audio(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / (video_slug('Ramayanam: Dharma, Love, Victory') + '_short.mp4')
            audio = AudioClip(lambda t: .05*np.sin(2*np.pi*440*t), duration=.4, fps=44100)
            base = ColorClip((64,64), color=(20,80,100), duration=.6)
            video = base.with_audio(audio)
            try:
                video.write_videofile(str(output), fps=10, codec='libx264', audio_codec='aac', temp_audiofile=str(Path(tmp)/'render_audio.m4a'), logger=None)
                with VideoFileClip(str(output)) as result:
                    self.assertIsNotNone(result.audio)
                    self.assertGreater(result.duration, .4)
            finally:
                video.close()
                base.close()
                audio.close()


if __name__ == '__main__':
    unittest.main()
