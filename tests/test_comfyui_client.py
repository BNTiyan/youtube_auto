import unittest
from comfyui_client import prepare_workflow

class ComfyWorkflowTests(unittest.TestCase):
    def test_replaces_only_explicit_prompt_and_preserves_original(self):
        original={'1':{'class_type':'CLIPTextEncode','inputs':{'text':'Illustration: {{PROMPT}}'}},'2':{'class_type':'CLIPTextEncode','inputs':{'text':'bad anatomy'}}}
        result=prepare_workflow(original,'carbon star')
        self.assertEqual(result['1']['inputs']['text'],'Illustration: carbon star')
        self.assertEqual(result['2']['inputs']['text'],'bad anatomy')
        self.assertIn('{{PROMPT}}',original['1']['inputs']['text'])
    def test_rejects_canvas_and_reference_workflows(self):
        for value in ({'nodes':[]},{'1':{'class_type':'LoadImage','inputs':{}}}):
            with self.assertRaises(ValueError): prepare_workflow(value,'star')
    def test_requires_prompt_marker(self):
        with self.assertRaises(ValueError):
            prepare_workflow({'1':{'class_type':'CLIPTextEncode','inputs':{'text':'fixed'}}},'star')
    def test_generation_fetches_output_image(self):
        import io
        from unittest.mock import patch, Mock
        from PIL import Image
        import comfyui_client as c
        buffer=io.BytesIO();Image.new('RGB',(16,16),'red').save(buffer,format='PNG')
        workflow={'1':{'class_type':'CLIPTextEncode','inputs':{'text':'{{PROMPT}}'}}}
        path=Mock();path.read_text.return_value=__import__('json').dumps(workflow)
        submitted=Mock();submitted.json.return_value={'prompt_id':'test'}
        history=Mock();history.json.return_value={'test':{'outputs':{'2':{'images':[{'filename':'out.png','subfolder':'','type':'output'}]}}}}
        output=Mock(content=buffer.getvalue())
        with patch.object(c,'workflow_path',return_value=path),patch.object(c.requests,'post',return_value=submitted),patch.object(c.requests,'get',side_effect=[history,output]):
            self.assertEqual(c.generate_image('star').size,(16,16))
