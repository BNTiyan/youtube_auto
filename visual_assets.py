"""Find attributed Commons images, checking source metadata and pixels against a script."""
import base64
import hashlib
import io
import json
import os
from pathlib import Path
from html import unescape
import re
import requests
from PIL import Image, ImageOps
from llm_client import generate_json, provider_name

COMMONS_API = 'https://commons.wikimedia.org/w/api.php'
HEADERS = {'User-Agent': 'YouTubeAuto/1.0 (https://github.com/BNTiyan/youtube_auto)'}
CACHE = Path(os.getenv('VIDEO_VISUAL_CACHE', 'generated/visual_cache'))
_MEMORY = {}


def plain(value):
    return unescape(re.sub('<[^>]+>', '', value or '')).strip()


def permitted_license(metadata):
    name = plain(metadata.get('LicenseShortName', {}).get('value', '')).lower()
    return (name.startswith('cc by') and not name.startswith(('cc by-sa', 'cc by-nc', 'cc by-nd'))) or name.startswith(('cc0', 'public domain'))


def plan_visual(topic, narration):
    data = generate_json(
        'Choose an exact image-search subject for this educational script. Return JSON '
        'with subject (English subject name), query (a precise English Wikimedia Commons search), '
        'and avoid (a short list of misleading alternatives). Preserve the real scientific entity '
        'or concept. A carbon star means an astronomical star, not carbon atoms, a celebrity, or a logo. '
        'Do not ask for generic technology, office, laptop, AI robot, book, or decorative star photos. '
        'For a story, specify a clearly labeled illustration, not a claimed historical photograph.\n'
        f'Topic: {topic}\nNarration: {narration}',
        schema={'type':'object','properties':{'subject':{'type':'string'},'query':{'type':'string'},'avoid':{'type':'array','items':{'type':'string'}}},'required':['subject','query','avoid']},
    )
    if not all(isinstance(data.get(k), str) and data[k].strip() for k in ('subject','query')):
        raise ValueError('Visual plan needs an exact subject and query')
    return data


def metadata_matches(topic, narration, plan, candidate):
    """Require source text evidence before asking vision; similar-looking objects are insufficient."""
    source = (candidate.get('title','') + ' ' + candidate.get('description','')).lower().replace('_',' ')
    context = (topic + ' ' + narration).lower()
    if re.search(r'carbon[ -](?:rich[ -])?star', context):
        # R Sculptoris is a documented carbon-rich star; BW Sculptoris is a different object.
        return bool(re.search(r'carbon[ -](?:rich[ -])?star|carbon.rich.*\bstar|\br sculptoris\b', source))
    tokens = re.findall(r'[a-z0-9]+', plan['subject'].lower())
    stop = {'a','an','the','of','and','in','on','how','why','what','is','are','for','with','image','photo','photograph','illustration','diagram'}
    tokens = [t for t in tokens if t not in stop]
    return bool(tokens) and all(re.search(r'\b'+re.escape(token)+r'\b', source) for token in tokens)


def search_candidates(query):
    response = requests.get(COMMONS_API, params={
        'action':'query', 'format':'json', 'generator':'search',
        'gsrsearch':query, 'gsrnamespace':6, 'gsrlimit':5,
        'prop':'imageinfo', 'iiprop':'url|extmetadata|mime', 'iiurlwidth':1100,
    }, headers=HEADERS, timeout=20)
    response.raise_for_status()
    pages = response.json().get('query', {}).get('pages', {}).values()
    for page in sorted(pages, key=lambda p:p.get('index', 999)):
        info = (page.get('imageinfo') or [{}])[0]
        if info.get('mime') not in ('image/jpeg','image/png','image/tiff','image/webp'):
            continue
        metadata = info.get('extmetadata', {})
        if not permitted_license(metadata):
            continue
        yield {
            'title': page['title'], 'image_url':info.get('thumburl') or info.get('url'),
            'source_url':info.get('descriptionurl'),
            'description':plain(metadata.get('ImageDescription',{}).get('value',''))[:4000],
            'author':plain(metadata.get('Artist',{}).get('value','')),
            'license':plain(metadata.get('LicenseShortName',{}).get('value','')),
            'license_url':plain(metadata.get('LicenseUrl',{}).get('value','')),
        }


