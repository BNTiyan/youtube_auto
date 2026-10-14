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
            self.assertEqual(len(short_script_pages(script)), 3)

    def test_unfinished_generated_text_rejected(self):
        with patch('llm_client.generate_json', return_value={'script': 'This stops mid'}):
            with self.assertRaisesRegex(ValueError, 'unfinished'):
                build_short_script('Topic', 'word ' * 110)

    def test_long_title_and_sentence_fit_without_slicing(self):
        frame = create_short_slide('Retrieval Augmented Generation', 'The model retrieves relevant documents and uses their information to produce a more useful answer with source context.', TECH_THEMES['rag'])
        self.assertEqual(frame.shape, (1920,1080,3))


if __name__ == '__main__':
    unittest.main()
