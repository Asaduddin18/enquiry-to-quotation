from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_CEILING
from email import policy
from email.parser import BytesParser
from email.utils import parseaddr
from html import escape
from io import BytesIO
import re
from xml.etree.ElementTree import ParseError
from zipfile import BadZipFile, ZipFile

from fastapi import APIRouter, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException
from psycopg.types.json import Jsonb

from .intake import dated_source, parse_email
from .rfq import ready_context
from .store import connect
from .suppliers import classify, fingerprint

router = APIRouter()
GST = timezone(timedelta(hours=4))
PREFIX = '/enquiries/{enquiry_id}/lines/{line_id}/offers'
FIELDS = ('RFQ reference', 'Line reference', 'Offered item / specification', 'Brand',
          'Country of origin', 'Price (OMR)', 'Price basis', 'Pieces per pack',
          'Minimum order', 'Minimum order unit', 'Deliver by (GST)', 'Valid until (GST)')


def read_terms(data):
    with ZipFile(BytesIO(data)) as archive:
        if sum(entry.file_size for entry in archive.infolist()) > 20 * 1024 * 1024:
            raise ValueError('Workbook expands beyond the size limit.')
    workbook = load_workbook(BytesIO(data), read_only=True, data_only=False)
    try:
        if 'Supplier offer' not in workbook:
            raise ValueError('Expected the Supplier offer sheet.')
        terms = {}
        for label, cell in workbook['Supplier offer'].iter_rows(max_row=100, max_col=2):
            if label.value in FIELDS:
                if label.value in terms:
                    raise ValueError('Duplicate workbook field.')
                terms[label.value] = {
                    'value': str(cell.value).strip() if cell.value is not None else '',
                    'cell': f'B{label.row}',
                    'formula': cell.data_type == 'f',
                }
        return terms
    finally:
        workbook.close()


def value(terms, label):
    return terms.get(label, {}).get('value', '')


def date(value):
    return datetime.strptime(value, '%d %b %Y %H:%M GST').replace(tzinfo=GST)


def positive(value):
    number = Decimal(value)
    if not number.is_finite() or number <= 0 or number > 10**9:
        raise ValueError('Expected a positive commercial value.')
    return number


def pieces(unit, pack):
    if unit.upper() in {'EA', 'PC', 'PCS'}:
        return Decimal(1)
    if unit.upper() in {'BOX', 'PACK'} and pack and pack == int(pack):
        return pack
    raise ValueError('Unknown unit or missing pack size.')


def compare(line, terms, deadline, now, accepted=False):
    missing = [label for label in FIELDS if label != 'Pieces per pack'
               and not value(terms, label)]
    if missing or any(field['formula'] for field in terms.values()):
        raise ValueError('Clarify missing values or formulas: ' + ', '.join(missing))
    offered = value(terms, 'Offered item / specification')
    required = ' '.join(line.get(key) or '' for key in ('description', 'specification'))
    required_class = classify(line)
    offered_class = classify({'description': offered})
    dimensions = r'\bm\s*(\d+)\s*(?:mm)?(?:\s*[x×]\s*(\d+))?'
    expected = set(re.findall(dimensions, required.lower()))
    actual = set(re.findall(dimensions, offered.lower()))
    if not all(required_class) or not expected:
        raise ValueError('Verify the requirement specification.')
    if offered_class != required_class or not expected <= actual:
        raise ValueError('Offered specification differs or needs clarification.')
    if line.get('substitution') and not accepted:
        raise ValueError('Review brand or substitution conditions.')
    delivery = date(value(terms, 'Deliver by (GST)'))
    validity = date(value(terms, 'Valid until (GST)'))
    if validity <= now:
        raise ValueError('Offer expired.')
    if delivery > deadline:
        raise ValueError('Delivery misses the required date.')
    pack_text = value(terms, 'Pieces per pack')
    pack = positive(pack_text) if pack_text else None
    basis = pieces(value(terms, 'Price basis'), pack)
    minimum = positive(value(terms, 'Minimum order')) * pieces(value(terms, 'Minimum order unit'), pack)
    if minimum != int(minimum):
        raise ValueError('Minimum order must resolve to whole pieces.')
    demand = Decimal(line['quantity']) * pieces(line['unit'], pack)
    multiple = max(basis, pieces(value(terms, 'Minimum order unit'), pack))
    purchased = (max(demand, minimum) / multiple).to_integral_value(rounding=ROUND_CEILING) * multiple
    price = positive(value(terms, 'Price (OMR)'))
    return {'unit_price': price / basis, 'purchase_quantity': purchased,
            'total': (purchased / basis) * price, 'delivery': delivery, 'validity': validity}