def check_relevance(topic, narration, plan, candidate, image):
    # Resize only the model input; retain the original image for the rendered video.
    preview = image.copy()
    preview.thumbnail((768,768))
    buffer = io.BytesIO()
    preview.save(buffer, format='JPEG', quality=85)
    verdict = generate_json(
        'Check whether this image AND its source description directly support the educational script. '
        'The source metadata identifies the object; pixels alone cannot identify a specific star or species. '
        'Reject a different named object, decorative icon, unrelated stock scene, printed catalogue, '
        'or ambiguous match. A scientific observation or explicitly labeled scientific visualization is acceptable '
        'when the source identifies the right subject. Return JSON matches (boolean), reason (string), '
        'and caption (a short factual English identification; distinguish observation, diagram, or illustration).\n'
        f'Topic: {topic}\nScript: {narration}\nPlan: {json.dumps(plan)}\n'
        f'Source: {json.dumps(candidate)}',
        schema={'type':'object','properties':{'matches':{'type':'boolean'},'reason':{'type':'string'},'caption':{'type':'string'}},'required':['matches','reason','caption']},
        model=os.getenv('VISUAL_LLM_MODEL','qwen3.5:4b'),
        images=[base64.b64encode(buffer.getvalue()).decode('ascii')],
    )
    return verdict


def relevant_image(topic, narration):
    """Return an approved image or None. Never substitute a random search result."""
    if os.getenv('VIDEO_VISUALS', 'verified') == 'local' or provider_name() != 'ollama':
        return None
    key = hashlib.sha256(('metadata-v2\n'+topic+'\n'+narration).encode()).hexdigest()
    if key in _MEMORY:
        return _MEMORY[key]
    CACHE.mkdir(parents=True, exist_ok=True)
    metadata_path, image_path = CACHE/(key+'.json'), CACHE/(key+'.jpg')
    if metadata_path.exists() and image_path.exists():
        image = Image.open(image_path).convert('RGB')
        image.info['visual_asset'] = json.loads(metadata_path.read_text())
        _MEMORY[key] = image
        return image
    try:
        plan = plan_visual(topic, narration)
        if re.search(r'carbon[ -]star', topic, re.I):
            plan.update(subject='carbon star', query='"R Sculptoris" carbon')
        for candidate in list(search_candidates(plan['query']))[:3]:
            if not metadata_matches(topic, narration, plan, candidate):
                continue
            try:
                response = requests.get(candidate['image_url'], headers=HEADERS, timeout=20)
                response.raise_for_status()
                image = ImageOps.exif_transpose(Image.open(io.BytesIO(response.content))).convert('RGB')
                verdict = check_relevance(topic, narration, plan, candidate, image)
                if verdict.get('matches') is not True:
                    continue
                candidate.update(caption=re.sub(r'\.[^.]+$', '', candidate['title'].removeprefix('File:')).replace('_',' '), relevance_reason=verdict['reason'], topic=topic, query=plan['query'])
                image.save(image_path, quality=92)
                metadata_path.write_text(json.dumps(candidate, ensure_ascii=False, indent=2))
                image.info['visual_asset'] = candidate
                _MEMORY[key] = image
                print(f"  Relevant image: {candidate['title']} ({candidate['license']})")
                return image
            except (requests.RequestException, ValueError, OSError, KeyError) as exc:
                print(f'  Image candidate skipped: {type(exc).__name__}')
    except (requests.RequestException, ValueError, OSError, RuntimeError, KeyError) as exc:
        print(f'  No verified source image: {type(exc).__name__}; using a local teaching visual.')
    _MEMORY[key] = None
    return None


def image_credit(image):
    asset = image.info.get('visual_asset', {}) if image is not None else {}
    if not asset:
        return ''
    return f"{asset.get('author','')} / {asset.get('license','')}"


def save_visual_manifest(output_path, images):
    assets = {}
    for image in images:
        if image is not None and image.info.get('visual_asset'):
            asset=image.info['visual_asset']
            assets[asset['source_url']]=asset
    path=Path(output_path).with_suffix('')
    Path(str(path)+'_visuals.json').write_text(json.dumps(list(assets.values()),ensure_ascii=False,indent=2))
