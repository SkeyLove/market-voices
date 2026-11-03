"""Exchange-calendar windows. The caller supplies serialized durable state."""
from datetime import UTC, datetime, timedelta
import json
import exchange_calendars as xc


def slots(at=None):
    at=at or datetime.now(UTC)
    schedule=xc.get_calendar('XNYS').schedule.loc[(at-timedelta(days=7)).date().isoformat():(at+timedelta(days=14)).date().isoformat()]
    return [{'id':f'{day.date()}-{kind}','kind':kind,'at':time.isoformat()}
            for day,row in schedule.iterrows()
            for kind,time in [('pre',row['open']-timedelta(hours=1)),('post',row['close']+timedelta(hours=1))]]


def due(at=None):
    at=at or datetime.now(UTC)
    candidates=[s for s in slots(at) if timedelta(0)<=at-datetime.fromisoformat(s['at'])<timedelta(hours=2)]
    return candidates[-1] if candidates else None


def tick(store,produce,checkpoint=lambda:None,at=None):
    from .publication import eligible,prepare,publish
    at=at or datetime.now(UTC)
    slot=due(at)
    if slot is None:
        return {'status':'not_due'}
    with store.db() as db:
        if db.execute('SELECT 1 FROM windows WHERE id=?',(slot['id'],)).fetchone():
            return {'status':'already_attempted','window':slot['id']}
        db.execute('INSERT INTO windows VALUES (?,?,?)',(slot['id'],'running',json.dumps(slot)))
    checkpoint()
    failure=None
    try:
        produce()
    except Exception:
        failure='production_failed'
    automatic=store.get('mode','auto')=='auto'
    items=eligible(store,automatic=automatic)
    recent=[i for i in items if at-timedelta(days=7)<=datetime.fromisoformat(i['published'])<=at]
    previous=set(store.get('published_summaries',[]))
    fresh=[i for i in recent if i['summary_hash'] not in previous]
    if automatic and fresh and not failure:
        try:
            edition=prepare(store,slot['id'],automatic=True,at=at)
            result=publish(store,edition['id'],slot,at)
            store.set('published_summaries',sorted(previous|{i['summary_hash'] for i in recent}))
            store.set('failed_windows',0)
            outcome='published'
        except ValueError:
            failure='publication_failed'
            outcome='delayed'
    else:
        outcome='delayed'
    if outcome!='published':
        misses=store.get('failed_windows',0)+1
        store.set('failed_windows',misses)
        if misses>=3 and automatic:
            store.set('mode','manual')
            store.event('mode_changed',mode='manual',reason='three_failed_windows')
        # Operator-approved current editions may be queued ahead of the window.
        with store.db() as db:
            row=db.execute('SELECT id FROM editions WHERE approved=1 AND used=0 ORDER BY backup ASC,rowid ASC LIMIT 1').fetchone()
        if row:
            try:
                result=publish(store,row['id'],slot,at)
                outcome='backup_or_approved'
            except ValueError:
                store.set('delayed',True)
        else:
            store.set('delayed',True)
    record={'window':slot['id'],'status':outcome,'error':failure,
            'mode':store.get('mode','auto'),'delay_seconds':(at-datetime.fromisoformat(slot['at'])).total_seconds()}
    with store.db() as db:
        db.execute('UPDATE windows SET status=?,data=? WHERE id=?',(outcome,json.dumps(record),slot['id']))
    store.event('window_finished',**record)
    checkpoint()
    return record
