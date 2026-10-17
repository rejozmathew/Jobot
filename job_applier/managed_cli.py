"""Managed subcommands for the existing run_applier.py entry point."""
import argparse
import json
import os
from pathlib import Path
from urllib.parse import urlsplit
from .managed_shared import ProtocolError


def load_config(path):
    path=Path(path)
    if not path.is_absolute():raise ProtocolError('absolute_config_path_required')
    if not path.is_file():raise ProtocolError('config_not_found')
    config=json.loads(path.read_text(encoding='utf-8'))
    required=('db_path','instance_id') if isinstance(config,dict) and config.get('transport')=='local' else ('db_path','instance_id','base_url','operator_token_env')
    if not isinstance(config,dict) or not all(config.get(k) for k in required):raise ProtocolError('invalid_config')
    if not Path(config['db_path']).is_absolute():raise ProtocolError('absolute_db_path_required')
    return config


def credential(name, config=None):
    """Resolve one named secret: launcher environment or explicit private JSON reference.

    Never search for stores, export tokens, or borrow another role's credential.
    Configuration contains only a file path/key; secret contents are never reported.
    """
    if not isinstance(name,str) or not name:raise ProtocolError('credential_unavailable')
    token=os.environ.get(name,'')
    if token:return token
    try:
        reference=(config or {}).get('credential_files',{}).get(name)
        if not isinstance(reference,dict):raise ValueError()
        path=Path(reference['path']);key=reference['key']
        if not path.is_absolute() or not isinstance(key,str) or not key or path.stat().st_size>1048576:
            raise ValueError()
        data=json.loads(path.read_text(encoding='utf-8'))
        token=data[key]
        if not isinstance(token,str) or not token.strip():raise ValueError()
    except (OSError,ValueError,KeyError,TypeError,AttributeError):
        raise ProtocolError('credential_unavailable') from None
    return token


def credential_available(name, config=None):
    try:
        credential(name,config)
        return True
    except ProtocolError:
        return False


def main(argv=None):
    parser=argparse.ArgumentParser(prog='run_applier.py managed',description='Explicit managed-worker operations; no legacy agent or default DB.')
    subs=parser.add_subparsers(dest='command',required=True)
    initialize=subs.add_parser('init',help='create new synthetic review-only instance')
    initialize.add_argument('--db',required=True);initialize.add_argument('--instance-id',required=True)
    preview=subs.add_parser('preview-new',help='inspect target without writing')
    preview.add_argument('--db',required=True)
    for command in ('backup','migrate-copy'):
        sub=subs.add_parser(command)
        sub.add_argument('--source',required=True);sub.add_argument('--destination',required=True);sub.add_argument('--instance-id',required=True)
        if command=='migrate-copy':sub.add_argument('--expected-source-sha256',required=True)
    serve=subs.add_parser('serve',help='authenticated loopback API; no worker spawned')
    serve.add_argument('--config',required=True)
    call=subs.add_parser('call',help='thin authenticated JSON client')
    call.add_argument('--config',required=True);call.add_argument('--operation',required=True)
    call.add_argument('--payload',default='{}');call.add_argument('--token-env')
    call.add_argument('--transport',choices=('local','http'))
    fake=subs.add_parser('fake-worker',help='synthetic protocol exerciser; never contacts portals')
    fake.add_argument('--config',required=True);fake.add_argument('--token-env',required=True)
    fake.add_argument('--run-id',required=True);fake.add_argument('--worker-id',required=True)
    fake.add_argument('--session-id',default='fake-worker');fake.add_argument('--browser-profile',required=True)
    args=parser.parse_args(argv)
    try:
        from .managed import Service
        from .managed_data import preview_new,backup,migrate_copy
        if args.command=='init':result=Service.create(args.db,instance_id=args.instance_id).health()
        elif args.command=='preview-new':result=preview_new(args.db)
        elif args.command=='backup':result=backup(args.source,args.destination,instance_id=args.instance_id)
        elif args.command=='migrate-copy':result=migrate_copy(args.source,args.destination,instance_id=args.instance_id,expected_source_sha256=args.expected_source_sha256)
        else:
            from .managed_client import Client
            config=load_config(args.config)
            service=Service(config['db_path'],instance_id=config['instance_id'])
            service.executor_config=config
            if args.command=='serve':
                token=credential(config['operator_token_env'],config)
                import uvicorn
                from .managed_api import create_app
                # Reuse client's strict URL validation; it performs no network call.
                with Client(config['base_url'],config['instance_id'],token):pass
                workers=json.loads(credential(config['worker_tokens_env'],config))
                app=create_app(service,operator_token=token,worker_tokens=workers)
                parsed=urlsplit(config['base_url'])
                uvicorn.run(app,host=parsed.hostname,port=parsed.port or 8000,access_log=False)
                return 0
            from .managed_client import configured_client
            with configured_client(config,token_name=getattr(args,'token_env',None),transport=getattr(args,'transport',None)) as client:
                if args.command=='call':
                    payload=json.loads(Path(args.payload[1:]).read_text(encoding='utf-8') if args.payload.startswith('@') else args.payload)
                    if not isinstance(payload,dict):raise ProtocolError('invalid_payload')
                    if args.operation in ('intake','queue_enqueue'):payload.setdefault('producer','managed_cli')
                    if args.operation=='queue_enqueue':payload.setdefault('enqueue_origin','api_request')
                    result=client.call(args.operation,**payload)
                else:
                    from .managed_fake_worker import run
                    result=run(client,run_id=args.run_id,worker_id=args.worker_id,session_id=args.session_id,browser_profile=args.browser_profile)
        print(json.dumps(result,ensure_ascii=False))
        return 0
    except ProtocolError as exc:print(json.dumps({'error':exc.code}));return 2
    except FileExistsError:print(json.dumps({'error':'target_exists'}));return 2
    except (OSError,ValueError,KeyError,TypeError):print(json.dumps({'error':'configuration_or_data_error'}));return 2
