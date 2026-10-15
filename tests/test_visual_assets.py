import tempfile
import unittest
from unittest.mock import patch, Mock
from pathlib import Path
from PIL import Image
import visual_assets as v


class VisualAssetTests(unittest.TestCase):
    def setUp(self):
        v._MEMORY.clear()
        v._COMFY_UNAVAILABLE = False
        self.workflow_patch = patch('comfyui_client.workflow_path', return_value=Path('/tmp/youtube-auto-no-workflow.json'))
        self.workflow_patch.start()
        self.addCleanup(self.workflow_patch.stop)

    def test_only_known_reusable_licenses(self):
        self.assertTrue(v.permitted_license({'LicenseShortName':{'value':'CC BY 4.0'}}))
        self.assertFalse(v.permitted_license({'LicenseShortName':{'value':'CC BY-SA 4.0'}}))
        self.assertFalse(v.permitted_license({'LicenseShortName':{'value':'All rights reserved'}}))
        self.assertFalse(v.permitted_license({}))

    def test_wrong_image_rejected_and_not_cached_as_approved(self):
        import io
        b=io.BytesIO();Image.new('RGB',(40,40),'red').save(b,format='JPEG')
        candidate={'title':'Unrelated image','image_url':'https://example.test/image.jpg','source_url':'https://example.test/source'}
        response=Mock(content=b.getvalue())
        with tempfile.TemporaryDirectory() as tmp, patch.object(v,'CACHE',Path(tmp)), patch.object(v,'provider_name',return_value='ollama'), patch.object(v,'plan_visual',return_value={'subject':'carbon star','query':'carbon star'}), patch.object(v,'search_candidates',return_value=iter([candidate])), patch.object(v.requests,'get',return_value=response), patch.object(v,'check_relevance',return_value={'matches':False,'reason':'wrong object','caption':''}):
            self.assertIsNone(v.relevant_image('Carbon star','A carbon-rich astronomical star.'))
            self.assertEqual(list(Path(tmp).glob('*.json')),[])

    def test_similar_star_name_does_not_pass_metadata(self):
        plan={'subject':'carbon star'}
        self.assertFalse(v.metadata_matches('Carbon star','A carbon-rich star.',plan,{'title':'File:BW Sculptoris.jpg','description':'BW Sculptoris in Legacy Survey'}))
        self.assertTrue(v.metadata_matches('Carbon star','A carbon-rich star.',plan,{'title':'A red giant','description':'An observation of R Sculptoris.'}))

    def test_manifest_preserves_attribution(self):
        image=Image.new('RGB',(40,40))
        image.info['visual_asset']={'source_url':'https://commons.wikimedia.org/example','author':'ESO','license':'CC BY 4.0'}
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'video.mp4'
            v.save_visual_manifest(path,[image,image,None])
            import json
            assets=json.loads((Path(tmp)/'video_visuals.json').read_text())
            self.assertEqual(len(assets),1)
            self.assertEqual(assets[0]['author'],'ESO')

    def test_generated_image_is_checked_and_cached_with_label(self):
        image=Image.new('RGB',(32,32),'red')
        workflow=Mock();workflow.exists.return_value=True;workflow.read_text.return_value='test workflow'
        with tempfile.TemporaryDirectory() as tmp, patch.object(v,'CACHE',Path(tmp)), patch('comfyui_client.workflow_path',return_value=workflow), patch('comfyui_client.generate_image',return_value=image) as generate, patch.object(v,'provider_name',return_value='ollama'), patch.object(v,'plan_visual',return_value={'subject':'carbon star','query':'star'}), patch.object(v,'check_relevance',return_value={'matches':True,'reason':'An appropriate conceptual illustration'}), patch.object(v,'search_candidates') as search:
            result=v.relevant_image('Carbon star','A red giant with carbon-rich gas.')
            self.assertEqual(result.info['visual_asset']['kind'],'generated')
            self.assertIn('AI-generated',result.info['visual_asset']['caption'])
            self.assertIs(v.relevant_image('Carbon star','A red giant with carbon-rich gas.'),result)
            generate.assert_called_once()
            search.assert_not_called()

    def test_unavailable_comfy_is_not_retried_for_every_scene(self):
        workflow=Mock();workflow.exists.return_value=True;workflow.read_text.return_value='test workflow'
        with tempfile.TemporaryDirectory() as tmp, patch.object(v,'CACHE',Path(tmp)), patch('comfyui_client.workflow_path',return_value=workflow), patch('comfyui_client.generate_image',side_effect=TimeoutError('slow')) as generate, patch.object(v,'provider_name',return_value='ollama'), patch.object(v,'plan_visual',return_value={'subject':'star','query':'star'}), patch.object(v,'search_candidates',return_value=[]):
            self.assertIsNone(v.relevant_image('Star','Scene one'))
            self.assertIsNone(v.relevant_image('Star','Scene two'))
            generate.assert_called_once()

    def test_check_relevance_uses_illustration_prompt_for_generated(self):
        image = Image.new('RGB', (32, 32), 'blue')
        candidate = {'kind': 'generated', 'title': 'AI-generated illustration: star'}
        plan = {'subject': 'star', 'query': 'star'}
        with patch.object(v, 'generate_json') as gen:
            gen.return_value = {'matches': True, 'reason': 'Clear illustration', 'caption': 'AI-generated illustration of a star'}
            res = v.check_relevance('Star', 'A hot star.', plan, candidate, image)
            self.assertTrue(res['matches'])
            prompt = gen.call_args[0][0]
            self.assertIn('AI-generated educational illustration', prompt)
            self.assertIn('conceptual illustration', prompt)

    def test_check_relevance_uses_metadata_prompt_for_sourced(self):
        image = Image.new('RGB', (32, 32), 'green')
        candidate = {'title': 'File:Star.jpg', 'source_url': 'https://example.com'}
        plan = {'subject': 'star', 'query': 'star'}
        with patch.object(v, 'generate_json') as gen:
            gen.return_value = {'matches': True, 'reason': 'Matches astronomical observation', 'caption': 'Observation of star'}
            res = v.check_relevance('Star', 'A hot star.', plan, candidate, image)
            self.assertTrue(res['matches'])
            prompt = gen.call_args[0][0]
            self.assertIn('pixels alone cannot identify', prompt)

    def test_find_cached_topic_images(self):
        import json
        with tempfile.TemporaryDirectory() as tmp:
            tmp_cache = Path(tmp)
            with patch.object(v, 'CACHE', tmp_cache):
                meta = {'topic': 'Carbon star', 'title': 'Test star', 'kind': 'generated'}
                (tmp_cache / 'test1.json').write_text(json.dumps(meta))
                Image.new('RGB', (16, 16), 'red').save(tmp_cache / 'test1.jpg')

                results = v.find_cached_topic_images('Carbon star')
                self.assertEqual(len(results), 1)
                self.assertEqual(results[0].info['visual_asset']['topic'], 'Carbon star')

                single = v.find_cached_topic_image('carbon star')
                self.assertIsNotNone(single)
                self.assertEqual(single.info['visual_asset']['title'], 'Test star')

