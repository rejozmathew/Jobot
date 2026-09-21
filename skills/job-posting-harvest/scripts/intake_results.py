"""Discovery intake; optional explicitly requested enqueue into the local dispatcher."""
import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from job_applier.managed_identity import canonical_url, job_key
from job_applier.managed_redaction import reject_secrets
from job_applier.managed_shared import ProtocolError

FIELDS=frozenset({'url','company','title','location','verdict','source_type','source_id',
                  'namespace','requisition_id','identity_evidence','country','posted_at'})


def publish(client, records, *, dry_run=False, provenance=None):
    if not isinstance(records,list) or type(dry_run) is not bool:
        raise ProtocolError('invalid_handoff')
    results=[]; canonical=set(); failed=0
    for index,record in enumerate(records):
        try:
            if not isinstance(record,dict):raise ProtocolError('invalid_record')
            data={key:value for key,value in record.items() if key in FIELDS}
            for key in ('url','source_type','source_id'):
                if not isinstance(data.get(key),str) or not data[key].strip():
                    raise ProtocolError('invalid_'+key)
            for key,value in data.items():
                if not isinstance(value,str):raise ProtocolError('invalid_'+key)
            normalized=canonical_url(data['url'])
            reject_secrets({k:v for k,v in data.items() if k!='url'})
            if dry_run:
                # Preview groups supplied identities; it makes no claim about existing DB rows.
                strong=bool(data.get('namespace') and data.get('requisition_id') and data.get('identity_evidence'))
                key=job_key(normalized,data.get('namespace') if strong else None,
                            data.get('requisition_id') if strong else None)
                canonical.add(key)
                results.append({'index':index,'status':'preview','dry_run':True})
            else:
                row=client.call('intake',**data,**(provenance or {}))
                canonical.add(row['id'])
                results.append({'index':index,'status':'ok','job_id':row['id'],
                                'job_status':row['status']})
        except ProtocolError as exc:
            failed+=1;results.append({'index':index,'status':'error','error':exc.code})
        except (TypeError,ValueError,KeyError):
            failed+=1;results.append({'index':index,'status':'error','error':'invalid_record'})
    return {'received':len(records),'canonical_jobs':len(canonical),'results':results,'failed':failed}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',required=True);parser.add_argument('--input',required=True)
    parser.add_argument('--dry-run',action='store_true')
    parser.add_argument('--enqueue',action='store_true',help='queue only Strong apply / Apply verdicts, not caveats or skipped jobs')
    parser.add_argument('--producer',default='discovery_intake',help='process supplying this batch')
    parser.add_argument('--discovery-run-id');parser.add_argument('--discovery-profile')
    args=parser.parse_args(argv)
    from job_applier.managed_cli import load_config
    from job_applier.managed_client import configured_client
    try:
        records=json.loads(Path(args.input).read_text(encoding='utf-8'))
        cfg=load_config(args.config)
        provenance={k:v for k,v in {'producer':args.producer,'discovery_run_id':args.discovery_run_id,
                                   'discovery_profile':args.discovery_profile}.items() if v}
        if args.dry_run:result=publish(None,records,dry_run=True)
        else:
            with configured_client(cfg) as client:
                result=publish(client,records,provenance=provenance)
                if args.enqueue:
                    result['enqueue']=[]
                    for item in result['results']:
                        if item['status']!='ok' or records[item['index']].get('verdict','').strip().casefold() not in ('strong apply','apply'):continue
                        try:
                            queued=client.call('queue_enqueue',job_ids=[item['job_id']],identity_id=cfg['identity_id'],
                                resume_asset_id=cfg['resume_asset_id'],request_id='harvest:'+item['job_id'],
                                enqueue_origin='discovery',**provenance)
                            result['enqueue'].append({'job_id':item['job_id'],'state':queued['items'][0]['state']})
                        except ProtocolError as exc:
                            result['enqueue'].append({'job_id':item['job_id'],'error':exc.code})
                            if exc.code!='already_applied':result['failed']+=1
        print(json.dumps(result,sort_keys=True))
        return 1 if result['failed'] else 0
    except (OSError,ValueError,KeyError,ProtocolError):
        print(json.dumps({'error':'handoff_unavailable'}));return 2


if __name__=='__main__':raise SystemExit(main())
