"""Only registered feeds and explicitly imported source material are collected."""
from datetime import datetime
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from urllib.parse import parse_qs,urlsplit
from defusedxml import ElementTree as ET
from .contracts import Raw,Source
from .transport import get_text


class Text(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts=[]; self.skip=0
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style'):
            self.skip+=1
    def handle_endtag(self,tag):
        if tag in ('script','style'):
            self.skip=max(0,self.skip-1)
    def handle_data(self,data):
        if not self.skip:
            self.parts.append(data)


def plain(text):
    parser=Text();parser.feed(text);return ' '.join(' '.join(parser.parts).split())


def parse_feed(text,source):
    records=[]
    for node in ET.fromstring(text).iter():
        if node.tag.split('}')[-1] not in ('entry','item'):
            continue
        fields={n.tag.split('}')[-1]:n for n in node}
        def value(key):
            n=fields.get(key)
            return ''.join(n.itertext()).strip() if n is not None else ''
        link=fields.get('link')
        href=(link.attrib.get('href') or link.text or '') if link is not None else ''
        date=value('published') or value('pubDate') or value('updated')
        try:
            try:
                published=datetime.fromisoformat(date.replace('Z','+00:00'))
            except ValueError:
                published=parsedate_to_datetime(date)
            body=value('content') or value('encoded')
            evidence='full_text' if body else 'feed_excerpt'
            body=body or value('description') or value('summary')
            if not body and source.platform=='youtube':
                body=value('title'); evidence='title_only'
            records.append(Raw(source_id=source.id,url=href,title=value('title'),published=published,
                               text=plain(body)[:100000],evidence=evidence,locator='RSS/Atom content' if evidence=='full_text' else 'RSS excerpt'))
        except (ValueError,TypeError,IndexError):
            continue
    return records[:8]


def collect(store):
    total=failed=0
    for source in store.sources().values():
        if not source.feed_url:
            continue
        try:
            records=parse_feed(get_text(source.feed_url),source)
            for record in records:
                from .contracts import digest
                key=digest(record.url)
                current=next((r for k,r,_,_,_ in store.records() if k==key),None)
                if not (current and current.evidence=='transcript' and record.evidence=='title_only'):
                    store.ingest(record)
                if source.platform=='youtube':
                    if current and current.evidence=='transcript':
                        continue
                    try:
                        video(store,source.id,record.url,record.published,record.title)
                    except Exception as exc:
                        store.event('transcript_failed',source=source.id,id=key,error=type(exc).__name__)
            total+=len(records)
            store.event('collection',source=source.id,found=len(records),status='ok' if records else 'empty')
        except Exception as exc:
            failed+=1
            store.event('collection',source=source.id,found=0,status='failed',error=type(exc).__name__)
    return {'collected':total,'failed_sources':failed}


def video(store,source_id,url,published,title):
    source=store.sources()[source_id]
    if source.platform!='youtube':
        raise ValueError('youtube_source_required')
    p=urlsplit(url)
    vid=parse_qs(p.query).get('v',[''])[0] if p.hostname in ('www.youtube.com','youtube.com') else p.path.lstrip('/') if p.hostname=='youtu.be' else ''
    import re
    if not re.fullmatch('[A-Za-z0-9_-]{11}',vid):
        raise ValueError('invalid_video_url')
    from youtube_transcript_api import YouTubeTranscriptApi
    transcript=YouTubeTranscriptApi().fetch(vid,languages=['en','zh-Hans','zh'])
    text='\n'.join(f'[{s.start:.0f}s] {s.text}' for s in transcript)
    return store.ingest(Raw(source_id=source.id,url='https://www.youtube.com/watch?v='+vid,
        published=published,title=title,text=text[:100000],evidence='transcript',locator='timestamped transcript'))
