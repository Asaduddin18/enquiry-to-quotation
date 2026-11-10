import json
import os
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from enquiry.app import app
from enquiry.history import benchmark, candidates, for_offer, vector_enabled
from enquiry.store import connect

ROOT = Path('artifacts/phase-7')
RECORDS = json.loads((ROOT / 'history.json').read_text())
CASES = json.loads((ROOT / 'cases.json').read_text())
TODAY = date(2026, 11, 10)


def test_frozen_benchmark_cases():
    if not os.getenv('DATABASE_URL'):
        pytest.skip('Use a disposable PostgreSQL database.')
    with TestClient(app) as client:
        for _ in range(2):
            response = client.post('/history/import', json=RECORDS)
            assert response.status_code == 200, response.text
        assert client.get('/history/evidence', params={'source_id': 'legacy:P2'}).json()['pack'] == 10
        with connect() as db:
            assert db.execute('SELECT count(*) AS count FROM historical_price').fetchone()['count'] == 60
            has_vector = vector_enabled(db)
            for case in CASES:
                rows = candidates(db, case['spec'], case['description'])
                assert len(rows) <= 25
                if has_vector:
                    assert len(rows) == 25
                result = benchmark(rows, case['spec'], case['pieces'], Decimal(case['price']), TODAY)
                assert {record['id'] for record in result['included']} == {
                    'legacy:' + record for record in case['gold']
                }, case['id']
                assert result['flag'] == case['flag'], case['id']
                if len(case['gold']) >= 3:
                    assert result['median'] == Decimal('0.320')
                else:
                    assert result['status'] == 'insufficient history'
                if case['id'] == 'above':
                    assert result['difference'] == Decimal('31.25')
                    assert result['excluded']
        correction = RECORDS[0] | {'price': '0.310'}
        assert client.post('/history/import', json=[correction]).status_code == 200
        assert client.get('/history/evidence', params={'source_id': 'legacy:P1'}).json()['price'] == '0.310'


def test_history_connection_failure_is_nonblocking(monkeypatch):
    import psycopg
    import enquiry.history as history

    def disconnected():
        raise psycopg.OperationalError('offline')

    monkeypatch.setattr(history, 'connect', disconnected)
    line = {'description': 'Hex bolt', 'specification': 'M10 x 50 A2-70'}
    assert for_offer(line, 500, Decimal('0.420'), TODAY) == {'status': 'history unavailable'}
