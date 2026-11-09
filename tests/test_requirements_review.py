import os
import re
from pathlib import Path
from email import policy
from email.parser import BytesParser
from io import BytesIO
from datetime import datetime

from openpyxl import load_workbook
import enquiry.offers as sourcing
import enquiry.quotes as quoting
from pypdf import PdfReader
from zipfile import ZipFile
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
            'delivery_deadline': '2026-11-12T14:00:00+04:00',
            'lines': [
                {'line_number': str(number), 'description': 'Hex head bolt',
                 'specification': 'M10 x 55 A2-70' if is_revision else ('Class 10.9' if number == 20 else 'M10 x 50 A2-70'),
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
            fields = dict(version=version, decision='confirmed', description='Hex head bolt',
                          specification='Class 10.9' if index == 2 else 'M10 x 50 A2-70', quantity='500', unit='EA')
            return client.post(f'{parent}/lines/{parent_id}-{index}/review', data=fields | overrides)

        assert decide(1, 0, specification='').status_code == 422
        assert decide(1, 0, quantity='501').status_code == 422
        assert decide(1, 0, quantity='501', reason='Buyer counted 501').status_code == 303
        assert decide(1, 0, quantity='501', reason='Buyer counted 501').status_code == 303
        assert decide(2, 1).status_code == 303
        assert decide(3, 2, decision='awaiting clarification', reason='Verify brand').status_code == 303
        line10 = f'{parent}/lines/{parent_id}-1/suppliers'
        line20 = f'{parent}/lines/{parent_id}-2/suppliers'
        line30 = f'{parent}/lines/{parent_id}-3/suppliers'

        def approval(url, grade, ids):
            page = client.get(url).text
            token = re.search(r'name="token" value="([^"]+)"', page)[1]
            return dict(token=token, family='HEX_BOLT', grade=grade, supplier_ids=ids)

        assert 'Confirm the requirement' in client.get(line30).text
        assert client.post(line30, data={'token': 'unused'}).status_code == 409
        first = approval(line10, 'A2-70', ['A', 'B'])
        assert client.post(line10, data=first).status_code == 303
        assert client.post(line10, data=first).status_code == 303
        assert 'value="C" checked' in client.get(line20).text
        second = approval(line20, '10.9', ['A', 'C'])
        assert client.post(line20, data=second).status_code == 422
        assert client.post(line20, data=second | {'reason': 'Can source on request'}).status_code == 303
        rfq10 = line10.replace('/suppliers', '/rfq')
        rfq20 = line20.replace('/suppliers', '/rfq')
        assert client.post(line30.replace('/suppliers', '/rfq')).status_code == 409
        assert client.post(rfq10).status_code == 303
        assert client.post(rfq10).status_code == 303
        assert client.get(rfq10 + '/email').status_code == 409
        workbook = client.get(rfq10 + '/workbook').content
        with ZipFile(BytesIO(workbook)) as archive:
            sheet = archive.read('xl/worksheets/sheet1.xml')
        reference = re.search(rb'RFQ-[A-F0-9]{16}', sheet)[0].decode()
        assert sheet.count(reference.encode()) == 2
        assert b'501' in sheet and b'MR-26-184' not in sheet
        assert client.post(rfq10 + '/approve', data={'reference': reference, 'reviewed': 'true'}).status_code == 303
        assert client.post(rfq10 + '/approve', data={'reference': reference, 'reviewed': 'true'}).status_code == 303
        email = BytesParser(policy=policy.default).parsebytes(client.get(rfq10 + '/email').content)
        assert len(email['Bcc'].addresses) == 2 and reference in email['Subject']
        assert reference in email.get_body().get_content()
        assert 'MR-26-184' not in email.as_string()
        assert next(email.iter_attachments()).get_payload(decode=True) == workbook
        class FixtureClock(datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(2026, 11, 9, 10, tzinfo=sourcing.GST).astimezone(tz)

        monkeypatch.setattr(sourcing, 'datetime', FixtureClock)
        monkeypatch.setattr(quoting, 'datetime', FixtureClock)
        supplier_email = BytesParser(policy=policy.default).parsebytes(
            next(FIXTURES.glob('05-*.eml')).read_bytes()
        )
        attachment = next(supplier_email.iter_attachments())
        returned = load_workbook(BytesIO(attachment.get_payload(decode=True)))
        returned.active['B3'] = returned.active['B4'] = reference
        filled = BytesIO()
        returned.save(filled)
        attachment.set_payload(filled.getvalue())
        from email.encoders import encode_base64
        del attachment['Content-Transfer-Encoding']
        encode_base64(attachment)
        supplier_email.replace_header('Subject', f'Re: {reference}')
        reply = supplier_email.as_bytes()
        for _ in range(2):
            assert client.post('/supplier-replies', files={'email': ('reply.eml', reply)}).status_code == 303
        offers = line10.replace('/suppliers', '/offers')
        page = client.get(offers).text
        assert 'OMR 210.420 total' in page
        token = re.search(r'name="token" value="([^"]+)"', page)[1]
        reply_id = re.search(r'name="reply_id" value="(\d+)"', page)[1]
        assert client.post(offers, data={'reply_id': reply_id, 'token': token}).status_code == 303
        assert client.get(offers + '/handoff').json()['cost']['total'] == '210.42'
        quotes = parent + '/quotes'
        quote_token = re.search(r'name="token" value="([^"]+)"', client.get(quotes).text)[1]
        quote_form = {'token': quote_token, 'lines': f'{parent_id}-1',
                      f'price_{parent_id}-1': '0.480', 'price_reason': 'Competitive bid'}
        assert client.post(quotes, data=quote_form).status_code == 422
        quote_form['permission'] = 'Customer permits line 10 to be quoted separately'
        quote = client.post(quotes, data=quote_form).headers['location']
        assert client.post(quotes, data=quote_form).headers['location'] == quote
        assert client.get(quote + '/email').status_code == 409
        assert client.post(quote + '/approve', data={'reviewed': 'true'}).status_code == 422
        approval = {'reviewed': 'true', 'manager_exception': 'true', 'reason': 'Approved competitive bid'}
        assert client.post(quote + '/approve', data=approval).status_code == 303
        assert client.post(quote + '/issue', data={'sent': 'true'}).status_code == 422
        pdf = client.get(quote + '/pdf').content
        text = PdfReader(BytesIO(pdf)).pages[0].extract_text()
        assert '240.480' in text and 'Pending' in text and '210.42' not in text
        assert reference not in text
        customer_email = BytesParser(policy=policy.default).parsebytes(client.get(quote + '/email').content)
        assert next(customer_email.iter_attachments()).get_payload(decode=True) == pdf
        assert client.post(quote + '/issue', data={'sent': 'true'}).status_code == 303
        assert client.post(quote + '/issue', data={'sent': 'true'}).status_code == 303
        purchase = dict(line_id=f'{parent_id}-1', reference='PO-42', cost='211', pieces='501',
                        purchased_on='2026-11-09')
        assert client.post(quote + '/purchase', data=purchase).status_code == 303
        assert client.post(quote + '/purchase', data=purchase).status_code == 303
        assert client.post(quote + '/purchase', data=purchase | {'cost': '212'}).status_code == 409
        draft = client.post(quotes, data=quote_form).headers['location']
        assert client.post(draft + '/approve', data=approval).status_code == 303
        assert client.post(rfq20).status_code == 303
        revision = upload('16-customer-revision.eml')
        assert upload('16-customer-revision.eml') == revision
        assert f'value="{parent_id}" required' in client.get(revision).text
        preview = client.get(revision + '/revision-preview', params={'parent_id': parent_id})
        assert 'M10 x 50 A2-70 → M10 x 55 A2-70' in preview.text
        form = {'parent_id': parent_id, 'version': 3, 'scope_confirmed': 'true'}
        assert client.post(revision + '/apply-revision', data=form).status_code == 303
        assert client.post(revision + '/apply-revision', data=form).status_code == 303
        assert decide(1, 3).status_code == 409
        assert client.post(line10, data=first).status_code == 409
        assert 'Recipients approved' in client.get(line20).text
        assert client.get(rfq10 + '/email').status_code == 409
        assert client.get(offers + '/handoff').status_code == 409
        assert client.get(draft + '/email').status_code == 409
        assert client.get(quote + '/pdf').content == pdf
        assert client.get(rfq20 + '/workbook').status_code == 200
        assert decide(1, 4, specification='M10 x 55 A2-70').status_code == 303
        assert 'Recipient approval required' in client.get(line10).text
        assert client.post(line10, data=first).status_code == 409

    with connect() as db:
        rows = db.execute(
            'SELECT snapshot FROM enquiry_review WHERE enquiry_id=%s ORDER BY version', (parent_id,)
        ).fetchall()
        assert db.execute(
            'SELECT count(*) AS count FROM supplier_approval WHERE enquiry_id=%s', (parent_id,)
        ).fetchone()['count'] == 2
    assert len(rows) == 5
    before, after = [row['snapshot'] for row in rows[2:4]]
    assert after[1:] == before[1:]
    assert after[0]['id'] == before[0]['id']
    assert after[0]['status'] == 'needs review'
    assert after[0]['specification'] == 'M10 x 55 A2-70'
