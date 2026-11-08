from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from enquiry.app import app
from enquiry.extraction import Extraction, review
from enquiry.intake import parse_email, read_pdf

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / 'artifacts/trading-fixtures/cases/practice/shutdown/01-customer-enquiry.eml'
)


def test_original_email_contains_the_requirement_pdf():
    raw = FIXTURE.read_bytes()
    key, _, source = parse_email(raw)
    pdf, pages = read_pdf(raw)
    assert key == '<shutdown-01@fixtures.example>'
    assert 'by 11 tomorrow' in source['body']
    assert pdf.startswith(b'%PDF-')
    assert all(text in pages[0] for text in ('500 EA', '200 EA', '300 EA', '12 Nov 2026'))


def test_missing_pdf_is_a_reviewable_error():
    with pytest.raises(ValueError, match='exactly one'):
        read_pdf(b'From: buyer@example.test\n\nPlease quote 500 bolts.')


def test_invented_evidence_and_unsupported_unit_are_flagged():
    extraction = Extraction.model_validate({
        'lines': [{
            'quantity': 500, 'unit': 'PALLET',
            'evidence': {'quantity': {'source': 'pdf', 'page': 1, 'excerpt': '999 EA'}},
        }],
    })
    issues = review(extraction, {'body': '', 'subject': ''}, ['500 EA'])
    assert 'Line 1: verify source for quantity.' in issues
    assert 'Line 1: confirm unit PALLET.' in issues


def test_replay_and_retry_with_postgres(monkeypatch):
    import os

    if not os.environ.get('DATABASE_URL'):
        pytest.skip('Set DATABASE_URL to a disposable PostgreSQL database.')
    raw = FIXTURE.read_bytes().replace(b'<shutdown-01@fixtures.example>',
                                      f'<test-{os.urandom(8).hex()}@example.test>'.encode())
    calls = []

    def extract(source, pages):
        calls.append(source)
        if len(calls) == 1:
            raise httpx.ReadTimeout('simulated timeout')
        return Extraction(lines=[])

    monkeypatch.setattr(app.state, 'extract', extract)
    with TestClient(app, follow_redirects=False) as client:
        def upload():
            return client.post('/enquiries/import', files={'email': ('test.eml', raw)})

        first = upload()
        assert first.status_code == 303
        url = first.headers['location']
        assert 'Retry extraction' in client.get(url).text
        assert upload().headers['location'] == url
        assert len(calls) == 1
        assert client.post(url + '/retry').status_code == 303
        assert 'ready for buyer review' in client.get(url).text
        assert upload().headers['location'] == url
        assert len(calls) == 2
        assert client.get(url + '/pdf').content.startswith(b'%PDF-')
