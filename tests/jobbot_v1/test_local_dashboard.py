"""The local desktop dashboard opens without asking for credentials."""
from fastapi.testclient import TestClient
from test_operator_ui import make_test_environment, BASE_URL


def test_open_local_dashboard_connects_without_login(tmp_path):
    service, _, app = make_test_environment(tmp_path)
    client = TestClient(app, base_url=BASE_URL)
    page = client.get('/')
    assert page.status_code == 200
    session = client.get('/session')
    assert session.status_code == 200
    assert session.json()['instance_id'] == service.instance_id
    response = client.post('/v1/view', json={}, headers={'X-JobBot-Instance': service.instance_id})
    assert response.status_code == 200
    assert 'Operator credential' not in page.text
    assert 'id="operator-token"' not in page.text


def test_dashboard_shows_browser_mode_choice(tmp_path):
    _, _, app = make_test_environment(tmp_path)
    page = TestClient(app, base_url=BASE_URL).get('/').text
    assert 'id="main-browser-mode"' in page
    assert 'value="headed"' in page
    assert 'value="headless"' in page
