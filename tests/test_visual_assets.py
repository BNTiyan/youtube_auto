import tempfile
import unittest
from unittest.mock import patch, Mock
from pathlib import Path
from PIL import Image
import visual_assets as v


class VisualAssetTests(unittest.TestCase):
    def setUp(self):
        v._MEMORY.clear()

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
