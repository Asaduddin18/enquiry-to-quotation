from datetime import datetime, timedelta, timezone
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import parseaddr
from html import escape
from io import BytesIO
from uuid import uuid4
from xml.etree import ElementTree
from zipfile import ZipFile

from fastapi import APIRouter, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from .requirements_review import intake
from .store import connect
from .suppliers import DATA, approval_context, current_recipient_approval, load_directory

router = APIRouter()
PREFIX = '/enquiries/{enquiry_id}/lines/{line_id}/rfq'
XLSX = 'vnd.openxmlformats-officedocument.spreadsheetml.sheet'
TEMPLATE = DATA.parent / 'templates/supplier-quotation.xlsx'
SHEET = 'xl/worksheets/sheet1.xml'
XML = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'


def render_workbook(fields):
    output = BytesIO()
    with ZipFile(TEMPLATE) as original, ZipFile(output, 'w') as result:
        sheet = ElementTree.fromstring(original.read(SHEET))
        for address, value in fields.items():
            cell = sheet.find(f'.//{XML}c[@r="{address}"]')
            if isinstance(value, int):
                cell.clear()
                cell.set('r', address)
                ElementTree.SubElement(cell, XML + 'v').text = str(value)
            else:
                cell.find(f'.//{XML}t').text = value
        for name in original.namelist():
            data = ElementTree.tostring(sheet) if name == SHEET else original.read(name)
            result.writestr(name, data)
    return output.getvalue()


def build_package(reference, line, recipients, delivery):
    item = ' · '.join(dict.fromkeys(
        value for value in (line['description'], line['specification'], line.get('substitution')) if value
    ))
    workbook = render_workbook({
        'B3': reference, 'B4': reference, 'B5': item,
        'B6': line['quantity'], 'B7': line['unit'], 'B9': delivery,
    })
    email = EmailMessage(policy=policy.SMTP)
    email['To'] = 'undisclosed-recipients:;'
    email['Bcc'] = ', '.join(recipient['email'] for recipient in recipients)
    email['Subject'] = f'{reference} | Availability and price'
    email.set_content(
        f'Hello,\n\nUnder reference {reference}, please quote '
        f'{line["quantity"]} {line["unit"]} of {item}.\n'
        f'Delivery required by {delivery}, delivered to site in Muscat. Quote in OMR excluding VAT.\n'
        'Please complete the attached workbook, keeping the references unchanged. Include any '
        'alternate, minimum quantity, delivery timing, and offer validity.\n\nRegards,\nPurchasing'
    )
    email.add_attachment(workbook, maintype='application', subtype=XLSX,
                         filename=f'{reference}-request.xlsx')
    return email.as_bytes(), workbook


def ready_context(db, enquiry_id, line_id):
    line, approvals = approval_context(db, enquiry_id, line_id)
    directory, _ = load_directory()
    approval = current_recipient_approval(line, approvals, directory)
    if not approval:
        raise HTTPException(409, 'Confirm the current line and approve its recipients first.')
    package = db.execute('SELECT * FROM rfq_package WHERE approval_id=%s', (approval['id'],)).fetchone()
    return line, approval, package


def url_for(enquiry_id, line_id):
    return f'/enquiries/{enquiry_id}/lines/{line_id}/rfq'


@router.get(PREFIX, response_class=HTMLResponse)
def preview(enquiry_id: int, line_id: str):
    url = url_for(enquiry_id, line_id)
    with connect() as db:
        _, approval, package = ready_context(db, enquiry_id, line_id)
    back = f'<a href="/enquiries/{enquiry_id}/lines/{escape(line_id, quote=True)}/suppliers">Back to recipients</a>'
    if not package:
        return f'''{back}<h1>Prepare RFQ package</h1>
        <form method="post" action="{url}"><button>Generate draft and workbook</button></form>'''
    message = BytesParser(policy=policy.default).parsebytes(package['draft'])
    summary = escape(f"Subject: {message['Subject']}\nBCC: {message['Bcc']}\n\n"
                     + message.get_body().get_content())
    if package['approved_at']:
        action = f'''<p>Approved for manual sending.</p><a href="{url.removesuffix('/rfq')}/offers">Compare supplier offers</a> <a href="{url}/email">Download EML</a>'''
    else:
        action = f'''<form method="post" action="{url}/approve">
        <input type="hidden" name="reference" value="{package['reference']}">
        <label><input type="checkbox" name="reviewed" value="true" required> I reviewed the recipients, email and workbook.</label>
        <button>Approve this package</button></form>'''
    return f'''{back}<h1>Review RFQ package</h1><pre>{summary}</pre>
    <a href="{url}/workbook">Inspect Excel workbook</a>{action}'''


@router.post(PREFIX)
def prepare(enquiry_id: int, line_id: str):
    with connect() as db:
        line, approval, package = ready_context(db, enquiry_id, line_id)
        if not package:
            enquiry = intake(db, enquiry_id)
            candidate = enquiry['candidate']
            private_values = (candidate.get('customer_reference'), enquiry['source'].get('sender'))
            name, address = parseaddr(private_values[1] or '')
            item_text = ' '.join(str(line.get(key) or '') for key in ('description', 'specification', 'substitution'))
            if any(value and value.casefold() in item_text.casefold()
                   for value in (private_values[0], name, address)):
                raise HTTPException(422, 'Remove customer identifiers from the confirmed line before drafting.')
            deadline = enquiry['candidate'].get('delivery_deadline')
            if not deadline or datetime.fromisoformat(deadline).tzinfo is None:
                raise HTTPException(422, 'A delivery deadline with time zone is required.')
            delivery = datetime.fromisoformat(deadline).astimezone(timezone(timedelta(hours=4)))
            reference = 'RFQ-' + uuid4().hex[:16].upper()
            draft, workbook = build_package(
                reference, line, approval['selection']['recipients'],
                delivery.strftime('%d %b %Y %H:%M GST'),
            )
            db.execute(
                'INSERT INTO rfq_package (approval_id,reference,draft,workbook) VALUES (%s,%s,%s,%s)',
                (approval['id'], reference, draft, workbook),
            )
    return RedirectResponse(url_for(enquiry_id, line_id), status_code=303)


@router.post(PREFIX + '/approve')
def approve_package(enquiry_id: int, line_id: str, reference: str = Form(), reviewed: bool = Form()):
    if not reviewed:
        raise HTTPException(422, "Confirm that you reviewed the package.")
    with connect() as db:
        _, approval, package = ready_context(db, enquiry_id, line_id)
        if not package or package['reference'] != reference:
            raise HTTPException(409, 'Reload the current RFQ package before approving.')
        db.execute('UPDATE rfq_package SET approved_at=now() WHERE approval_id=%s AND approved_at IS NULL',
                   (approval['id'],))
    return RedirectResponse(url_for(enquiry_id, line_id), status_code=303)


@router.get(PREFIX + '/{file_type}')
def download(enquiry_id: int, line_id: str, file_type: str):
    with connect() as db:
        _, _, package = ready_context(db, enquiry_id, line_id)
    if not package or file_type not in {'workbook', 'email'}:
        raise HTTPException(404, 'RFQ file not found.')
    if file_type == 'email' and not package['approved_at']:
        raise HTTPException(409, 'Approve the package before downloading the email.')
    data, extension, mime = ((package['draft'], 'eml', 'message/rfc822') if file_type == 'email'
                             else (package['workbook'], 'xlsx', 'application/' + XLSX))
    return Response(data, media_type=mime, headers={
        'Content-Disposition': f'attachment; filename="{package["reference"]}.{extension}"',
    })
