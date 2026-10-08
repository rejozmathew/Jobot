"""Deliver recorded submissions through Hermes, independently of application work.

The selected managed ledger is read-only here. Private delivery receipts are not
application history. No model, gateway, browser or application helper is started.
"""
import argparse
from contextlib import closing
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import re
import subprocess
import time

from .application_runtime import readonly, resolve_config
from .managed import Service
from .managed_redaction import safe_text
from .workspace_process import FileLock
from .daily_summary import poll_summary


def send_hermes(options, message):
    """Use Hermes's supported CLI and its private profile credentials."""
    environment = dict(os.environ)
    if options.get('profile_home'):
        environment['HERMES_HOME'] = options['profile_home']
    result = subprocess.run(
        [options.get('hermes_executable') or 'hermes', 'send', '--to', options['target'],
         '--file', '-', '--json'],
        input=message, text=True, encoding='utf-8', capture_output=True,
        env=environment, timeout=30)
    # Raw CLI output can contain provider errors/private details. Persist only
    # the acknowledgement, never stdout/stderr or an exception's raw message.
    if result.returncode:
        raise RuntimeError('hermes_delivery_failed')
    try:
        receipt = json.loads(result.stdout)
    except (ValueError, TypeError):
        raise RuntimeError('hermes_delivery_unacknowledged') from None
    if not isinstance(receipt, dict) or receipt.get('success') is not True:
        raise RuntimeError('hermes_delivery_unacknowledged')
    return {'message_id': str(receipt.get('message_id') or '')[:100]}


def _field(value, fallback):
    text = ' '.join(safe_text(str(value or fallback), 300).split()) or fallback
    # Job metadata is external text. Keep it from becoming a Discord mention,
    # a Hermes media attachment directive, or formatting around our message.
    text = re.sub(r'MEDIA:', 'MEDIA\u200b:', text, flags=re.I)
    text = text.replace('@', '@\u200b')
    return re.sub(r'([\\`*_{}\[\]()<>#|~])', r'\\\1', text)


def _records(service):
    with closing(readonly(service.db_path)) as db:
        instance = db.execute('SELECT id FROM instance').fetchone()
        if not instance or instance[0] != service.instance_id:
            raise ValueError('notification_instance_mismatch')
        return [dict(row) for row in db.execute('''
            SELECT l.job_id, j.company, j.title, l.recorded_at,
                EXISTS (SELECT 1 FROM application_attempts a WHERE a.job_id=l.job_id
                        AND a.outcome='applied' AND a.completed_at IS NOT NULL) AS applied
            FROM submission_ledger l JOIN jobs j ON j.id=l.job_id
            ORDER BY l.recorded_at,l.job_id''')]


def _save(path, state):
    temporary = path.with_suffix('.tmp')
    with temporary.open('w', encoding='utf-8') as stream:
        if os.name != 'nt':
            os.fchmod(stream.fileno(), 0o600)
        json.dump(state, stream, ensure_ascii=True)
    temporary.replace(path)


def poll(config, service, *, sender=send_hermes):
    options = config.get('submission_notifications') or {}
    if not options.get('target') or options.get('enabled') is False:
        return {'enabled': False, 'sent': 0, 'failed': 0}
    if not re.fullmatch(r'discord:[0-9]+', options['target']):
        raise ValueError('explicit_discord_channel_required')
    folder = Path(config['spool_dir'])/'notifications'
    folder.mkdir(parents=True, exist_ok=True)
    if os.name != 'nt':
        folder.chmod(0o700)
    path = folder/'submissions.json'
    with FileLock(folder/'submissions.lock'):
        records = _records(service)
        if not path.exists():
            # Enabling alerts starts from now, rather than flooding the channel
            # with old applications. Deployment initializes this before pickup.
            state = {'instance_id': service.instance_id, 'initialized_at': service.now(),
                     'deliveries': {r['job_id']: {'state': 'historical'} for r in records}}
            _save(path, state)
            daily=poll_summary(config,service,state,sender=sender,save=lambda:_save(path,state))
            return {'enabled': True, 'initialized': True, 'sent': 0, 'failed': 0, **daily}
        state = json.loads(path.read_text(encoding='utf-8'))
        if state['instance_id'] != service.instance_id:
            raise ValueError('notification_checkpoint_instance_mismatch')
        now = datetime.fromisoformat(service.now())
        sent = failed = 0
        for record in records:
            delivery = state['deliveries'].get(record['job_id'], {})
            if delivery.get('state') in ('historical', 'sent') or not record['applied']:
                continue
            if delivery.get('retry_at') and datetime.fromisoformat(delivery['retry_at']) > now:
                continue
            message = ('Application submitted\nCompany: '+_field(record['company'], 'Company unavailable')+
                       '\nRole: '+_field(record['title'], 'Role unavailable'))
            try:
                receipt = sender(options, message)
            except Exception as exc:
                failures = delivery.get('failures', 0)+1
                delivery = {'state': 'pending', 'failures': failures, 'error': type(exc).__name__,
                            'retry_at': (now+timedelta(seconds=min(300, 15*2**min(failures-1, 5)))).isoformat()}
                failed += 1
            else:
                delivery = {'state': 'sent', 'sent_at': service.now(),
                            'message_id': str((receipt or {}).get('message_id') or '')[:100]}
                sent += 1
            state['deliveries'][record['job_id']] = delivery
            _save(path, state)
        daily=poll_summary(config,service,state,sender=sender,save=lambda:_save(path,state))
        return {'enabled': True, 'initialized': False, 'sent': sent, 'failed': failed, **daily}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config')
    parser.add_argument('command', choices=('once', 'watch'))
    args = parser.parse_args(argv)
    config = resolve_config(args.config)
    service = Service(config['db_path'], instance_id=config['instance_id'])
    while True:
        try:
            result = poll(config, service)
        except Exception as exc:
            if args.command == 'once':
                raise
            result = {'notification_error': type(exc).__name__}
        if args.command == 'once' or any(result.get(k) for k in ('sent','failed','daily_sent','daily_failed','notification_error')):
            print(json.dumps(result), flush=True)
        if args.command == 'once':
            return 0
        time.sleep(5)


if __name__ == '__main__':
    raise SystemExit(main())
