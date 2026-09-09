"""Use the installed Hermes Gmail skill with the configured mailbox credential."""
import argparse
import importlib.util
from datetime import datetime,timezone
from email.utils import getaddresses,parsedate_to_datetime
import html
import json
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import urlsplit


def mailbox_handoff(config):
    """Expose the configured invocation, never credential content or mail bodies."""
    script=config.get('gmail_script');token=config.get('mailbox_token_path')
    available=bool(script and token and Path(script).is_file() and Path(token).is_file())
    return {'available':available,'wrapper_argv':[sys.executable,'-m','job_applier.hermes_gmail',
        '--script',script,'--token-file',token,'gmail'] if available else [],
        'instruction':'Use credentials mode verification for a correlated private email code. Finish form corrections, request a fresh code after an interruption, then fill and submit promptly.' if available else
        'Configured mailbox is unavailable. Inspect the actual challenge and available recovery.'}


def _gmail_json(config,*args):
    """Keep all wrapper output inside this private call, including transport errors."""
    if not mailbox_handoff(config)['available']:raise ValueError('configured_mailbox_unavailable')
    try:
        result=subprocess.run([sys.executable,'-m','job_applier.hermes_gmail','--script',config['gmail_script'],
            '--token-file',config['mailbox_token_path'],'gmail',*args],capture_output=True,text=True,encoding='utf-8',timeout=45)
        if result.returncode:raise ValueError('mailbox_read_failed')
        if result.stdout.strip()=='No messages found.':return []
        return json.loads(result.stdout)
    except (OSError,subprocess.SubprocessError,json.JSONDecodeError):raise ValueError('mailbox_read_failed') from None


def verification_value(config,package,challenge,*,now=None):
    """PRIVATE result: caller may return timing/message identity, never `value`."""
    try:
        requested=datetime.fromisoformat(challenge['requested_at'].replace('Z','+00:00'))
        now=now or datetime.now(timezone.utc)
        if requested.tzinfo is None or requested>now:raise ValueError()
        length=challenge['length']
        if type(length) is not int or not 4<=length<=12:raise ValueError()
    except (KeyError,TypeError,ValueError):raise ValueError('observed_verification_request_required') from None
    profile=package['attempt'].get('profile_json') or {}
    if isinstance(profile,str):profile=json.loads(profile)
    recipient=profile.get('identity',{}).get('email','').casefold()
    if not recipient:raise ValueError('configured_mailbox_identity_unavailable')
    job=package['job'];platform=package.get('platform')
    host=urlsplit(job['url']).hostname or ''
    domain='greenhouse.io' if platform=='greenhouse' or host.endswith('.greenhouse.io') else host
    senders=config.get('mailbox_verification_senders',{}).get(platform or domain,[])
    query=f'to:{recipient} after:{int(requested.timestamp())} ("security code" OR "verification code" OR "one-time code")'
    rows=_gmail_json(config,'search',query,'--max','10')
    if not isinstance(rows,list):raise ValueError('mailbox_response_unrecognized')
    matches=[]
    for row in rows:
        if not isinstance(row,dict) or not re.fullmatch(r'[A-Za-z0-9_-]{1,200}',str(row.get('id',''))):continue
        message=_gmail_json(config,'get',row['id'])
        if not isinstance(message,dict) or message.get('id')!=row['id']:continue
        recipients={address.casefold() for _,address in getaddresses([message.get('to','')])}
        sender_addresses=[address.casefold() for _,address in getaddresses([message.get('from','')])]
        if recipient not in recipients or len(sender_addresses)!=1:continue
        sender=sender_addresses[0];sender_domain=sender.rsplit('@',1)[-1]
        if sender not in senders and sender_domain!=domain and not sender_domain.endswith('.'+domain):continue
        try:
            received=parsedate_to_datetime(message.get('date',''))
            if received.tzinfo is None or not requested<=received<=now:continue
        except (TypeError,ValueError):continue
        body=html.unescape(re.sub(r'<[^>]*>',' ',str(message.get('body',''))))
        content=' '.join(body.split());subject=str(message.get('subject',''))
        if re.search(r'password\s*reset|reset\s*(?:your\s*)?password',subject,re.I):continue
        company=job.get('company')
        if not company or not re.search(r'(?<!\w)'+re.escape(company)+r'(?!\w)',content,re.I):continue
        pattern=r'(?:security|verification|one[ -]?time)\s+code\s*(?::|is\b)?\s*([A-Za-z0-9]{'+str(length)+r'})(?![A-Za-z0-9])'
        codes=set(re.findall(pattern,content,re.I))
        if len(codes)!=1:continue
        matches.append({'value':next(iter(codes)),'message_id':row['id'],
                        'received_at':received.isoformat(),'requested_at':requested.isoformat()})
    if len(matches)>1:raise ValueError('ambiguous_verification_mail')
    if not matches:raise ValueError('correlated_verification_mail_unavailable')
    return matches[0]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--script',required=True)
    parser.add_argument('--token-file',required=True)
    args,remaining=parser.parse_known_args()
    spec=importlib.util.spec_from_file_location('jobbot_google_api',args.script)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.TOKEN_PATH=Path(args.token_file)
    sys.argv=[args.script,*remaining]
    module.main()


if __name__=='__main__':main()
