"""Read-only calendar-day counts and daily Discord delivery bookkeeping."""
from collections import defaultdict
from datetime import date,datetime,time,timedelta,timezone
import json
from zoneinfo import ZoneInfo

from .managed_reports import instant,posting_groups,reported_outcome
from .managed_queue import attempt_schedule,RETRY_OUTCOMES,AUTOMATIC_ATTEMPTS


def application_day(service,day,*,timezone_name='America/Chicago',identity_id=None):
    selected=date.fromisoformat(day);zone=ZoneInfo(timezone_name)
    begin=datetime.combine(selected,time.min,zone).astimezone(timezone.utc)
    end=datetime.combine(selected+timedelta(days=1),time.min,zone).astimezone(timezone.utc)
    inside=lambda value:bool(value and begin<=instant(value)<end)
    with service.read() as db:
        groups=posting_groups(db)
        attempts=[dict(r) for r in db.execute('''SELECT id,job_id,identity_id,started_at,completed_at,outcome,evidence
            FROM application_attempts WHERE (? IS NULL OR identity_id=?)''',(identity_id,identity_id))]
        queue=[dict(r) for r in db.execute('SELECT * FROM dispatch_queue WHERE (? IS NULL OR identity_id=?) ORDER BY rowid',
                                         (identity_id,identity_id))]
        skipped=[dict(r) for r in db.execute('''SELECT job_id,skipped_at FROM job_duplicate_skips
            WHERE (? IS NULL OR identity_id=? OR identity_id='')''',(identity_id,identity_id))]
        ledger=[dict(r) for r in db.execute('''SELECT l.job_id,l.recorded_at FROM submission_ledger l
            WHERE ? IS NULL OR l.person_key IN (SELECT person_key FROM candidates WHERE id=?)''',(identity_id,identity_id))]
    posting=lambda job:groups.get(job,job)
    attempts.sort(key=lambda a:(instant(a['started_at']),a['id']))
    started=[a for a in attempts if inside(a['started_at'])]
    attempted={posting(a['job_id']) for a in started}
    accepted=defaultdict(list);new=defaultdict(list);already=set()
    for attempt in attempts:
        outcome=reported_outcome(attempt)
        if outcome not in ('applied','already_applied'):continue
        key=posting(attempt['job_id']);accepted[key].append(instant(attempt['completed_at']))
        if outcome=='applied':new[key].append(attempt)
        elif inside(attempt['completed_at']):already.add(key)
    # Retained legacy success can predate the available attempt history.
    for entry in ledger:
        if entry['recorded_at']:accepted[posting(entry['job_id'])].append(instant(entry['recorded_at']))
    submitted={key for key,rows in new.items() if any(inside(a['completed_at']) for a in rows)
               and not any(stamp<begin for stamp in accepted[key])}
    success_times={key:min(instant(a['completed_at']) for a in new[key] if inside(a['completed_at'])) for key in submitted}
    successful_by_end={key for key,stamps in accepted.items() if any(stamp<end for stamp in stamps)}
    schedule=attempt_schedule(queue)
    exhausted={posting(q['job_id']) for q in queue if q['state']=='finished' and q['outcome'] in RETRY_OUTCOMES
               and inside(q['ended_at']) and schedule[q['id']]['attempt_number']==AUTOMATIC_ATTEMPTS}
    return {'date':day,'timezone':timezone_name,'start_at':begin.isoformat(),'end_at':end.isoformat(),
            'submitted_jobs':len(submitted),'attempted_jobs':len(attempted),'attempts':len(started),
            'attempts_for_submitted_jobs':sum(posting(a['job_id']) in submitted and instant(a['started_at'])<=success_times[posting(a['job_id'])]
                                               for a in attempts),
            'already_applied_jobs':len(already),'without_submission_jobs':len(attempted-successful_by_end),
            'duplicate_jobs_skipped':len({r['job_id'] for r in skipped if inside(r['skipped_at'])}),
            'automatic_limit_jobs':len(exhausted)}


