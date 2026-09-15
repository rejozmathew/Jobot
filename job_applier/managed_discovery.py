"""Discovery schedule reporting; the external harvest runtime owns execution."""
from datetime import datetime, timedelta
import json

from .workspace_process import process_matches


class DiscoveryServices:
    def discovery_status(self):
        with self.tx() as db:
            settings=self._settings_record(db)['values']
            installed=bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='discovery_runs'").fetchone())
            row=db.execute('SELECT * FROM discovery_runs ORDER BY rowid DESC LIMIT 1').fetchone() if installed else None
            check=db.execute('SELECT last_checked_at FROM discovery_control WHERE id=1').fetchone()[0] if installed else None
        last=dict(row) if row else None
        due=None
        if last:
            identity=json.loads(last.pop('process_identity_json'))
            last['state']=('running' if process_matches(identity) else 'interrupted') if not last['ended_at'] else (
                'failed' if last['error'] or last['executor_exit_code']!=0 else 'completed')
            due=(datetime.fromisoformat(last['started_at'])+timedelta(hours=settings['discovery_interval_hours'])).isoformat()
        age=(datetime.fromisoformat(self.now())-datetime.fromisoformat(check)).total_seconds() if check else None
        return {'installed':installed,'batch_size':settings['discovery_batch_size'],
            'interval_hours':settings['discovery_interval_hours'],'last_run':last,'next_due_at':due,
            'scheduler_last_checked_at':check,'scheduler_recent':age is not None and 0<=age<180,
            'runner':'JobBot discovery service / Hermes'}
