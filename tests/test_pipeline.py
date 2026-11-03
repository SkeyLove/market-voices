from datetime import UTC,datetime,timedelta
import json
from pathlib import Path
import sqlite3
import pytest
from market_voices.contracts import Raw,Source,Summary,digest,issues
from market_voices.store import Store
from market_voices.publication import prepare,approve_edition,publish,export,snapshot,statistics,withdraw,rollback,eligible
from market_voices.schedule import slots,due,tick

AT=datetime(2026,11,3,14,tzinfo=UTC)

@pytest.fixture(autouse=True)
def freeze_validation_clock(monkeypatch):
    import market_voices.contracts as contracts
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):
            return AT if tz else AT.replace(tzinfo=None)
    monkeypatch.setattr(contracts,'datetime',Clock)


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path/'private')


def content(store,index=0,stance='bullish',group='g',when=AT-timedelta(hours=1),category='creator',approved=True):
    source=Source(id='s'+str(index),speaker_id='person'+str(index),speaker='Person '+str(index),group=group,
                  category=category,identity_url='https://example.com/person',verified=True,rights='summary_link_only')
    store.register(source)
    raw=Raw(source_id=source.id,url=f'https://example.com/post/{index}',title='Title',published=when,
            text='The source explicitly says this stock looks attractively valued today.',evidence='full_text',locator='paragraph 1')
    key=store.ingest(raw)
    summary=Summary(title_zh='中文标题',title_en='English title',summary_zh='这是一条对应原文的中文摘要。',summary_en='An English source summary.',
                    speaker_id=source.speaker_id,ticker='' if category=='official' else 'NVDA',stance=stance,
                    quote=raw.text,input_hash=raw.fingerprint,method='skill',producer='test',
                    conditions_zh='如果条件满足' if stance=='conditional' else '',conditions_en='If conditions hold' if stance=='conditional' else '')
    store.save_summary(key,summary)
    if approved:
        store.approve(key,digest(summary.model_dump(mode='json')),'test-reviewer')
    return key,raw,summary,source


def test_unapproved_never_visible(store):
    content(store,approved=False)
    assert not snapshot(store)['items']
    with pytest.raises(ValueError):prepare(store,'edition')
    edition=prepare(store,'candidate',automatic=True,at=AT)
    assert len(edition['items'])==1


def test_double_approval_and_edits(store):
    key,raw,summary,_=content(store)
    e=prepare(store,'edition',at=AT)
    with pytest.raises(ValueError):publish(store,'edition',at=AT)
    with pytest.raises(ValueError):approve_edition(store,'edition','wrong','human')
    approve_edition(store,'edition',e['hash'],'human')
    publish(store,'edition',at=AT)
    assert len(snapshot(store)['items'])==1
    store.save_summary(key,summary.model_copy(update={'summary_zh':'修改后必须重新审核'}))
    assert not eligible(store)
    with pytest.raises(ValueError):store.approve(key,digest(summary.model_dump(mode='json')),'human')


def test_changed_source_invalidates_summary_but_fetch_time_does_not(store):
    _,raw,_,_=content(store)
    store.ingest(raw.model_copy(update={'collected':raw.collected+timedelta(hours=2)}))
    assert len(eligible(store))==1
    store.ingest(raw.model_copy(update={'text':'Changed original source.'}))
    assert not eligible(store)


def test_latest_group_condition_suppresses_older_vote(store):
    content(store,index=1,when=AT-timedelta(hours=3))
    content(store,index=2,stance='conditional',when=AT-timedelta(hours=2))
    rows=eligible(store)
    assert statistics(rows,AT)['opinions']==0
    content(store,index=3,group='independent',stance='bearish')
    stats=statistics(eligible(store),AT)
    assert stats['counts']=={'bullish':0,'neutral':0,'bearish':1}


def test_same_time_conflict_and_official_historical(store):
    content(store,index=1)
    content(store,index=2,stance='bearish')
    content(store,index=3,category='official',group='gov')
    content(store,index=4,group='old',when=AT-timedelta(days=9))
    assert statistics(eligible(store),AT)['opinions']==0


def test_withdraw_removes_from_archives_and_blocks_rollback(store,tmp_path):
    key,*_=content(store)
    e=prepare(store,'one',at=AT);approve_edition(store,'one',e['hash'],'human');publish(store,'one',at=AT)
    withdraw(store,key,'incorrect attribution')
    assert not snapshot(store)['items']
    with pytest.raises(ValueError):rollback(store,'one')
    export(store,tmp_path/'site')
    assert not json.loads((tmp_path/'site/editions/one.json').read_text())['items']