def format_summary(report):
    return ('JobBot daily summary — '+report['date']+' ('+report['timezone']+')\n'
            f"Jobs submitted: {report['submitted_jobs']}\n"
            f"Jobs attempted: {report['attempted_jobs']}\n"
            f"Application attempts: {report['attempts']}\n"
            f"Attempts used for submitted jobs (including earlier days): {report['attempts_for_submitted_jobs']}\n"
            f"Duplicate jobs skipped: {report['duplicate_jobs_skipped']}\n"
            f"Already-applied results: {report['already_applied_jobs']}\n"
            f"Attempted jobs without submission by day end: {report['without_submission_jobs']}\n"
            f"Jobs reaching the 6-attempt automatic limit: {report['automatic_limit_jobs']}")


def poll_summary(config,service,state,*,sender,save):
    """Called under the notification service's existing single-writer lock."""
    options=config.get('submission_notifications') or {};daily=options.get('daily_summary') or {}
    if daily.get('enabled') is not True:return {}
    zone_name=daily.get('timezone','America/Chicago');zone=ZoneInfo(zone_name)
    due=time.fromisoformat(daily.get('time','08:00'))
    if due.tzinfo is not None:raise ValueError('daily_time_must_be_local')
    now=instant(service.now());local=now.astimezone(zone)
    record=state.get('daily_summary')
    if record is None or record.get('timezone')!=zone_name:
        # Enabling begins with today's completed report tomorrow. Never replay
        # historical days simply because the feature or timezone was changed.
        state['daily_summary']={'timezone':zone_name,'next_date':local.date().isoformat(),'deliveries':{}}
        save();return {'daily_sent':0,'daily_failed':0}
    day=date.fromisoformat(record['next_date'])
    if day>=local.date() or local.time().replace(tzinfo=None)<due:return {'daily_sent':0,'daily_failed':0}
    key=day.isoformat();delivery=record['deliveries'].get(key,{})
    if delivery.get('state')=='sent':
        record['next_date']=(day+timedelta(days=1)).isoformat();save()
        return {'daily_sent':0,'daily_failed':0}
    if delivery.get('retry_at') and instant(delivery['retry_at'])>now:return {'daily_sent':0,'daily_failed':0}
    if not delivery.get('message'):
        report=application_day(service,key,timezone_name=zone_name,identity_id=config.get('identity_id'))
        delivery={'state':'pending','message':format_summary(report),'counts':report,'failures':0}
        record['deliveries'][key]=delivery;save()
    try:receipt=sender(options,delivery['message'])
    except Exception as exc:
        failures=delivery.get('failures',0)+1
        delivery.update(state='pending',failures=failures,error=type(exc).__name__,
                        retry_at=(now+timedelta(seconds=min(300,15*2**min(failures-1,5)))).isoformat())
        save();return {'daily_sent':0,'daily_failed':1}
    delivery.update(state='sent',sent_at=service.now(),message_id=str((receipt or {}).get('message_id') or '')[:100])
    delivery.pop('error',None);delivery.pop('retry_at',None)
    record['next_date']=(day+timedelta(days=1)).isoformat();save()
    return {'daily_sent':1,'daily_failed':0}


def main(argv=None):
    import argparse
    from .application_runtime import resolve_config
    from .managed import Service
    parser=argparse.ArgumentParser(description='Preview daily counts without sending a message')
    parser.add_argument('--config');parser.add_argument('--date',required=True)
    parser.add_argument('--timezone',default='America/Chicago');args=parser.parse_args(argv)
    config=resolve_config(args.config);service=Service(config['db_path'],instance_id=config['instance_id'])
    print(json.dumps(application_day(service,args.date,timezone_name=args.timezone,identity_id=config.get('identity_id')),indent=2))


if __name__=='__main__':main()
