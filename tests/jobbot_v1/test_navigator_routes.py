from integrations.jobnavigator_bridge.resolve_routes import classify, destination, route_priority


def test_routes_use_observed_apply_control_and_preserve_requisition():
    url='https://jobs.example.com/posting?id=ABC123&source=linkedin'
    from urllib.parse import quote
    wrapper='https://www.linkedin.com/safety/go/?url='+quote(url,safe='')
    result=classify({'url':'https://www.linkedin.com/jobs/view/123/',
                     'controls':[{'text':'Apply','href':wrapper}]},'123')
    assert result=={'application_type':'external','application_url':url}
    assert destination('https://ad.doubleclick.net/ddm/clk/1;2?'+url)==url


def test_unknown_and_other_posting_are_not_easy_apply():
    assert classify({'url':'https://other.example/jobs/view/123/',
                     'controls':[{'text':'Easy Apply'}]},'123') is None
    assert classify({'url':'https://www.linkedin.com/jobs/view/123/','controls':[]},'123') is None
    assert classify({'url':'https://www.linkedin.com/jobs/view/999/',
                     'controls':[{'text':'Easy Apply'}]},'123') is None
    assert classify({'url':'https://www.linkedin.com/jobs/view/123/',
                     'controls':[{'text':'Easy Apply'}]},'123')['application_type']=='linkedin_easy_apply'


def test_matching_backlog_is_first_without_starving_unseen_rows():
    seen = {'failed-read': 10}
    rows = [('review', 'held_for_review'), ('failed-read', 'eligible'), ('match', 'eligible')]
    assert [r[0] for r in sorted(rows, key=lambda r: route_priority(*r, seen))] == [
        'match', 'review', 'failed-read']
