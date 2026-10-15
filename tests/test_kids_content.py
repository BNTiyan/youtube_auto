import unittest
from unittest.mock import patch
from kids_content import build_kids_prompt, generate_kids_lesson
from latest_topic_pipeline import normalize_topic_package


class KidsContentTests(unittest.TestCase):
    def test_prompt_has_age_language_and_topic_context(self):
        prompt = build_kids_prompt('Ramayanam', 'A story about Rama.', 'te')
        self.assertIn('ages 8–12', prompt)
        self.assertIn('language code: te', prompt)
        self.assertIn('in the story', prompt)
        self.assertIn('concrete example', prompt)
        self.assertIn('Hook the audience immediately in the very first sentence', prompt)
        self.assertIn('Hi friends', prompt)

    def test_lesson_sections_reach_creator_config(self):
        data = {'video_topic':'Lion families', 'video_summary':'Lions live in prides.', 'short_text':'Lions live in family groups.', 'points':['Cooperation'], 'sections':[{'title':'A pride','narration':'Lions live in groups called prides.', 'slide_text':'A pride is a group of lions.'} for _ in range(4)]}
        with patch('kids_content.generate_json', return_value=data):
            lesson = generate_kids_lesson('Lions', 'Source text', 'en')
        item=normalize_topic_package(lesson, channel='childishdreamer')['creator_config']['general']['items'][0]
        self.assertEqual(item['audience'], '8-12')
        self.assertEqual(len(item['sections']), 4)
        self.assertEqual(item['fact'], data['short_text'])

    def test_question_answer_is_included_in_spoken_narration(self):
        data = {'video_topic':'Lions', 'video_summary':'Summary', 'short_text':'A complete short.',
                'sections': {role: {'title':role, 'narration':'What is a pride?' if role=='question' else 'Lions live in prides.', 'slide_text':'Lions live in prides.'} for role in ('explain','example','question','takeaway')}}
        data['sections']['question']['answer'] = 'A pride is a group of lions.'
        with patch('kids_content.generate_json', return_value=data):
            lesson = generate_kids_lesson('Lions', 'Lions live in prides.')
        self.assertIn('A pride is a group of lions.', lesson['sections'][2]['narration'])

    def test_incomplete_lesson_rejected(self):
        with patch('kids_content.generate_json', return_value={'video_topic':'Lions','video_summary':'Summary','short_text':'Short.', 'sections':[]}):
            with self.assertRaisesRegex(ValueError, 'four complete sections'):
                generate_kids_lesson('Lions','Source')
