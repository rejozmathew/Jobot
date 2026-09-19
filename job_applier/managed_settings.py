"""Versioned effective operational settings; no credentials or active-attempt mutation."""
import hashlib
import json
import math
import re
from zoneinfo import available_timezones
from .managed_shared import ProtocolError, dumps
from .managed_redaction import reject_secrets

DEFAULTS={'mode':'development','submission_mode':'review','worker':'external','autofill':'simplify',
    'screenshots':False,'timezone':'UTC','trigger':'manual','allowed_fallback':'targeted',
    'field_seconds':60,'no_progress_seconds':45,'attempt_seconds':300,'lease_seconds':60,
    'reasoning_provider':None,'reasoning_model':None,'reasoning_effort':'low','application_model_override':False,'learning_activation':'manual',
    'notifications':'none','excluded_companies':[],'market_countries':['US'],'browser_mode':'headed',
    'discovery_batch_size':5,'discovery_interval_hours':4}
CHOICES={'mode':('development','pilot'),'submission_mode':('review','submit'),
    'worker':('external','hermes'),'autofill':('simplify','native'),'trigger':('manual',),
    'allowed_fallback':('targeted','block'),'learning_activation':('manual',),'notifications':('none',),
    'browser_mode':('headed','headless'),'reasoning_effort':('low','medium','high','xhigh')}
BOUNDS={'field_seconds':(1,300),'no_progress_seconds':(1,600),'attempt_seconds':(1,3600),'lease_seconds':(10,600)}
PUBLIC_ID=re.compile(r'^[A-Za-z0-9_.:/-]{1,250}$')


def validate_settings(values):
    reject_secrets(values)
    if set(values)-set(DEFAULTS):raise ProtocolError('unsupported_setting')
    out=dict(DEFAULTS);out.update(values)
    for key,allowed in CHOICES.items():
        if out[key] not in allowed:raise ProtocolError('unsupported_'+key)
    if type(out['screenshots']) is not bool:raise ProtocolError('invalid_screenshot_policy')
    if type(out['application_model_override']) is not bool:raise ProtocolError('invalid_model_override')
    if out['mode']=='development' and out['submission_mode']!='review':raise ProtocolError('development_submission_disabled')
    if out['timezone'] not in available_timezones()|{'UTC'}:raise ProtocolError('unsupported_timezone')
    for key,(low,high) in BOUNDS.items():
        value=out[key]
        if type(value) not in (int,float) or not math.isfinite(value) or not low<=value<=high:raise ProtocolError('invalid_budget')
    if type(out['discovery_batch_size']) is not int or not 1<=out['discovery_batch_size']<=100:
        raise ProtocolError('invalid_discovery_batch_size')
    hours=out['discovery_interval_hours']
    if type(hours) not in (int,float) or not math.isfinite(hours) or not 1<=hours<=168:
        raise ProtocolError('invalid_discovery_interval_hours')
    for key in ('reasoning_provider','reasoning_model'):
        if out[key] is not None and (not isinstance(out[key],str) or not PUBLIC_ID.fullmatch(out[key])):raise ProtocolError('invalid_reasoning_selection')
    if bool(out['reasoning_provider'])!=bool(out['reasoning_model']):raise ProtocolError('incomplete_reasoning_selection')
    for key in ('excluded_companies','market_countries'):
        if not isinstance(out[key],list) or len(out[key])>100 or any(not isinstance(x,str) or not x.strip() or len(x)>100 for x in out[key]):raise ProtocolError('invalid_market_policy')
    return out


class SettingsServices:
    def model_catalog(self, *, refresh=False):
        from .model_settings import model_catalog
        return model_catalog(getattr(self, 'executor_config', None), refresh=refresh)

    @staticmethod
    def _reasoning_matches(run,capabilities):
        snapshot=json.loads(run['settings_json'])
        if snapshot.get('autofill')=='native' and (not isinstance(capabilities.get('autofill_strategies'),list) or 'native' not in capabilities['autofill_strategies']):raise ProtocolError('autofill_capability_unavailable')
        for setting,reported in (('reasoning_provider','provider'),('reasoning_model','model')):
            if snapshot.get(setting) and capabilities.get(reported)!=snapshot[setting]:raise ProtocolError('reasoning_selection_mismatch')
        if capabilities.get('reasoning_effort') and capabilities['reasoning_effort']!=snapshot.get('reasoning_effort','low'):
            raise ProtocolError('reasoning_selection_mismatch')
        if capabilities.get('browser_mode')=='headless' and snapshot.get('browser_mode','headed')=='headed':
            raise ProtocolError('browser_mode_mismatch')

    def _settings_record(self,db):
        row=db.execute('SELECT * FROM settings_revisions ORDER BY version DESC LIMIT 1').fetchone()
        if row:return {'version':row['version'],'values':dict(DEFAULTS)|json.loads(row['values_json'])}
        original=json.loads(db.execute('SELECT settings_json FROM instance WHERE id=?',(self.instance_id,)).fetchone()[0])
        return {'version':1,'values':dict(DEFAULTS)|original}

    def settings_view(self):
        with self.tx() as db:result=self._settings_record(db)
        return dict(result,supported=CHOICES,budget_ranges=BOUNDS,
            notes={'reasoning':'Requested selection; only an attested matching external worker can accept.',
                   'field_seconds':'Measured tools use a semantic field_context milestone; without one, only attempt/no-progress budgets apply.',
                   'notifications':'No outbound connector configured; external delivery is unavailable.',
                   'learning_activation':'Shared changes require deliberate operator activation.'})

    def configure(self,changes,*,expected_version):
        if not isinstance(changes,dict) or type(expected_version) is not int:raise ProtocolError('invalid_settings_request')
        with self.tx() as db:
            current=self._settings_record(db)
            if expected_version!=current['version']:raise ProtocolError('settings_version_conflict')
            values=validate_settings(current['values']|changes)
            now=self.now()
            old_json=dumps(current['values']);new_json=dumps(values)
            db.execute('INSERT OR IGNORE INTO settings_revisions VALUES (?,?,?,?)',(current['version'],old_json,hashlib.sha256(old_json.encode()).hexdigest(),now))
            version=current['version']+1
            db.execute('INSERT INTO settings_revisions VALUES (?,?,?,?)',(version,new_json,hashlib.sha256(new_json.encode()).hexdigest(),now))
            db.execute('UPDATE instance SET settings_json=? WHERE id=?',(new_json,self.instance_id))
        self.settings=values
        return self.settings_view()
