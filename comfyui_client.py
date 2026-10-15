"""Run an exported local ComfyUI API workflow without changing installed models."""
import copy
import io
import json
import os
from pathlib import Path
import secrets
import time
import requests
from PIL import Image


def workflow_path():
    return Path(os.getenv('COMFYUI_WORKFLOW', 'comfyui_workflow.json')).expanduser()


def prepare_workflow(workflow, prompt):
    workflow = copy.deepcopy(workflow)
    if not isinstance(workflow, dict) or not workflow or any(not isinstance(n, dict) or 'class_type' not in n for n in workflow.values()):
        raise ValueError('Export API format, not the normal canvas JSON')
    replaced = 0
    for node in workflow.values():
        if node['class_type'] == 'LoadImage':
            raise ValueError('Use a text-to-image workflow without required reference images')
        inputs = node.get('inputs', {})
        for name, value in list(inputs.items()):
            if isinstance(value, str) and '{{PROMPT}}' in value:
                inputs[name] = value.replace('{{PROMPT}}', prompt)
                replaced += 1
        if node['class_type'] in ('KSampler', 'SamplerCustomAdvanced', 'RandomNoise'):
            for name in ('seed', 'noise_seed'):
                if name in inputs and isinstance(inputs[name], int):
                    inputs[name] = secrets.randbelow(2**48)
    if not replaced:
        raise ValueError('Put {{PROMPT}} in the positive text prompt before exporting')
    return workflow


def generate_image(prompt):
    base = os.getenv('COMFYUI_BASE_URL', 'http://127.0.0.1:8188').rstrip('/')
    workflow = prepare_workflow(json.loads(workflow_path().read_text()), prompt)
    response = requests.post(base+'/prompt', json={'prompt': workflow, 'client_id': secrets.token_hex(16)}, timeout=30)
    response.raise_for_status()
    job = response.json()['prompt_id']
    print(f'  ComfyUI job submitted: {job}', flush=True)
    deadline = time.monotonic() + int(os.getenv('COMFYUI_TIMEOUT', '900'))
    while time.monotonic() < deadline:
        response = requests.get(base+'/history/'+job, timeout=30)
        response.raise_for_status()
        result = response.json().get(job, {})
        if result.get('status', {}).get('status_str') == 'error':
            messages = result.get('status', {}).get('messages', [])
            detail = next((str(m[1].get('exception_message', '')) for m in messages if len(m) > 1 and m[0] == 'execution_error'), '')
            raise RuntimeError('ComfyUI workflow execution failed: '+detail[:500])
        for output in result.get('outputs', {}).values():
            for item in output.get('images', []):
                if item.get('type') != 'output':
                    continue
                response = requests.get(base+'/view', params={k:item[k] for k in ('filename','subfolder','type') if k in item}, timeout=60)
                response.raise_for_status()
                return Image.open(io.BytesIO(response.content)).convert('RGB')
        time.sleep(2)
    # Cancel only our job, never another user's active generation.
    response = requests.get(base+'/queue', timeout=30)
    response.raise_for_status()
    queue = response.json()
    if any(item[1] == job for item in queue.get('queue_pending', [])):
        requests.post(base+'/queue', json={'delete':[job]}, timeout=30).raise_for_status()
    raise TimeoutError('ComfyUI generation timed out; removed queued request; an active render may still be running')


if __name__ == '__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prompt', required=True)
    parser.add_argument('--output', default='generated/comfyui_test.png')
    args=parser.parse_args()
    image=generate_image(args.prompt)
    path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True)
    image.save(path)
    print(path.resolve())
