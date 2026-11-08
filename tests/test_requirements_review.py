import os
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from enquiry.app import app
from enquiry.extraction import Extraction
from enquiry.store import connect

FIXTURES = Path('artifacts/trading-fixtures/cases/practice/shutdown')


def test_confirm_and_apply_line_revision(monkeypatch):
    if not os.getenv('DATABASE_URL'):
        pytest.skip('Set DATABASE_URL to a disposable PostgreSQL database.')
    key = f'<review-{uuid4()}@fixtures.example>'.encode()

    def extract(source, pages):
        is_revision = 'change notice' in pages[0]
        numbers = [10] if is_revision else [10, 20, 30]
        return Extraction.model_validate({
            'customer_reference': 'MR-26-184',
            'lines': [
                {'line_number': str(number), 'description': 'Fastener',
                 'specification': 'M10 x 55' if is_revision else 'M10 x 50',
                 'quantity': 500, 'unit': 'EA'}
                for number in numbers
            ],
        })

    monkeypatch.setattr(app.state, 'extract', extract, raising=False)

    with TestClient(app, follow_redirects=False) as client:
        def upload(name):
            data = (FIXTURES / name).read_bytes().replace(b'<shutdown-01@fixtures.example>', key)
            data = data.replace(b'<shutdown-16@fixtures.example>', key.replace(b'review-', b'revision-'))
            response = client.post('/enquiries/import', files={'email': (name, data)})
            assert response.status_code == 303
            return response.headers['location']

        parent = upload('01-customer-enquiry.eml')
        parent_id = int(parent.rsplit('/', 1)[-1])

        def decide(index, version, **overrides):
            fields = dict(version=version, decision='confirmed', description='Fastener',
                          specification='M10 x 50', quantity='500', unit='EA')
            return client.post(f'{parent}/lines/{parent_id}-{index}/review', data=fields | overrides)

        assert decide(1, 0, specification='').status_code == 422
        assert decide(1, 0, quantity='501').status_code == 422
        assert decide(1, 0, quantity='501', reason='Buyer counted 501').status_code == 303
        assert decide(1, 0, quantity='501', reason='Buyer counted 501').status_code == 303
        assert decide(2, 1).status_code == 303
        assert decide(3, 2, decision='awaiting clarification', reason='Verify brand').status_code == 303
        revision = upload('16-customer-revision.eml')
        assert upload('16-customer-revision.eml') == revision
        assert f'value="{parent_id}" required' in client.get(revision).text
        preview = client.get(revision + '/revision-preview', params={'parent_id': parent_id})
        assert 'M10 x 50 → M10 x 55' in preview.text
        form = {'parent_id': parent_id, 'version': 3, 'scope_confirmed': 'true'}
        assert client.post(revision + '/apply-revision', data=form).status_code == 303
        assert client.post(revision + '/apply-revision', data=form).status_code == 303
        assert decide(1, 3).status_code == 409

    with connect() as db:
        rows = db.execute(
            'SELECT snapshot FROM enquiry_review WHERE enquiry_id=%s ORDER BY version', (parent_id,)
        ).fetchall()
    assert len(rows) == 4
    before, after = [row['snapshot'] for row in rows[-2:]]
    assert after[1:] == before[1:]
    assert after[0]['id'] == before[0]['id']
    assert after[0]['status'] == 'needs review'
    assert after[0]['specification'] == 'M10 x 55'
