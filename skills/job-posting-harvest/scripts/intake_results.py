"""Bounded discovery handoff into shared intake. No eligibility or execution authority."""
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
                  'namespace','requisition_id','identity_evidence'})


def publish(client, records, *, dry_run=False):
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
                row=client.call('intake',**data)
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
    parser.add_argument('--dry-run',action='store_true');args=parser.parse_args(argv)
    from job_applier.managed_cli import load_config
    from job_applier.managed_client import Client
    try:
        records=json.loads(Path(args.input).read_text(encoding='utf-8'))
        cfg=load_config(args.config)
        if args.dry_run:result=publish(None,records,dry_run=True)
        else:
            token=os.environ.get(cfg['operator_token_env'],'')
            if not token:raise ProtocolError('credential_unavailable')
            client=Client(base_url=cfg['base_url'],instance_id=cfg['instance_id'],token=token)
            try:result=publish(client,records)
            finally:client.close()
        print(json.dumps(result,sort_keys=True))
        return 1 if result['failed'] else 0
    except (OSError,ValueError,KeyError):
        print(json.dumps({'error':'handoff_unavailable'}));return 2


if __name__=='__main__':raise SystemExit(main())