def test_atomic_whitelist_export_and_immutable_original(store,tmp_path):
    content(store)
    e=prepare(store,'one',at=AT);approve_edition(store,'one',e['hash'],'human');publish(store,'one',at=AT)
    out=tmp_path/'site';export(store,out)
    assert (out/'reader.js').exists()
    payload=(out/'feed.json').read_text()
    assert 'api_key' not in payload and 'raw' not in json.loads(payload)
    assert 'The source explicitly' in payload  # only approved quote, not raw field
    with pytest.raises(ValueError):export(store,out)
    with store.db() as db:
        edition=json.loads(db.execute('SELECT data FROM editions WHERE id="one"').fetchone()[0]);edition['items'][0]['summary_zh']='tampered'
        db.execute('UPDATE editions SET data=? WHERE id="one"',(json.dumps(edition),))
    with pytest.raises(ValueError):publish(store,'one')


def test_budget_conservative_reservation_and_settlement(store):
    store.reserve('a','2026-11',20,30)
    with pytest.raises(ValueError):store.reserve('b','2026-11',11,30)
    store.settle('a',1)
    store.reserve('b','2026-11',20,30)
    # Unknown charge stays at its reservation even after reopening.
    assert Store(store.directory).metrics()['budget'][0]['charged_cny']==21
    with pytest.raises(ValueError):store.settle('b',25)


def test_calendar_holidays_early_close_dst():
    windows={s['id']:datetime.fromisoformat(s['at']) for s in slots(datetime(2026,11,25,tzinfo=UTC))}
    assert not any(k.startswith('2026-11-26') for k in windows)
    assert windows['2026-11-27-post'].hour==19
    assert windows['2026-11-25-pre'].hour==13
    summer={s['id']:datetime.fromisoformat(s['at']) for s in slots(datetime(2026,7,8,tzinfo=UTC))}
    assert summer['2026-07-08-pre'].hour==12
    assert due(datetime(2026,11,3,13,40,tzinfo=UTC))['id']=='2026-11-03-pre'


def test_mode_trip_backup_and_dedup(store):
    content(store,when=AT-timedelta(days=20))
    for i in range(3):
        e=prepare(store,f'backup-{i}',backup=True,at=AT)
        approve_edition(store,e['id'],e['hash'],'human')
    for day in (3,4,5):
        at=datetime(2026,11,day,13,40,tzinfo=UTC)
        result=tick(store,lambda:None,at=at)
        assert result['status']=='backup_or_approved'
        assert tick(store,lambda:pytest.fail('duplicate ran'),at=at)['status']=='already_attempted'
    assert store.get('mode')=='manual'
    assert snapshot(store)['kind']=='historical_selection'
    assert snapshot(store)['stats']['opinions']==0
    tick(store,lambda:None,at=datetime(2026,11,6,13,40,tzinfo=UTC))
    assert snapshot(store)['delayed']
    assert snapshot(store)['edition']=='backup-2'


def test_auto_publishes_once_and_manual_does_not_take_new_content(store):
    content(store,approved=False)
    result=tick(store,lambda:None,at=datetime(2026,11,3,13,40,tzinfo=UTC))
    assert result['status']=='published'
    previous=store.get('current')
    store.set('mode','manual')
    content(store,index=2,group='new',approved=False)
    tick(store,lambda:None,at=datetime(2026,11,3,22,5,tzinfo=UTC))
    assert store.get('current')==previous
    assert store.get('delayed')


def test_no_human_evaluation_is_fabricated():
    from market_voices.evaluation import evaluate
    report=evaluate([{'label_origin':'synthetic','checks':{'speaker':True}}])
    assert report['dimensions']['speaker']['rate'] is None


def test_snapshot_detects_tampered_published_edition(store):
    content(store)
    e=prepare(store,'one',at=AT);approve_edition(store,'one',e['hash'],'human');publish(store,'one',at=AT)
    with store.db() as db:
        value=json.loads(db.execute('SELECT data FROM editions WHERE id="one"').fetchone()[0])
        value['items'][0]['summary_en']='Changed after approval'
        db.execute('UPDATE editions SET data=? WHERE id="one"',(json.dumps(value),))
    with pytest.raises(ValueError,match='integrity'):
        snapshot(store)
