from copy import deepcopy
import sqlite3

import pytest
from fastapi.testclient import TestClient

from crm_backend.api import create_app
from crm_backend.store import Store
from crm_backend.workspace import COLLECTIONS
from tests.test_crm_api import PASSWORD, logged


def document():
    data = {key: [] for key in COLLECTIONS}
    data['factorySettings'] = {'companyName': 'Наш цех', 'version': 1, 'materials': {}}
    data['clients'] = [{'id': 'C-1', 'name': 'Клиент'}]
    data['orders'] = [{'id': 'F-1', 'clientId': 'C-1', 'parts': [
        {'id': 'P-1', 'height': 720, 'width': 400, 'qty': 2,
         'cadModel': {'operations': [{'kind': 'groove', 'depth': 3}]}}],
        'manualLayout': {'placements': [{'x': 8, 'y': 8, 'rotation': 90}]}}]
    data['stockMovements'] = [{'kind': 'приход', 'title': 'МДФ'}]
    return data


@pytest.fixture
def workspace(tmp_path):
    app = create_app(tmp_path / 'factory')
    app.state.store.create_user('owner', PASSWORD, 'admin')
    return app


def test_shared_data_conflict_history_and_restore(workspace, tmp_path):
    a, ah = logged(workspace)
    b, bh = logged(workspace)
    assert a.get('/api/workspace').json() == {'revision': 0, 'data': None}
    payload = document()
    first = a.put('/api/workspace', headers=ah, json={'expected_revision': 0, 'data': payload})
    assert first.status_code == 200, first.text
    assert b.get('/api/workspace').json()['data'] == payload
    changed = deepcopy(payload)
    changed['clients'][0]['name'] = 'Обновлённый клиент'
    assert b.put('/api/workspace', headers=bh, json={'expected_revision': 1, 'data': changed}).json()['revision'] == 2
    assert a.put('/api/workspace', headers=ah, json={'expected_revision': 1, 'data': payload}).status_code == 409
    store = workspace.state.store
    backup = store.backup(tmp_path / 'backups')
    restored = Store.restore_to(backup, tmp_path / 'restored')
    with sqlite3.connect(restored) as con:
        assert con.execute('SELECT COUNT(*) FROM workspace_revisions').fetchone()[0] == 2
        assert con.execute('PRAGMA foreign_key_check').fetchall() == []
    fresh, _ = logged(create_app(tmp_path / 'restored'))
    assert fresh.get('/api/workspace').json() == {'revision': 2, 'data': changed}


def test_permissions_validation_and_import(workspace):
    admin, headers = logged(workspace)
    guest = TestClient(workspace)
    assert guest.get('/api/workspace').status_code == 401
    assert admin.put('/api/workspace', json={'expected_revision': 0, 'data': document()}).status_code == 403
    for role in ['manager', 'worker', 'technologist']:
        workspace.state.store.create_user(role, PASSWORD, role)
        client, auth = logged(workspace, role)
        assert client.get('/api/workspace').status_code == (200 if role == 'manager' else 403)
        assert client.post('/api/workspace/import', headers=auth, json={'expected_revision': 0, 'data': document()}).status_code == 403
        if role != 'manager':
            assert client.put('/api/workspace', headers=auth, json={'expected_revision': 0, 'data': document()}).status_code == 403
    dealer = admin.post('/api/dealers', headers=headers, json={'name': 'Дилер'}).json()
    workspace.state.store.create_user('dealer', PASSWORD, 'dealer', dealer['id'])
    client, auth = logged(workspace, 'dealer')
    for path in ['/api/workspace', '/api/workspace/version']:
        assert client.get(path).status_code == 403
    bad = document()
    bad['clients'] *= 2
    assert admin.put('/api/workspace', headers=headers, json={'expected_revision': 0, 'data': bad}).status_code == 422
    assert admin.get('/api/workspace/version').json()['revision'] == 0
    assert admin.post('/api/workspace/import', headers=headers, json={'expected_revision': 0, 'data': document()}).status_code == 200
    assert admin.post('/api/workspace/import', headers=headers, json={'expected_revision': 1, 'data': document()}).status_code == 409


def test_first_setup_once_and_origin(tmp_path):
    app = create_app(tmp_path / 'new')
    client = TestClient(app)
    assert client.get('/api/setup').json() == {'configured': False}
    body = {'username': 'owner', 'password': PASSWORD}
    assert client.post('/api/setup', headers={'Origin': 'https://evil.example'}, json=body).status_code == 403
    assert client.post('/api/setup', json=body).status_code == 201
    assert client.post('/api/setup', json=body).status_code == 409
    assert client.get('/api/setup').json() == {'configured': True}
    assert client.post('/api/login', json=body).status_code == 200


def test_staff_shell_uses_server_bootstrap(workspace):
    client = TestClient(workspace)
    response = client.get('/work/')
    assert response.status_code == 200
    assert '<base href="/work/assets/">' in response.text
    assert 'workspace_server.js' in response.text
    assert 'workspace_server.js?v=' in response.text
    assert 'cutting_layout.js?v=' in response.text
    assert '<script src="app.js">' not in response.text
    assert client.get('/work/assets/workspace_server.js').status_code == 200


def test_backup_download_requires_admin_and_contains_workspace(workspace, tmp_path):
    admin, headers = logged(workspace)
    admin.put('/api/workspace', headers=headers, json={'expected_revision': 0, 'data': document()})
    response = admin.post('/api/workspace/backup', headers=headers)
    assert response.status_code == 200, response.text
    name = response.json()['name']
    downloaded = admin.get('/api/workspace/backup/' + name)
    assert downloaded.status_code == 200
    target = tmp_path / 'download.sqlite3'
    target.write_bytes(downloaded.content)
    with sqlite3.connect(target) as con:
        assert con.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert con.execute('SELECT MAX(revision) FROM workspace_revisions').fetchone()[0] == 1
    workspace.state.store.create_user('manager', PASSWORD, 'manager')
    manager, auth = logged(workspace, 'manager')
    assert manager.post('/api/workspace/backup', headers=auth).status_code == 403
    assert manager.get('/api/workspace/backup/' + name).status_code == 403
    assert TestClient(workspace).get('/api/workspace/backup/' + name).status_code == 401
    assert admin.get('/api/workspace/backup/not-a-backup.sqlite3').status_code == 404
