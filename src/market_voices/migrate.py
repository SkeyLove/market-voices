"""Explicit, local-only migration from the earlier inbox. No implicit credential scan."""
import json
import os
import sqlite3
from pathlib import Path
from datetime import UTC,datetime
from .contracts import Raw,Source,Summary,digest


def model(source,destination):
    destination=Path(destination)
    if destination.exists():
        raise ValueError('output_must_be_new')
    data=json.loads(Path(source).read_text())
    if not isinstance(data,dict):
        raise ValueError('invalid_model_config')
    cleaned={k:data[k] for k in ('provider','base_url','model','api_key') if k in data}
    destination.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd=os.open(destination,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as f:
        json.dump(cleaned,f,indent=2)
    return {'migrated':True,'rates_required':True}


def inbox(store,path):
    connection=sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True)
    count=skipped=0
    try:
        for row in connection.execute('SELECT data FROM items'):
            item=json.loads(row[0]); reader=item.get('reader',{})
            if not item.get('text') or not item.get('published'):
                skipped+=1;continue
            speaker=reader.get('speaker') or item.get('speaker') or item.get('source') or 'Unverified speaker'
            identity=digest(speaker.casefold().strip())[:16]
            source_id='legacy-'+identity
            source=Source(id=source_id,speaker_id='person-'+identity,speaker=speaker,group='group-'+identity,
                category=item.get('category','creator'),platform=item.get('platform','official'),
                identity_url=item['url'],verified=False,rights='pending')
            store.register(source)
            try:
                raw=Raw(source_id=source_id,url=item['url'],title=item['title'],published=item['published'],
                    collected=item.get('collected') or datetime.now(UTC).isoformat(),text=item['text'],
                    evidence=item.get('evidence') if item.get('evidence') in ('full_text','transcript','official_text','summary_only','unavailable') else 'feed_excerpt',
                    locator=item.get('locator') or ('timestamped transcript' if item.get('evidence')=='transcript' else ''))
                key=store.ingest(raw)
                if reader:
                    summary=Summary(**{k:reader[k] for k in ('title_zh','title_en','summary_zh','summary_en','stance','ticker','horizon','quote') if k in reader},
                        speaker_id=source.speaker_id,input_hash=raw.fingerprint,method='skill' if reader.get('method')=='agent_assisted' else 'api',
                        producer=reader.get('model','legacy-unverified'))
                    store.save_summary(key,summary)
                count+=1
            except ValueError:
                skipped+=1
    finally:
        connection.close()
    return {'migrated':count,'skipped':skipped,'approved':0,'source_verification_required':True}
