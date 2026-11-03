"""Approved immutable editions; deterministic server-side counts and atomic export."""
import json
import os
import shutil
import tempfile
from datetime import UTC, datetime, timedelta
from importlib.resources import files
from pathlib import Path

from .contracts import digest, issues, timestamp


def statistics(items,at):
    latest={}
    for item in items:
        published=datetime.fromisoformat(item['published'])
        if not at-timedelta(days=7)<=published<=at or not item['ticker']:
            continue
        key=(item['group'],item['ticker'],item['horizon'])
        old=latest.get(key)
        if old is None or item['published']>old['published']:
            latest[key]=item
        elif item['published']==old['published'] and item['stance']!=old['stance']:
            latest[key]={**item,'stance':'unclear'}
    counts={'bullish':0,'neutral':0,'bearish':0}
    ranks={}
    for item in latest.values():
        if item['category']=='official' or item['stance'] not in counts or not item['quote']:
            continue
        counts[item['stance']]+=1
        key=(item['ticker'],item['horizon'])
        row=ranks.setdefault(key,{'ticker':key[0],'horizon':key[1],**dict.fromkeys(counts,0)})
        row[item['stance']]+=1
    return {'counts':counts,'ranks':sorted(ranks.values(),key=lambda r:(-r['bullish'],-sum(r[s] for s in counts),r['ticker'])),
            'opinions':sum(counts.values()),'window_start':(at-timedelta(days=7)).isoformat(),
            'as_of':at.isoformat(),'rule':'latest independent group × stock × horizon; 7 days'}


def project(key,raw,summary,source):
    return {'id':key,'url':raw.url,'published':raw.published.isoformat(),'collected':raw.collected.isoformat(),
        'speaker':source.speaker,'speaker_id':source.speaker_id,'group':source.group,
        'category':source.category,'platform':source.platform,'source':source.speaker,
        'identity_url':source.identity_url,'locator':raw.locator,
        **{k:getattr(summary,k) for k in ('title_zh','title_en','summary_zh','summary_en','stance','ticker',
                                        'horizon','quote','conditions_zh','conditions_en','method','producer','prompt_version')},
        'summary_hash':digest(summary.model_dump(mode='json'))}


def eligible(store,automatic=False):
    sources=store.sources()
    withdrawn=set(store.get('withdrawn',[]))
    result=[]
    for key,raw,summary,approval,approved_hash in store.records():
        if not summary or key in withdrawn or raw.source_id not in sources:
            continue
        source=sources[raw.source_id]
        if issues(raw,summary,source):
            continue
        if not automatic and (not approval or approved_hash!=digest(summary.model_dump(mode='json'))):
            continue
        result.append(project(key,raw,summary,source))
    return sorted(result,key=lambda i:(i['published'],i['id']),reverse=True)


def prepare(store,edition_id,backup=False,automatic=False,at=None,ids=None):
    at=at or datetime.now(UTC)
    if not edition_id or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._' for c in edition_id):
        raise ValueError('invalid_edition_id')
    items=eligible(store,automatic=automatic)
    if ids is not None:
        items=[i for i in items if i["id"] in ids]
        if len(items)!=len(set(ids)):
            raise ValueError("ineligible_content_ids")
    if not backup:
        items=[i for i in items if at-timedelta(days=7)<=datetime.fromisoformat(i['published'])<=at]
    if not items:
        raise ValueError('no_eligible_content')
    edition={'schema_version':'voices.edition.v1','id':edition_id,'kind':'historical_selection' if backup else 'current',
             'created_at':at.isoformat(),'items':items,'stats':statistics([] if backup else items,at)}
    edition['hash']=digest(edition)
    with store.db() as db:
        db.execute('INSERT INTO editions(id,data,approved,backup) VALUES (?,?,?,?)',
                   (edition_id,json.dumps(edition,ensure_ascii=False),int(automatic),int(backup)))
    return edition


def approve_edition(store,edition_id,expected_hash,reviewer):
    if not reviewer.strip():
        raise ValueError('reviewer_required')
    with store.db() as db:
        row=db.execute('SELECT data FROM editions WHERE id=?',(edition_id,)).fetchone()
        if not row or json.loads(row[0])['hash']!=expected_hash:
            raise ValueError('edition_changed')
        db.execute('UPDATE editions SET approved=1 WHERE id=?',(edition_id,))
    store.event('edition_approved',id=edition_id,reviewer=reviewer,hash=expected_hash)


