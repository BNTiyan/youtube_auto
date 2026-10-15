"""Persist editorial feedback and reuse matching preferences in future generations."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
from datetime import datetime, timezone

FILE = Path(os.getenv('VIDEO_FEEDBACK_FILE', 'content_feedback.json'))


def entries():
    if not FILE.exists(): return []
    data = json.loads(FILE.read_text())
    return data.get('entries', [])


def matching_feedback(topic, scope='all', limit=8):
    words=set(re.findall(r'\w+', topic.lower()))
    matched=[]
    for item in entries():
        if item.get('scope','all') not in ('all',scope): continue
        target=item.get('topic','').strip().lower()
        if item.get('applies_to') != 'all' and target and not (bool(topic.strip()) and (target in topic.lower() or topic.lower() in target or len(words & set(re.findall(r'\w+',target)))>=2)): continue
        matched.append(item)
    return matched[-limit:]


def feedback_context(topic, scope='all'):
    matches=matching_feedback(topic,scope)
    if not matches: return ''
    return '\nEDITORIAL FEEDBACK FROM APPROVED REVIEWERS (preferences, not factual evidence):\n' + json.dumps([
        {key:x.get(key) for key in ('rating','comment','prefer','topic')} for x in matches
    ],ensure_ascii=False)


def add_feedback(topic, rating, comment, prefer='auto', scope='all', applies_to='topic', record_id=None, video_url=''):
    if rating not in range(1,6): raise ValueError('Rating must be 1–5')
    if prefer not in ('auto','sourced','generated'): raise ValueError('Invalid image preference')
    if scope not in ('all','script','visuals'): raise ValueError('Invalid feedback scope')
    if applies_to not in ('topic','all'): raise ValueError('Invalid feedback target')
    if not comment.strip(): raise ValueError('Feedback comment is required')
    record={'id':record_id or hashlib.sha256((topic+comment+str(datetime.now(timezone.utc))).encode()).hexdigest()[:16],
            'topic':topic[:200],'rating':rating,'comment':comment[:3000],'prefer':prefer,'scope':scope,
            'applies_to':applies_to,'video_url':video_url[:500], 'saved_at':datetime.now(timezone.utc).isoformat()}
    data=[e for e in entries() if e['id']!=record['id']]+[record]
    FILE.parent.mkdir(parents=True,exist_ok=True)
    FILE.write_text(json.dumps({'entries':data},ensure_ascii=False,indent=2)+'\n')
    return record


def from_event(path):
    event=json.loads(Path(path).read_text());issue=event['issue'];body=issue.get('body') or ''
    def field(name,default=''):
        m=re.search(r'^## '+re.escape(name)+r'\s*\n(.*?)(?=^## |\Z)',body,re.M|re.S)
        return m.group(1).strip() if m else default
    return add_feedback(field('Topic'),int(field('Rating')),field('Feedback'),field('Image Preference','auto'),field('Scope','all'),field('Applies To','topic'),record_id='issue-'+str(issue['number']),video_url=field('Video URL'))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--topic',default='');p.add_argument('--rating',type=int);p.add_argument('--comment')
    p.add_argument('--prefer',choices=['auto','sourced','generated'],default='auto')
    p.add_argument('--scope',choices=['all','script','visuals'],default='all')
    p.add_argument('--applies-to',choices=['topic','all'],default='topic')
    p.add_argument('--from-event');p.add_argument('--show',action='store_true')
    a=p.parse_args()
    if a.from_event: from_event(a.from_event);print('Feedback saved')
    elif a.show: print(json.dumps(entries(),ensure_ascii=False,indent=2))
    elif a.rating and a.comment: add_feedback(a.topic,a.rating,a.comment,a.prefer,a.scope,a.applies_to);print('Feedback saved')
    else: p.error('Provide --rating and --comment, --show, or --from-event')
