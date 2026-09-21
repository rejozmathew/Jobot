"""Startup and authoritative metadata regression using isolated managed records."""
import json

import pytest

from job_applier import browser_controls
from job_applier.managed import ProtocolError
from test_local_sessions import setup, reserve, connect, own
from test_greenhouse_recovery import form_dom


@pytest.mark.parametrize('platform,operation,parameters', [
    ('workday','fast_forward',{'seconds':60}),
    ('greenhouse','greenhouse_advance',{'seconds':60}),
    ('unknown','browser',{'method':'simplify','action':'autofill'}),
])
def test_initial_filling_routes_by_platform_and_enabled_control(platform,operation,parameters):
    guidance=browser_controls.next_operation(platform,{'status':'ready','controls':{'autofill':{'enabled':True}}})
    assert guidance['operation']==operation and guidance['parameters']==parameters


def test_active_writer_and_settled_review_have_distinct_guidance():
    active=browser_controls.next_operation('greenhouse',{'status':'active','controls':{'autofill':{'enabled':True}}})
    assert active['operation']=='greenhouse_advance' and active['parameters']=={'seconds':60}
    review=browser_controls.next_operation('greenhouse',{'status':'needs_review','controls':{}})
    assert review['operation']=='greenhouse_advance' and review['parameters']=={'seconds':60}


def test_metadata_enrichment_is_idempotent_and_preserves_explicit_labels_and_outcomes(tmp_path):
    s,asset,jobs,ws,cfg=setup(tmp_path);job=jobs[0]
    first=s.enrich_job(job['id'],url=job['url'],company='Example',title='Director',source='employer_posting')
    assert first['changed'] and first['job']['company']=='Example' and first['job']['title']=='Director'
    again=s.enrich_job(job['id'],url=job['url'],company='Another',title='Manager',source='simplify_job_card')
    assert not again['changed'] and set(again['conflicts'])=={'company','title'}
    stored=s.job(job['id'])
    assert stored['status']==job['status'] and stored['eligibility']=='ready'
    assert json.loads(stored['metadata_json'])['label_sources']['company']['source']=='employer_posting'


def test_enrichment_rejects_wrong_job_and_backfill_only_previews_until_applied(tmp_path):
    s,asset,jobs,ws,cfg=setup(tmp_path);job=jobs[0]
    with pytest.raises(ProtocolError,match='metadata_job_mismatch'):
        s.enrich_job(job['id'],url=jobs[1]['url'],company='Wrong',source='employer_posting')
    session=connect(s,reserve(s,asset,jobs))
    records=[{'job_id':job['id'],'job_url':job['url'],'company':'Example','job_title':'Director','attempt_id':session['attempt_id']}]
    result=s.backfill_job_metadata(records=records)
    assert result['preview'] and result['rows'][0]['proposed']=={'company':'Example','title':'Director'}
    assert s.job(job['id'])['company'] is None


def test_reintake_fills_missing_labels_without_overwriting_existing(tmp_path):
    s,asset,jobs,ws,cfg=setup(tmp_path);job=jobs[0]
    first=s.intake(url=job['url'],company='Example',title='Director')
    assert first['id']==job['id'] and first['company']=='Example'
    assert s.intake(url=job['url'],company='Other')['company']=='Example'


def test_metadata_accepts_alternate_url_only_after_verified_identity_alias(tmp_path):
    s,asset,jobs,ws,cfg=setup(tmp_path)
    job=s.intake(url='https://careers.example.test/role/director',namespace='fixture:portal',requisition_id='director',identity_evidence='employer_posting')
    alias='https://apply.example.test/jobs/director'
    result=s.intake(url=alias,namespace='fixture:portal',requisition_id='director',identity_evidence='employer_posting',company='Example')
    assert result['id']==job['id'] and result['company']=='Example'
    enriched=s.enrich_job(job['id'],url=alias,title='Director',source='employer_posting')
    assert enriched['changed'] and enriched['job']['title']=='Director'


def test_normal_owned_observation_persists_metadata_in_all_job_views(tmp_path):
    s,asset,jobs,ws,cfg=setup(tmp_path);session=connect(s,reserve(s,asset,jobs))
    result=s.observe_job_metadata(**own(s,session),metadata={
        'url':jobs[0]['url'],'company':'Example','title':'Director','source':'employer_posting'})
    assert result['changed']
    assert s.application_context(session['attempt_id'])['job']['company']=='Example'
    assert s.attempt_report(session['attempt_id'])['attempt']['job_title']=='Director'
    assert json.loads(s.attempt_report(session['attempt_id'])['attempt']['job_metadata_json'])['label_discovery']['status']=='identified'


def test_structured_posting_metadata_has_exact_job_url_provenance():
    result=form_dom('''<script type="application/ld+json">{"@type":"JobPosting",
"url":"https://boards.greenhouse.io/example/jobs/12345","title":"Director",
"hiringOrganization":{"name":"Example"}}</script>''',[{'method':'metadata'}])
    assert result['results'][0]['company']=='Example'
    assert result['results'][0]['title']=='Director'
    assert result['results'][0]['source']=='employer_posting'


def test_ambiguous_postings_do_not_supply_labels():
    result=form_dom('''<script type="application/ld+json">[
{"@type":"JobPosting","title":"Director","hiringOrganization":{"name":"Example"}},
{"@type":"JobPosting","title":"Manager","hiringOrganization":{"name":"Other"}}]
</script>''',[{'method':'metadata'}])
    assert result['results'][0]=={}
