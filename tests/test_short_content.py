import unittest
from unittest.mock import patch
from shorts_creator import build_short_script, short_script_pages, create_short_slide, TECH_THEMES


class ShortContentTests(unittest.TestCase):
    def test_explanation_and_all_points_preserved(self):
        script = build_short_script('RAG', 'RAG retrieves documents before answering.', ['It adds relevant context.', 'The model generates an answer.', 'Check the sources.'])
        self.assertIn('retrieves documents', script)
        self.assertIn('Check the sources.', script)
        self.assertEqual(' '.join(short_script_pages(script)), script)

    def test_long_source_rewritten_as_complete_short(self):
        with patch('llm_client.generate_json', return_value={'script': 'A complete explanation. A useful example. A final takeaway.'}) as generate:
            script = build_short_script('Topic', 'word ' * 110, source_text='Original full source')
            self.assertIn('Original full source', generate.call_args.args[0])
            self.assertIn('Hook the audience in the first sentence', generate.call_args.args[0])
            self.assertEqual(len(short_script_pages(script)), 3)

    def test_unfinished_generated_text_rejected(self):
        with patch('llm_client.generate_json', return_value={'script': 'This stops mid'}):
            with self.assertRaisesRegex(ValueError, 'unfinished'):
                build_short_script('Topic', 'word ' * 110)

    def test_long_title_and_sentence_fit_without_slicing(self):
        frame = create_short_slide('Retrieval Augmented Generation', 'The model retrieves relevant documents and uses their information to produce a more useful answer with source context.', TECH_THEMES['rag'])
        self.assertEqual(frame.shape, (1920,1080,3))

    def test_short_reuses_cached_video_images(self):
        from unittest.mock import Mock
        from PIL import Image
        import tempfile
        from pathlib import Path
        from shorts_creator import create_short

        cached = Image.new('RGB', (100, 100), 'purple')
        cached.info['visual_asset'] = {'title': 'Cached video illustration', 'topic': 'Star'}

        with tempfile.TemporaryDirectory() as tmp:
            out_file = Path(tmp) / 'star_short.mp4'
            with patch('shorts_creator.find_cached_topic_images', return_value=[cached]) as find_mock, \
                 patch('shorts_creator.relevant_image') as rel_mock, \
                 patch('shorts_creator.make_tts'), \
                 patch('shorts_creator.make_clip', return_value=Mock(duration=2)), \
                 patch('shorts_creator.concatenate_videoclips') as concat_mock, \
                 patch('shorts_creator.save_visual_manifest') as manifest_mock:
                final_mock = Mock()
                concat_mock.return_value = final_mock
                create_short('Star', 'A star is glowing in space.', 'space', str(out_file), use_images=True, prepared_for_kids=True)
                find_mock.assert_called_with('Star')
                rel_mock.assert_not_called()
                manifest_mock.assert_called_once()
                self.assertIn(cached, manifest_mock.call_args[0][1])


if __name__ == '__main__':
    unittest.main()
