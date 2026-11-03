"""Fictional, deterministic examples. No real-market performance claims."""
from datetime import UTC, datetime, timedelta
from .contracts import Source, Raw, Summary, digest
from .publication import prepare, approve_edition, publish


def initialize(store,at=None):
    at=at or datetime.now(UTC)
    store.set('demo',True)
    sources=[]
    for index,category in enumerate(('creator','institution','official')):
        source=Source(id=f'demo-{index}',speaker_id=f'person-{index}',speaker=f'Demo Speaker {index+1}',
            group=f'group-{index}',category=category,identity_url=f'https://example.com/people/{index}',
            verified=True,rights='summary_link_only')
        store.register(source);sources.append(source)
    keys=[]
    for index in range(30):
        source=sources[index%3]
        text=f'This is fictional example {index}. We expect returns to depend on future cash flows and the price paid.'
        raw=Raw(source_id=source.id,url=f'https://example.com/opinions/{index}',title=f'Fictional example {index}',
                published=at-timedelta(hours=index+1),text=text,evidence='full_text',locator='Paragraph 1')
        key=store.ingest(raw)
        stance=('bullish','bearish','neutral','conditional','unclear')[index%5]
        summary=Summary(title_zh=f'合成观点示例 {index+1}',title_en=f'Synthetic perspective {index+1}',
            summary_zh='这是一条虚构的演示观点，用于测试来源追溯和双语发布，不代表实际投资判断。',
            summary_en='A fictional demonstration of traceable bilingual publishing, not an actual investment opinion.',
            speaker_id=source.speaker_id,ticker='' if source.category=='official' else ('NVDA' if index%2 else 'AMZN'),
            stance=stance,quote=text,horizon='unspecified',conditions_zh='仅用于测试' if stance=='conditional' else '',
            conditions_en='For testing only' if stance=='conditional' else '',
            input_hash=raw.fingerprint,method='demo',producer='offline-demo.v1')
        store.save_summary(key,summary)
        store.approve(key,digest(summary.model_dump(mode='json')),'demo-fixture')
        keys.append(key)
    for index in range(6):
        edition=prepare(store,f'demo-reserve-{index+1}',backup=True,at=at,ids=keys[index*5:index*5+5])
        approve_edition(store,edition['id'],edition['hash'],'demo-fixture')
    edition=prepare(store,'demo-current',at=at)
    approve_edition(store,edition['id'],edition['hash'],'demo-fixture')
    publish(store,edition['id'],at=at)