@router.post('/supplier-replies')
def import_reply(email: UploadFile):
    raw = email.file.read(10 * 1024 * 1024 + 1)
    if not raw or len(raw) > 10 * 1024 * 1024:
        raise HTTPException(413, 'Upload a non-empty EML up to 10 MiB.')
    key, digest, source = parse_email(raw)
    try:
        timestamp = dated_source(source)
    except (ValueError, TypeError):
        raise HTTPException(422, 'Supplier email needs a dated timestamp.')
    sender = parseaddr(source['sender'])[1].casefold()
    refs = set(re.findall(r'\bRFQ-[A-F0-9]{16}\b', source['subject'], re.I))
    reference = next(iter(refs)).upper() if len(refs) == 1 else None
    supplier = terms = None
    issue = 'RFQ subject reference could not be linked.'
    with connect() as db:
        package = db.execute("""
            SELECT p.approved_at, a.enquiry_id, a.selection FROM rfq_package p
            JOIN supplier_approval a ON a.id=p.approval_id WHERE p.reference=%s
        """, (reference,)).fetchone()
        if package and package['approved_at']:
            db.execute('SELECT id FROM enquiry_intake WHERE id=%s FOR UPDATE', (package['enquiry_id'],))
            supplier = next((r['id'] for r in package['selection']['recipients']
                             if r['email'].casefold() == sender), None)
            issue = 'Sender was outside the approved recipients.'
            if supplier:
                attachments = [a for a in BytesParser(policy=policy.default).parsebytes(raw).iter_attachments()
                               if (a.get_filename() or '').lower().endswith('.xlsx')]
                try:
                    if len(attachments) != 1:
                        raise ValueError('Expected one offer workbook. Review email for follow-up or withdrawal.')
                    parsed = read_terms(attachments[0].get_payload(decode=True))
                    if any(value(parsed, field) != reference or parsed[field]['formula']
                           for field in FIELDS[:2]):
                        raise ValueError('Workbook references disagree with the email.')
                    terms, issue = parsed, None
                except (ValueError, BadZipFile, InvalidFileException, KeyError, OSError, ParseError, TypeError):
                    issue = 'Missing, unreadable, or mismatched workbook. Inspect the source email.'
        else:
            reference = None
        db.execute("""
            INSERT INTO supplier_reply (message_key,digest,raw_email,received_at,reference,supplier_id,terms,issue)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (message_key) DO NOTHING
        """, (key, digest, raw, timestamp, reference, supplier, Jsonb(terms), issue))
        stored = db.execute('SELECT digest FROM supplier_reply WHERE message_key=%s', (key,)).fetchone()
        if stored['digest'] != digest:
            raise HTTPException(409, 'Message ID reused with different content.')
    return RedirectResponse('/supplier-replies', status_code=303)


@router.get('/supplier-replies', response_class=HTMLResponse)
def inbox():
    with connect() as db:
        rows = db.execute('SELECT id,reference,supplier_id,issue FROM supplier_reply ORDER BY id DESC').fetchall()
    return '<h1>Supplier replies</h1><form method="post" enctype="multipart/form-data"><input type="file" name="email" required><button>Import EML</button></form><ul>' + ''.join(
        f'<li><a href="/supplier-replies/{row["id"]}/source">Reply {row["id"]}</a> '
        + escape(f'{row["reference"] or "Unlinked"} · {row["supplier_id"] or "Unknown sender"} · {row["issue"] or "Workbook linked"}')
        + '</li>' for row in rows
    ) + '</ul>'


@router.get('/supplier-replies/{reply_id}/source')
def source_email(reply_id: int):
    with connect() as db:
        row = db.execute('SELECT raw_email FROM supplier_reply WHERE id=%s', (reply_id,)).fetchone()
    if not row:
        raise HTTPException(404)
    return Response(row['raw_email'], media_type='message/rfc822',
                    headers={'Content-Disposition': 'attachment; filename="supplier-reply.eml"'})


def comparison(db, enquiry_id, line_id, now):
    line, _, package = ready_context(db, enquiry_id, line_id)
    if not package or not package['approved_at']:
        raise HTTPException(409, 'Approve the RFQ package first.')
    deadline = db.execute('SELECT candidate FROM enquiry_intake WHERE id=%s', (enquiry_id,)).fetchone()
    cutoff = datetime.fromisoformat(deadline['candidate']['delivery_deadline'])
    rows = db.execute("""
        SELECT id,supplier_id,terms,issue,review_action,review_reason FROM supplier_reply
        WHERE reference=%s ORDER BY received_at DESC,id DESC
    """, (package['reference'],)).fetchall()
    seen = set()
    offers = {}
    for row in rows:
        supplier = row['supplier_id']
        terms = row['terms']
        action = row['review_action']
        if not supplier or (not terms and action not in {'withdraw', 'hold'}) or supplier in seen:
            continue
        seen.add(supplier)
        try:
            if action in {'withdraw', 'hold'}:
                raise ValueError(f'Buyer review: {action}.')
            result = compare(line, terms, cutoff, now, action == 'accept substitution')
        except (ValueError, InvalidOperation, OverflowError) as error:
            row['blocker'] = str(error)
        else:
            offers[row['id']] = result
    ranked = sorted(offers, key=lambda key: (offers[key]['total'], offers[key]['delivery'], key))
    token = fingerprint([package['reference'], rows, ranked])
    return line, package, rows, offers, ranked, token


