"""Consistent media filenames for topic output, renderers, and upload steps."""
import re
import unicodedata


def video_slug(title):
    text = unicodedata.normalize('NFKC', str(title or '')).lower()
    text = re.sub(r'[^\w]+', '_', text, flags=re.UNICODE).strip('_')
    # Leave room for media suffixes within common filesystem filename limits.
    text = text.encode('utf-8')[:180].decode('utf-8', errors='ignore').rstrip('_')
    return text or 'latest_topic'