class AISceneTests(unittest.TestCase):
    def setUp(self):
        v._MEMORY.clear()

    def test_scene_prompt_is_grounded_and_cached_per_narration(self):
        workflow = Mock()
        workflow.exists.return_value = True
        workflow.read_text.return_value = 'scene workflow'
        with tempfile.TemporaryDirectory() as tmp, \
             patch.dict('os.environ', {'VIDEO_VISUALS': 'ai-scenes'}), \
             patch.object(v, 'CACHE', Path(tmp)), \
             patch('comfyui_client.workflow_path', return_value=workflow), \
             patch.object(v, 'generate_json', return_value={'subject': 'Lion', 'scene': 'Wide view of a lion resting.'}), \
             patch('comfyui_client.generate_image', return_value=Image.new('RGB', (40,40))) as generate, \
             patch.object(v, 'check_relevance', return_value={'matches': True, 'reason': 'Matches narration'}), \
             patch.object(v, 'search_candidates') as search:
            first = v.relevant_image('Lion', 'A lion rests.')
            self.assertIs(v.relevant_image('Lion', 'A lion rests.'), first)
            v.relevant_image('Lion', 'A lion walks.')
            self.assertEqual(generate.call_count, 2)
            self.assertIn('A lion walks.', generate.call_args.args[0])
            self.assertIn('scene_prompt', first.info['visual_asset'])
            search.assert_not_called()

    def test_missing_workflow_stops_without_stock_fallback(self):
        workflow = Mock()
        workflow.exists.return_value = False
        with patch.dict('os.environ', {'VIDEO_VISUALS': 'ai-scenes'}), \
             patch('comfyui_client.workflow_path', return_value=workflow), \
             patch.object(v, 'search_candidates') as search:
            with self.assertRaisesRegex(RuntimeError, 'require a ComfyUI'):
                v.relevant_image('Lion', 'A lion rests.')
            search.assert_not_called()