@router.post(PREFIX + '/review/{reply_id}')
def review_reply(enquiry_id: int, line_id: str, reply_id: int,
                 action: str = Form(), reason: str = Form(), token: str = Form()):
    with connect() as db:
        _, _, rows, _, _, current = comparison(db, enquiry_id, line_id, datetime.now(GST))
        if current != token:
            raise HTTPException(409, 'Reload the comparison.')
        row = next((r for r in rows if r['id'] == reply_id and r['supplier_id']), None)
        if not row or not reason.strip() or action not in {'withdraw', 'hold', 'accept substitution'}:
            raise HTTPException(422, 'Choose a linked reply, review action, and reason.')
        db.execute('UPDATE supplier_reply SET review_action=%s,review_reason=%s WHERE id=%s',
                   (action, reason.strip(), reply_id))
    return RedirectResponse(f'/enquiries/{enquiry_id}/lines/{line_id}/offers', status_code=303)


@router.post(PREFIX)
def select_offer(enquiry_id: int, line_id: str, reply_id: int = Form(),
                 token: str = Form(), reason: str = Form('')):
    with connect() as db:
        _, package, _, offers, ranked, current = comparison(db, enquiry_id, line_id, datetime.now(GST))
        if current != token or reply_id not in offers:
            raise HTTPException(409, 'Reload the comparison and select an eligible offer.')
        if reply_id != ranked[0] and not reason.strip():
            raise HTTPException(422, 'Explain the override.')
        previous = db.execute('SELECT reply_id,reason FROM sourcing_selection WHERE reference=%s ORDER BY id DESC LIMIT 1',
                              (package['reference'],)).fetchone()
        if previous != {'reply_id': reply_id, 'reason': reason.strip()}:
            db.execute('INSERT INTO sourcing_selection (reference,reply_id,reason) VALUES (%s,%s,%s)',
                       (package['reference'], reply_id, reason.strip()))
    return RedirectResponse(f'/enquiries/{enquiry_id}/lines/{line_id}/offers', status_code=303)


@router.get(PREFIX + '/handoff')
def handoff(enquiry_id: int, line_id: str):
    with connect() as db:
        line, package, _, offers, _, _ = comparison(db, enquiry_id, line_id, datetime.now(GST))
        selected = db.execute('SELECT reply_id,reason FROM sourcing_selection WHERE reference=%s ORDER BY id DESC LIMIT 1',
                              (package['reference'],)).fetchone()
    if not selected or selected['reply_id'] not in offers:
        raise HTTPException(409, 'Select a current eligible offer.')
    result = offers[selected['reply_id']]
    return {'line': line, 'reference': package['reference'], **selected,
            'cost': {key: str(amount) for key, amount in result.items()}}


@router.get(PREFIX, response_class=HTMLResponse)
def offers_page(enquiry_id: int, line_id: str):
    url = f'/enquiries/{enquiry_id}/lines/{line_id}/offers'
    with connect() as db:
        _, package, rows, offers, ranked, token = comparison(db, enquiry_id, line_id, datetime.now(GST))
    content = [f'<h1>Offers for {package["reference"]}</h1><a href="/supplier-replies">Import or inspect replies</a>',
               f'<p>{f"Recommended reply: {ranked[0]} (lowest eligible total spend)" if ranked else "Line blocked. No eligible offers."}</p>',
               '<p>Historical benchmark is deferred.</p>']
    for row in rows:
        key = row['id']
        result = offers.get(key)
        reason = row.get('blocker') or row['issue'] or 'Earlier offer'
        detail = (f'OMR {result["total"]:.3f} total · OMR {result["unit_price"]:.3f} per piece · '
                  f'{result["purchase_quantity"]} pieces' if result else reason)
        content.append(f'<h2>Reply {key} · {escape(row["supplier_id"] or "Unknown sender")}</h2>'
                       f'<a href="/supplier-replies/{key}/source">Source email and attachment</a><p>{escape(detail)}</p>')
        for label, cell in (row['terms'] or {}).items():
            content.append(f'<div>{escape(label)} ({escape(cell["cell"])}): {escape(cell["value"])}</div>')
        if result:
            content.append(f'<form method="post" action="{url}"><input type="hidden" name="token" value="{token}">'
                           f'<input type="hidden" name="reply_id" value="{key}"><input name="reason" placeholder="Override reason">'
                           '<button>Select offer</button></form>')
        if row['supplier_id']:
            content.append(f'<form method="post" action="{url}/review/{key}"><input type="hidden" name="token" value="{token}">'
                           '<input name="reason" required placeholder="Evidence and reason">'
                           '<button name="action" value="withdraw">Record withdrawal</button>'
                           '<button name="action" value="hold">Hold for clarification</button>'
                           '<button name="action" value="accept substitution">Approve substitution</button></form>')
    return ''.join(content)
