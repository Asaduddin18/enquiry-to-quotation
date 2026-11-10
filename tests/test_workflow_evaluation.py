import json
import os
import re
from datetime import datetime, timedelta
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import format_datetime
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from pypdf import PdfReader
from reportlab.pdfgen.canvas import Canvas

import enquiry.offers as sourcing
import enquiry.quotes as quoting
from enquiry.app import app
from enquiry.extraction import Extraction, deepseek, review
from enquiry.intake import parse_email, read_pdf

CASES = json.loads(Path('artifacts/phase-6/cases.json').read_text())
NOW = datetime(2026, 11, 10, 12, tzinfo=sourcing.GST)
DELIVERY = '12 Nov 2026 14:00 GST'


class EvaluationClock(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW.astimezone(tz)


def customer_email(case):
    pdf = BytesIO()
    page = Canvas(pdf)
    page.drawString(55, 790, 'Maintenance requisition ' + case['reference'])
    page.drawString(55, 765, 'Deliver to Muscat by ' + DELIVERY)
    page.drawString(55, 720, f"Item {case['line']}   {case['spec']}   {case['quantity']} EA")
    page.save()
    mail = EmailMessage()
    mail['From'] = f'{case["id"]}@maintenance.example'
    mail['To'] = 'buying@wadi-link.example'
    mail['Subject'] = case['subject']
    mail['Message-ID'] = f'<{uuid4()}@evaluation.example>'
    mail['Date'] = format_datetime(NOW - timedelta(hours=4))
    mail.set_content(case['body'])
    mail.add_attachment(pdf.getvalue(), maintype='application', subtype='pdf', filename='request.pdf')
    return mail.as_bytes()


def supplier_reply(workbook, offer, reference, index):
    book = load_workbook(BytesIO(workbook))
    terms = (offer['spec'], 'Standard stock', 'Oman', float(offer['price']), offer['basis'],
             offer['pack'], offer['minimum'], offer['basis'], DELIVERY, offer['valid'])
    for row, value in enumerate(terms, start=11):
        book.active.cell(row, 2, value)
    attachment = BytesIO()
    book.save(attachment)
    book.close()
    mail = EmailMessage()
    mail['From'] = {'A': 'sales@ridge-fasteners.example', 'B': 'quotes@harbour-bulk.example',
                    'C': 'sales@sumail-fixings.example'}[offer['supplier']]
    mail['To'] = 'buying@wadi-link.example'
    mail['Subject'] = 'Re: ' + reference
    mail['Date'] = format_datetime(NOW - timedelta(minutes=30-index))
    mail['Message-ID'] = f'<{uuid4()}@evaluation.example>'
    mail.set_content('Updated sheet attached.' if index else 'Please see our offer attached.')
    mail.add_attachment(attachment.getvalue(), maintype='application',
                        subtype='vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                        filename='offer.xlsx')
    return mail.as_bytes()


def field(html, name):
    return re.search(fr'name="{name}" value="([^"]+)"', html)[1]


@pytest.mark.parametrize('case', CASES, ids=lambda case: case['id'])
def test_held_out_workflow(case, monkeypatch):
    if not os.getenv('DATABASE_URL'):
        pytest.skip('Use a disposable PostgreSQL database.')
    monkeypatch.setattr(sourcing, 'datetime', EvaluationClock)
    monkeypatch.setattr(quoting, 'datetime', EvaluationClock)
    monkeypatch.setattr(app.state, 'extract', lambda *_: Extraction.model_validate({
        'customer_reference': case['reference'],
        'quote_deadline': '2026-11-10T15:30:00+04:00',
        'delivery_deadline': '2026-11-12T14:00:00+04:00',
        'lines': [{'line_number': case['line'], 'description': case['spec'],
                   'specification': case['spec'], 'quantity': case['quantity'], 'unit': 'EA'}],
    }), raising=False)

    with TestClient(app, follow_redirects=False) as client:
        def upload(url, data):
            response = client.post(url, files={'email': ('message.eml', data)})
            assert response.status_code == 303, response.text
            return response

        def post(url, data=None, expected=303):
            response = client.post(url, data=data)
            assert response.status_code == expected, response.text
            return response

        enquiry = upload('/enquiries/import', customer_email(case)).headers['location']
        line_id = enquiry.rsplit('/', 1)[-1] + '-1'
        line = f'{enquiry}/lines/{line_id}'
        post(line + '/review', dict(version=0, decision='confirmed', description=case['spec'],
                                    specification=case['spec'], quantity=case['quantity'], unit='EA'))
        suppliers = line + '/suppliers'
        grade = 'A2-70' if 'A2-70' in case['spec'] else '10.9'
        post(suppliers, dict(token=field(client.get(suppliers).text, 'token'), family='HEX_BOLT',
                             grade=grade, supplier_ids=sorted({offer['supplier'] for offer in case['offers']})))
        rfq = line + '/rfq'
        post(rfq)
        workbook = client.get(rfq + '/workbook').content
        reference = field(client.get(rfq).text, 'reference')
        post(rfq + '/approve', dict(reference=reference, reviewed='true'))
        assert case['reference'] not in client.get(rfq + '/email').text
        offers = line + '/offers'
        quotes = enquiry + '/quotes'
        approved = None
        for index, offer in enumerate(case['offers']):
            upload('/supplier-replies', supplier_reply(workbook, offer, reference, index))
            page = client.get(offers).text
            if 'blocker' in offer:
                assert offer['blocker'] in page and 'Line blocked' in page
                continue
            assert f'OMR {offer["total"]} total' in page
            if case.get('expect_stale_release') and index == 0:
                post(offers, dict(token=field(page, 'token'), reply_id=field(page, 'reply_id')))
                approved = post(quotes, dict(token=field(client.get(quotes).text, 'token'),
                                             lines=line_id)).headers['location']
                post(approved + '/approve', dict(reviewed='true'))

        if case['quote_total'] is None:
            assert client.get(offers + '/handoff').status_code == 409
            return
        page = client.get(offers).text
        recommended = re.search(r'Recommended reply: (\d+)', page)[1]
        post(offers, dict(token=field(page, 'token'), reply_id=recommended))
        if approved:
            assert client.get(approved + '/email').status_code == 409
        quote = post(quotes, dict(token=field(client.get(quotes).text, 'token'),
                                  lines=line_id)).headers['location']
        post(quote + '/approve', dict(reviewed='true'))
        draft = client.get(quote + '/email')
        assert draft.status_code == 200
        mail = BytesParser(policy=policy.default).parsebytes(draft.content)
        pdf = next(mail.iter_attachments()).get_payload(decode=True)
        assert pdf == client.get(quote + '/pdf').content
        text = PdfReader(BytesIO(pdf)).pages[0].extract_text()
        assert f'Total OMR {case["quote_total"]}' in text
        assert reference not in text
        post(quote + '/issue', dict(sent='true'))


@pytest.mark.parametrize('case', CASES, ids=lambda case: case['id'])
def test_held_out_live_extraction(case):
    if os.getenv('RUN_LIVE_EXTRACTION') != '1':
        pytest.skip('Opt in with RUN_LIVE_EXTRACTION=1 and a configured DeepSeek key.')
    raw = customer_email(case)
    _, _, source = parse_email(raw)
    _, pages = read_pdf(raw)
    result = deepseek(source, pages)
    assert result.customer_reference == case['reference']
    assert result.quote_deadline == NOW.replace(hour=15, minute=30)
    assert result.delivery_deadline == datetime(2026, 11, 12, 14, tzinfo=sourcing.GST)
    assert [(line.line_number, line.quantity, line.unit) for line in result.lines] == [
        (case['line'], case['quantity'], 'EA')
    ]
    assert not review(result, source, pages)
