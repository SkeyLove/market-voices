from datetime import UTC,datetime
import json
from pathlib import Path
import pytest
from market_voices.config import settings,path
from market_voices.collect import parse_feed
from market_voices.contracts import Raw,Source,Summary,issues,digest
from market_voices.store import Store
from market_voices.provider import infer,ProviderError


def fixture_record(store):
    source=Source(id='a',speaker_id='person',speaker='Person',group='group',category='creator',identity_url='https://example.com/person',verified=True,rights='summary_link_only')
    store.register(source)
    raw=Raw(source_id='a',url='https://example.com/talk',title='Original',published='2025-01-01T00:00:00Z',text='This stock is priced below my estimate of its intrinsic value.',evidence='full_text',locator='paragraph 2')
    store.ingest(raw)
    return raw,source


@pytest.fixture
def context(tmp_path,monkeypatch):
    config=tmp_path/'config.json'
    config.write_text(json.dumps({'api_key':'NEVER_LOG_THIS_SECRET','rates':{'input_per_million':.3,'output_per_million':1.2,'currency_to_cny':8,'verified_on':datetime.now(UTC).date().isoformat()},'allowed_tickers':['NVDA']}))
    monkeypatch.setenv('MARKET_VOICES_CONFIG',str(config))
    store=Store(tmp_path/'state')
    raw,source=fixture_record(store)
    return store,raw,source


def valid_result(raw,source):
    return {'title_zh':'价值判断','title_en':'Valuation view','summary_zh':'发言人认为股价低于内在价值。','summary_en':'The speaker considers the stock below intrinsic value.','speaker_id':source.speaker_id,'ticker':'NVDA','stance':'bullish','horizon':'unspecified','quote':raw.text}


def test_pre_request_checkpoint_and_usage_settlement(context):
    store,raw,source=context
    events=[]
    def checkpoint():
        assert store.metrics()['budget'][0]['requests']==1
        events.append('checkpoint')
    def post(endpoint,headers,body,timeout,local):
        assert events==['checkpoint']
        assert body['thinking']=={'type':'disabled'}
        assert headers['Authorization'].endswith('NEVER_LOG_THIS_SECRET')
        return 200,{'choices':[{'message':{'content':json.dumps(valid_result(raw,source))},'finish_reason':'stop'}],
                    'usage':{'prompt_tokens':100,'completion_tokens':200}}
    summary=infer(store,raw,source,checkpoint,post)
    assert summary.method=='api' and not issues(raw,summary,source)
    assert len(events)==2
    assert store.metrics()['budget'][0]['charged_cny']==pytest.approx(.00216)


def test_budget_failure_prevents_network(context):
    store,raw,source=context
    store.reserve('occupied',datetime.now(UTC).strftime('%Y-%m'),30,30)
    with pytest.raises(ValueError,match='budget_exhausted'):
        infer(store,raw,source,post=lambda *a,**k:pytest.fail('paid call despite cap'))


def test_unknown_transport_charge_not_released(context):
    store,raw,source=context
    def failed(*a,**kw):raise TimeoutError('NEVER_LOG_THIS_SECRET')
    with pytest.raises(ProviderError,match='transport_unknown_charge'):
        infer(store,raw,source,post=failed)
    with store.db() as db:
        row=db.execute('SELECT * FROM budget').fetchone()
    assert row['actual'] is None and row['reserved']>0
    assert 'NEVER_LOG' not in str(store.metrics())


@pytest.mark.parametrize('status,retry',[(401,False),(402,False),(429,True),(500,True)])
def test_http_retry_policy_is_bounded(context,status,retry):
    store,raw,source=context
    with pytest.raises(ProviderError) as caught:
        infer(store,raw,source,post=lambda *a,**kw:(status,{'error':'NEVER_LOG_THIS_SECRET'}))
    assert caught.value.retry==retry
    assert 'NEVER_LOG' not in str(caught.value)


def test_fabricated_quote_and_unregistered_ticker_rejected(context):
    store,raw,source=context
    result=valid_result(raw,source);result['quote']='An invented quotation that is definitely not in the source.'
    def post(*a,**kw):return 200,{'choices':[{'message':{'content':json.dumps(result)}}]}
    with pytest.raises(ProviderError,match='validation'):
        infer(store,raw,source,post=post)
    result['quote']=raw.text;result['ticker']='NOTREAL'
    with pytest.raises(ProviderError,match='ticker_not_confirmed'):
        infer(store,raw,source,post=post)


def test_feed_full_text_and_excerpt_and_xml_entities(context):
    _,_,source=context
    atom='<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Talk</title><link href="https://example.com/a"/><published>2025-01-01T12:00:00Z</published><content>&lt;p&gt;Original text.&lt;/p&gt;</content></entry></feed>'
    record=parse_feed(atom,source)[0]
    assert record.text=='Original text.' and record.evidence=='full_text'
    assert parse_feed(atom.replace('content','summary'),source)[0].evidence=='feed_excerpt'
    with pytest.raises(Exception):parse_feed('<!DOCTYPE x [<!ENTITY a "expanded">]><rss>&a;</rss>',source)


def test_config_no_secret_in_exception(tmp_path,monkeypatch):
    p=tmp_path/'bad.json';p.write_text('{"api_key": "NEVER_LOG_THIS_SECRET", "unexpected":42}')
    monkeypatch.setenv('MARKET_VOICES_CONFIG',str(p))
    with pytest.raises(ValueError) as exc:settings()
    assert 'NEVER_LOG' not in str(exc.value)


def test_repeat_collection_does_not_regenerate(context):
    store,raw,source=context
    initial=raw.fingerprint
    store.ingest(raw.model_copy(update={'collected':datetime.now(UTC)}))
    assert store.records()[0][1].fingerprint==initial


def test_permanent_auth_failure_blocks_next_window(context,monkeypatch):
    import market_voices.provider as mod
    store,raw,source=context
    calls=[]
    def failed(*args,**kwargs):
        calls.append(1)
        raise ProviderError('model_http_401',retry=False)
    monkeypatch.setattr(mod,'infer',failed)
    first=mod.process(store)
    second=mod.process(store)
    assert first['provider_blocked'] and second['provider_blocked']
    assert len(calls)==1


def test_two_failures_maximum_per_input_across_windows(context,monkeypatch):
    import market_voices.provider as mod
    store,raw,source=context
    calls=[]
    def failed(*args,**kwargs):
        calls.append(1)
        raise ProviderError('model_http_500',retry=True)
    monkeypatch.setattr(mod,'infer',failed)
    mod.process(store);mod.process(store)
    assert len(calls)==2


def test_expired_prices_prevent_inference(context,monkeypatch):
    store,raw,source=context
    import os
    p=Path(os.environ['MARKET_VOICES_CONFIG'])
    config=json.loads(p.read_text());config['rates']['verified_on']='2020-01-01';p.write_text(json.dumps(config))
    with pytest.raises(ProviderError,match='expired'):
        infer(store,raw,source,post=lambda *a,**k:pytest.fail('expired-rate call'))


def test_migrate_model_never_overwrites_and_is_private(tmp_path):
    import stat
    from market_voices.migrate import model
    old=tmp_path/'old.json';new=tmp_path/'new.json'
    old.write_text(json.dumps({'provider':'deepseek','api_key':'private-key'}))
    model(old,new)
    assert stat.S_IMODE(new.stat().st_mode)==0o600
    with pytest.raises(ValueError):model(old,new)
    assert json.loads(old.read_text())['api_key']=='private-key'
