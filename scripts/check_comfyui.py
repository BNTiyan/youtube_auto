"""Check the configured workflow and installed ComfyUI models without rendering."""
import json
import os
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import requests
from comfyui_client import prepare_workflow, workflow_path

path=workflow_path()
if not path.exists():
    print('No ComfyUI workflow configured; using sourced visuals.')
    raise SystemExit(0)
workflow=prepare_workflow(json.loads(path.read_text()),'Integration check')
base=os.getenv('COMFYUI_BASE_URL','http://127.0.0.1:8188').rstrip('/')
try:
    response=requests.get(base+'/object_info',timeout=10)
    response.raise_for_status()
    nodes=response.json()
    for node in workflow.values():
        name=node['class_type']
        if name not in nodes: raise ValueError('Missing ComfyUI node: '+name)
        required=nodes[name].get('input',{}).get('required',{})
        for key in ('unet_name','clip_name','vae_name'):
            if key in node.get('inputs',{}):
                available=required.get(key,[[]])[0]
                if node['inputs'][key] not in available:
                    raise ValueError('Missing model: '+node['inputs'][key])
    print('ComfyUI reachable; workflow nodes and installed model names verified.')
except (requests.RequestException,ValueError) as error:
    print(f'ComfyUI preflight warning: {error}. Visual selection will use sourced fallback.')
