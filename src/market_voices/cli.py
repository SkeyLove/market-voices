"""Public CLI: no secret values or raw exceptions are emitted."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

from .contracts import Raw, Source, Summary, digest, issues
from .store import Store


def default_state():
    return Path(os.environ.get('XDG_STATE_HOME',Path.home()/'.local/state'))/'market-voices'


def checkpoint(store):
    target=os.environ.get('MARKET_VOICES_STATE_REPO')
    if not target:
        if os.environ.get('GITHUB_ACTIONS')=='true':
            raise ValueError('private_durable_state_required')
        return
    target=Path(target).resolve()
    if store.directory.resolve()!=target:
        raise ValueError('state_repository_path_mismatch')
    # This repository MUST be private, verified by the deployment workflow.
    commands=[['git','-C',str(target),'add','voices.sqlite3'],
              ['git','-C',str(target),'diff','--cached','--quiet']]
    subprocess.run(commands[0],check=True,capture_output=True)
    changed=subprocess.run(commands[1],capture_output=True)
    if changed.returncode==1:
        subprocess.run(['git','-C',str(target),'commit','-m','Checkpoint production state'],check=True,capture_output=True)
        subprocess.run(['git','-C',str(target),'push','origin','HEAD'],check=True,capture_output=True)
    elif changed.returncode:
        raise ValueError('state_checkpoint_failed')


def main(argv=None):
    parser=argparse.ArgumentParser(description='Market Voices: static bilingual market commentary')
    parser.add_argument('--state',type=Path,default=default_state())
    parser.add_argument('--config',type=Path)
    commands=parser.add_subparsers(dest='command',required=True)
    commands.add_parser('reset-provider');
    commands.add_parser('status');commands.add_parser('collect');commands.add_parser('summarize')
    demo=commands.add_parser('demo');demo.add_argument('--output',type=Path,required=True)
    migrate=commands.add_parser('migrate-inbox');migrate.add_argument('--input',type=Path,required=True)
    migrate=commands.add_parser('migrate-model');migrate.add_argument('--input',type=Path,required=True);migrate.add_argument('--output',type=Path,required=True)
    for name in ('register','ingest','import-summary'):
        command=commands.add_parser(name);command.add_argument('--input',type=Path,required=True)
    video=commands.add_parser('video');video.add_argument('--source',required=True);video.add_argument('--url',required=True);video.add_argument('--published',required=True);video.add_argument('--title',required=True)
    exchange=commands.add_parser('candidates');exchange.add_argument('--output',type=Path,required=True)
    approve=commands.add_parser('approve-content');approve.add_argument('--id',required=True);approve.add_argument('--hash',required=True);approve.add_argument('--reviewer',required=True)
    edition=commands.add_parser('prepare');edition.add_argument('--id',required=True);edition.add_argument('--backup',action='store_true');edition.add_argument('--items',nargs='+')
    approve=commands.add_parser('approve-edition');approve.add_argument('--id',required=True);approve.add_argument('--hash',required=True);approve.add_argument('--reviewer',required=True)
    for name in ('publish','rollback'):
        command=commands.add_parser(name);command.add_argument('--edition',required=True)
    withdraw=commands.add_parser('withdraw');withdraw.add_argument('--id',required=True);withdraw.add_argument('--reason',required=True)
    mode=commands.add_parser('mode');mode.add_argument('value',choices=['auto','manual'])
    export=commands.add_parser('export');export.add_argument('--output',required=True,type=Path)
    window=commands.add_parser('run-window');window.add_argument('--skip-collect',action='store_true')
    commands.add_parser('due')
    evaluate=commands.add_parser('evaluate');evaluate.add_argument('--input',type=Path,required=True)
    args=parser.parse_args(argv)
    if args.config:
        os.environ['MARKET_VOICES_CONFIG']=str(args.config.resolve())
    try:
        from .publication import prepare,approve_edition,publish,rollback,withdraw,export
        from .provider import process
        from .collect import collect,video as collect_video
        from .schedule import tick,due
        if args.command=='due':
            print(json.dumps(due()));return 0
        if args.command=='evaluate':
            from .evaluation import evaluate
            print(json.dumps(evaluate(json.loads(args.input.read_text())),ensure_ascii=False));return 0
        store=Store(args.state)
        if args.command=='demo':
            if store.records() or store.get('current'):
                raise ValueError('demo_requires_empty_state')
            from .demo import initialize
            initialize(store);export(store,args.output)
            result={'status':'demo_built','output':str(args.output)}
        elif args.command=='migrate-inbox':
            from .migrate import inbox
            result=inbox(store,args.input)
        elif args.command=='migrate-model':
            from .migrate import model
            result=model(args.input,args.output)
        elif args.command in ('register','ingest','import-summary'):
            data=json.loads(args.input.read_text())
            rows=data if isinstance(data,list) else [data]
            for row in rows:
                if args.command=='register':
                    store.register(Source.model_validate(row))
                elif args.command=='ingest':
                    raw=Raw.model_validate(row)
                    if raw.source_id not in store.sources():
                        raise ValueError('unregistered_source')
                    store.ingest(raw)
                else:
                    key=row['id']; summary=Summary.model_validate(row['summary'])
                    records={k:(r,s) for k,r,s,_,_ in store.records()}
                    raw,_=records[key]
                    errors=issues(raw,summary,store.sources()[raw.source_id])
                    if errors:
                        raise ValueError('summary_validation_failed')
                    store.save_summary(key,summary)
            result={'imported':len(rows)}
        elif args.command=='collect':
            result=collect(store)
        elif args.command=='video':
            result={'id':collect_video(store,args.source,args.url,args.published,args.title)}
        elif args.command=='summarize':
            result=process(store,checkpoint=lambda:checkpoint(store))
        elif args.command=='candidates':
            rows=[{'id':k,'input_hash':r.fingerprint,'raw':r.model_dump(mode='json'),'summary':s.model_dump(mode='json') if s else None,
                   'summary_hash':digest(s.model_dump(mode='json')) if s else None,
                   'source':store.sources()[r.source_id].model_dump(),
                   'validation':issues(r,s,store.sources()[r.source_id]) if s else ['not_summarized']}
                  for k,r,s,_,_ in store.records()]
            if args.output.exists():
                raise ValueError('output_must_be_new')
            fd=os.open(args.output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'w') as f:
                json.dump(rows,f,ensure_ascii=False,indent=2)
            result={'candidates':len(rows),'private_file':True}
        elif args.command=='approve-content':
            row=next((row for row in store.records() if row[0]==args.id),None)
            if not row or not row[2] or issues(row[1],row[2],store.sources()[row[1].source_id]):
                raise ValueError('content_not_eligible')
            store.approve(args.id,args.hash,args.reviewer);result={'approved':args.id}
        elif args.command=='prepare':
            result=prepare(store,args.id,backup=args.backup,ids=args.items)
            result={'id':result['id'],'hash':result['hash'],'count':len(result['items'])}
        elif args.command=='approve-edition':
            approve_edition(store,args.id,args.hash,args.reviewer);result={'approved':args.id}
        elif args.command=='publish':
            result=publish(store,args.edition)
        elif args.command=='rollback':
            result=rollback(store,args.edition)
        elif args.command=='withdraw':
            withdraw(store,args.id,args.reason);result={'withdrawn':args.id}
        elif args.command=='reset-provider':
            store.set('provider_blocked',None);store.event('provider_reset',reason='operator');result={'provider_blocked':False}
        elif args.command=='mode':
            store.set('mode',args.value);store.event('mode_changed',mode=args.value,reason='operator');result={'mode':args.value}
        elif args.command=='export':
            export(store,args.output);result={'output':str(args.output)}
        elif args.command=='run-window':
            if os.environ.get('GITHUB_ACTIONS')=='true' and store.get('demo',False):
                raise ValueError('demo_state_not_for_production')
            def produce():
                if not args.skip_collect:
                    collect(store)
                return process(store,checkpoint=lambda:checkpoint(store))
            result=tick(store,produce,checkpoint=lambda:checkpoint(store))
        else:
            with store.db() as db:
                reserve=db.execute('SELECT COUNT(*) FROM editions WHERE approved=1 AND backup=1 AND used=0').fetchone()[0]
            result={'mode':store.get('mode','auto'),'demo':store.get('demo',False),'backup_editions':reserve,
                    'backup_pool_ready':reserve>=6,'current':store.get('current'),'metrics':store.metrics()}
        print(json.dumps(result,ensure_ascii=False,default=str))
        return 0
    except Exception as exc:
        # Remote payloads, local files and validation messages may contain secrets.
        safe={'budget_exhausted','missing_api_key','verified_rates_required','price_snapshot_expired',
              'output_must_be_new','no_eligible_content','content_not_eligible','summary_changed',
              'edition_not_approved','unregistered_source','demo_requires_empty_state',
              'private_durable_state_required','demo_state_not_for_production'}
        code=str(exc) if type(exc) is ValueError and str(exc) in safe else type(exc).__name__
        print(json.dumps({'error':code}));return 1


if __name__=='__main__':
    raise SystemExit(main())