def publish(store,edition_id,window=None,at=None):
    at=at or datetime.now(UTC)
    with store.db() as db:
        row=db.execute('SELECT * FROM editions WHERE id=?',(edition_id,)).fetchone()
        if not row or not row['approved']:
            raise ValueError('edition_not_approved')
        edition=json.loads(row['data'])
        fingerprint=edition.pop('hash')
        if digest(edition)!=fingerprint:
            raise ValueError('edition_integrity_failed')
        edition['hash']=fingerprint
        revoked=json.loads(db.execute("SELECT value FROM kv WHERE key='withdrawn'").fetchone()[0]) if db.execute("SELECT value FROM kv WHERE key='withdrawn'").fetchone() else []
        if any(i['id'] in revoked for i in edition['items']):
            raise ValueError('edition_contains_withdrawn_content')
        history_row=db.execute("SELECT value FROM kv WHERE key='releases'").fetchone()
        history=json.loads(history_row[0]) if history_row else []
        release={'edition':edition_id,'hash':fingerprint,'published_at':at.isoformat(),'window':window,
                 'delay_seconds':max(0,(at-datetime.fromisoformat(window['at'])).total_seconds()) if window else 0}
        history.append(release)
        for key,value in [('releases',history),('current',release),('delayed',False)]:
            db.execute('INSERT OR REPLACE INTO kv VALUES (?,?)',(key,json.dumps(value)))
        db.execute('UPDATE editions SET used=1 WHERE id=?',(edition_id,))
    store.event('published',**release)
    return release


def withdraw(store,item_id,reason):
    if not reason.strip():
        raise ValueError('reason_required')
    store.set('withdrawn',sorted(set(store.get('withdrawn',[])+[item_id])))
    store.event('withdrawn',id=item_id,reason=reason)


def rollback(store,edition_id):
    if edition_id not in [r['edition'] for r in store.get('releases',[])]:
        raise ValueError('not_previously_released')
    result=publish(store,edition_id)
    store.event('rollback',id=edition_id)
    return result


def snapshot(store,release=None):
    release=release or store.get('current')
    withdrawn=set(store.get('withdrawn',[]))
    if release:
        with store.db() as db:
            row=db.execute('SELECT data,approved FROM editions WHERE id=?',(release['edition'],)).fetchone()
            if not row or not row['approved']:
                raise ValueError('edition_not_approved')
            edition=json.loads(row['data'])
            content={k:v for k,v in edition.items() if k!='hash'}
            if digest(content)!=edition.get('hash') or edition['hash']!=release['hash']:
                raise ValueError('edition_integrity_failed')
        items=[i for i in edition['items'] if i['id'] not in withdrawn]
        at=datetime.fromisoformat(release['published_at'])
    else:
        items=[]
        edition={'id':None,'kind':'awaiting_publication'}
        at=datetime.now(UTC)
    from .schedule import slots
    next_window=next((s for s in slots(at) if datetime.fromisoformat(s['at'])>at),None)
    return {'schema_version':'voices.public.v1','items':items,'as_of':at.isoformat() if release else None,
            'edition':edition['id'],'kind':edition['kind'],'demo':store.get('demo',False),
            'delayed':store.get('delayed',False),'next_update':next_window,
            'stats':statistics([] if edition['kind']!='current' else items,at),
            'archive':[{'edition':r['edition'],'published_at':r['published_at']} for r in store.get('releases',[])],
            'source_health':[{k:e[k] for k in ('source','status','found','at') if k in e}
                             for e in store.metrics()['events'] if e.get('kind')=='collection'],
            'coverage':[{'speaker':s.speaker,'category':s.category,'identity_url':s.identity_url,
                         'verified':s.verified,'rights':s.rights} for s in store.sources().values()]}


def export(store,directory):
    directory=Path(directory)
    if directory.exists():
        raise ValueError('output_must_be_new')
    directory.parent.mkdir(parents=True,exist_ok=True)
    temp=Path(tempfile.mkdtemp(prefix='.voices-build-',dir=directory.parent))
    try:
        assets=files('market_voices').joinpath('assets')
        for name in ('index.html','reader.js','reader.css'):
            (temp/name).write_bytes(assets.joinpath(name).read_bytes())
        def write(name,data):
            (temp/name).write_text(json.dumps(data,ensure_ascii=False,allow_nan=False),encoding='utf-8')
        write('feed.json',snapshot(store))
        archive=temp/'editions'
        archive.mkdir()
        seen=set()
        for release in store.get('releases',[]):
            if release['edition'] in seen:
                continue
            seen.add(release['edition'])
            write('editions/'+release['edition']+'.json',snapshot(store,release))
        (temp/'.nojekyll').touch()
        os.replace(temp,directory)
    except BaseException:
        shutil.rmtree(temp)
        raise
    return directory
