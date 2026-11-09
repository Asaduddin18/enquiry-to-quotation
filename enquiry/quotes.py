from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_CEILING
from email import policy
from email.message import EmailMessage
from email.utils import parseaddr
from html import escape
from io import BytesIO

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from psycopg.types.json import Jsonb
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from .offers import GST, comparison
from .requirements_review import current, intake
from .store import connect
from .suppliers import fingerprint

router = APIRouter()
PREFIX = '/enquiries/{enquiry_id}/quotes'
MONEY = Decimal('0.001')
TARGET = Decimal('0.20')
FLOOR = Decimal('0.15')


def price_line(quantity, cost, override=None):
    target = (cost / (1 - TARGET) / quantity).quantize(MONEY, rounding=ROUND_CEILING)
    unit = Decimal(override) if override else target
    if not unit.is_finite() or not 0 < unit <= 10**9 or unit != unit.quantize(MONEY):
        raise ValueError('Use a positive unit price with up to three OMR decimals.')
    total = unit * quantity
    margin = (total - cost) / total
    return {'unit_price': f'{unit:.3f}', 'total': f'{total:.3f}',
            'margin': str(margin), 'below_floor': margin < FLOOR}


def sources(db, enquiry, lines, now):
    found = {}
    for line in lines:
        if line['status'] != 'confirmed':
            continue
        try:
            _, package, replies, offers, _, _ = comparison(db, enquiry['id'], line['id'], now)
        except HTTPException as error:
            if error.status_code != 409:
                raise
            continue
        selected = db.execute(
            'SELECT reply_id FROM sourcing_selection WHERE reference=%s ORDER BY id DESC LIMIT 1',
            (package['reference'],),
        ).fetchone()
        if selected and selected['reply_id'] in offers:
            reply_id = selected['reply_id']
            result = offers[reply_id]
            supplier = next(reply['supplier_id'] for reply in replies if reply['id'] == reply_id)
            found[line['id']] = {
                'line': line, 'rfq': package['reference'], 'reply_id': reply_id, 'supplier': supplier,
                **{key: str(value) for key, value in result.items()},
            }
    return found


def render(snapshot, reference):
    output = BytesIO()
    styles = getSampleStyleSheet()
    story = [Paragraph('Wadi Link Trading', styles['Title']),
             Paragraph(f'Quotation {reference}', styles['Heading2'])]
    summary = [
        f"Prepared for {snapshot['customer']}",
        f"Valid until {snapshot['validity']} (Oman time)",
        'Prices in OMR, excluding VAT.',
    ]
    for item in snapshot['items']:
        line = item['source']['line']
        summary.append(
            f"Line {line['line_number']} | {line['description']} | {line['specification']} | "
            f"{line['quantity']} {line['unit']} x OMR {item['price']['unit_price']} "
            f"= OMR {item['price']['total']} | Delivery by {item['source']['delivery']}"
        )
    if snapshot['pending']:
        summary.append('Pending, excluded from this quotation: ' + ', '.join(snapshot['pending']))
    summary.append(f"Total OMR {snapshot['total']}, excluding VAT")
    for text in summary:
        story.extend([Paragraph(escape(text), styles['BodyText']), Spacer(1, 10)])
    SimpleDocTemplate(output, title=f'Quotation {reference}').build(story)
    pdf = output.getvalue()
    email = EmailMessage(policy=policy.SMTP)
    email['To'] = snapshot['customer']
    email['Subject'] = f'Quotation {reference}'
    email.set_content('Hello,\n\nPlease find our quotation attached.\n\nRegards,\nWadi Link Trading')
    email.add_attachment(pdf, maintype='application', subtype='pdf', filename=f'{reference}.pdf')
    return pdf, email.as_bytes()


def locate(db, enquiry_id, revision):
    quote = db.execute(
        'SELECT * FROM customer_quote WHERE enquiry_id=%s AND revision=%s', (enquiry_id, revision)
    ).fetchone()
    if not quote:
        raise HTTPException(404, 'Quotation revision not found.')
    return quote


def revalidate(db, enquiry, quote, now):
    latest = db.execute('SELECT max(revision) AS revision FROM customer_quote WHERE enquiry_id=%s',
                        (enquiry['id'],)).fetchone()['revision']
    if latest != quote['revision']:
        raise HTTPException(409, 'Open the latest draft revision.')
    snapshot = quote['snapshot']
    _, lines = current(db, enquiry)
    if fingerprint(lines) != snapshot['requirements']:
        raise HTTPException(409, 'Customer requirements changed. Prepare a new draft.')
    if datetime.fromisoformat(snapshot['validity']) <= now:
        raise HTTPException(409, 'Quotation validity expired.')
    live = sources(db, enquiry, lines, now)
    for item in snapshot['items']:
        source = item['source']
        if live.get(source['line']['id']) != source:
            raise HTTPException(409, f"Line {source['line']['line_number']} no longer has the selected terms.")


@router.get(PREFIX, response_class=HTMLResponse)
def workspace(enquiry_id: int):
    with connect() as db:
        enquiry = intake(db, enquiry_id)
        _, lines = current(db, enquiry)
        available = sources(db, enquiry, lines, datetime.now(GST))
        quotes = db.execute(
            'SELECT revision,approved_at,issued_at FROM customer_quote WHERE enquiry_id=%s ORDER BY revision DESC',
            (enquiry_id,),
        ).fetchall()
    rows = []
    for line in lines:
        key = escape(line['id'], quote=True)
        label = escape(f"Line {line['line_number']} · {line.get('description')}")
        if line['id'] in available:
            rows.append(f'<p><label><input type="checkbox" name="lines" value="{key}" checked>{label}</label>'
                        f' · Cost OMR {escape(available[line["id"]]["total"])} '
                        f'<input name="price_{key}" placeholder="Optional unit price"></p>')
        else:
            rows.append(f'<p>{label} · Pending eligible supplier selection</p>')
    token = fingerprint([lines, available])
    history = ''.join(f'<li><a href="/enquiries/{enquiry_id}/quotes/{q["revision"]}">Revision {q["revision"]}</a> '
                      f'{"Issued" if q["issued_at"] else "Approved" if q["approved_at"] else "Draft"}</li>'
                      for q in quotes)
    permission = escape(enquiry['candidate'].get('partial_quote_permission') or 'No permission extracted')
    return f'''<h1>Customer quotation</h1><a href="/enquiries/{enquiry_id}">Back to enquiry</a>
    <p>Customer partial-quote evidence: {permission}</p>
    <form method="post" action="/enquiries/{enquiry_id}/quotes">
    <input type="hidden" name="token" value="{token}">{''.join(rows)}
    <label>Price override reason <input name="price_reason"></label><br>
    <label>Partial quote permission covering the selected lines <input name="permission"></label><br>
    <label>Optional earlier validity (Oman time) <input type="datetime-local" name="validity"></label>
    <button>Prepare quote revision</button></form><h2>History</h2><ul>{history}</ul>'''


@router.post(PREFIX)
async def prepare(enquiry_id: int, request: Request):
    form = await request.form()
    chosen = set(form.getlist('lines'))
    with connect() as db:
        enquiry = intake(db, enquiry_id)
        _, lines = current(db, enquiry)
        now = datetime.now(GST)
        live = sources(db, enquiry, lines, now)
        if form.get('token') != fingerprint([lines, live]):
            raise HTTPException(409, 'Reload the quotation workspace.')
        if not chosen or chosen - live.keys():
            raise HTTPException(422, 'Select lines with current eligible offers.')
        pending = [str(line['line_number']) for line in lines if line['id'] not in chosen]
        permission = str(form.get('permission', '')).strip()
        if pending and not permission:
            raise HTTPException(422, 'Record customer permission covering the selected subset.')
        items = []
        try:
            for line in lines:
                key = line['id']
                if key in chosen:
                    override = str(form.get(f'price_{key}', '')).strip()
                    reason = str(form.get('price_reason', '')).strip()
                    if override and not reason:
                        raise ValueError('Explain the price override.')
                    items.append({'source': live[key], 'reason': reason if override else '',
                                  'price': price_line(line['quantity'], Decimal(live[key]['total']), override)})
            limit = min(datetime.fromisoformat(item['source']['validity']) for item in items)
            entered = str(form.get('validity', '')).strip()
            validity = datetime.fromisoformat(entered).replace(tzinfo=GST) if entered else limit
            if not now < validity <= limit:
                raise ValueError('Validity must be in the future and within all selected offers.')
        except (ValueError, InvalidOperation) as error:
            raise HTTPException(422, str(error))
        customer = parseaddr(enquiry['source']['sender'])[1]
        if '@' not in customer:
            raise HTTPException(422, 'A customer email address is required.')
        snapshot = {'customer': customer, 'items': items, 'pending': pending, 'permission': permission,
                    'validity': validity.isoformat(), 'requirements': fingerprint(lines),
                    'target_margin': str(TARGET), 'margin_floor': str(FLOOR),
                    'total': f"{sum(Decimal(item['price']['total']) for item in items):.3f}"}
        previous = db.execute(
            'SELECT revision,snapshot,issued_at FROM customer_quote WHERE enquiry_id=%s ORDER BY revision DESC LIMIT 1',
            (enquiry_id,),
        ).fetchone()
        if previous and previous['snapshot'] == snapshot and not previous['issued_at']:
            revision = previous['revision']
        else:
            revision = previous['revision'] + 1 if previous else 1
            pdf, email = render(snapshot, f'Q-{enquiry_id}-R{revision}')
            db.execute('INSERT INTO customer_quote (enquiry_id,revision,snapshot,pdf,email) VALUES (%s,%s,%s,%s,%s)',
                       (enquiry_id, revision, Jsonb(snapshot), pdf, email))
    return RedirectResponse(f'/enquiries/{enquiry_id}/quotes/{revision}', status_code=303)


@router.get(PREFIX + '/{revision}', response_class=HTMLResponse)
def review_quote(enquiry_id: int, revision: int):
    with connect() as db:
        enquiry = intake(db, enquiry_id)
        quote = locate(db, enquiry_id, revision)
        latest_issue = db.execute('SELECT max(revision) AS latest FROM customer_quote WHERE enquiry_id=%s AND issued_at IS NOT NULL',
                                  (enquiry_id,)).fetchone()['latest']
    base = f'/enquiries/{enquiry_id}/quotes/{revision}'
    snapshot = quote['snapshot']
    details = ''.join(
        f'<li>Line {escape(str(item["source"]["line"]["line_number"]))} · '
        f'Supplier {escape(item["source"]["supplier"])} · Cost {escape(item["source"]["total"])} · '
        f'Selling total {item["price"]["total"]} · Margin {Decimal(item["price"]["margin"]):.2%} '
        f'{"· Exception required" if item["price"]["below_floor"] else ""} '
        f'{escape(item["reason"])} · <a href="/supplier-replies/{item["source"]["reply_id"]}/source">Offer evidence</a></li>'
        for item in snapshot['items']
    )
    status = 'Superseded' if quote['issued_at'] and latest_issue > revision else (
        'Issued' if quote['issued_at'] else 'Approved' if quote['approved_at'] else 'Draft')
    actions = ''
    if not quote['approved_at']:
        actions = f'''<form method="post" action="{base}/approve">
        <label><input name="manager_exception" value="true" type="checkbox">Manager authorises exception (demo)</label><br>
        <label>Manager exception reason <input name="reason"></label>
        <label><input name="reviewed" value="true" type="checkbox" required>Reviewed exact PDF and recipient</label>
        <button>Approve quotation</button></form>'''
    elif not quote['issued_at']:
        actions = f'''<a href="{base}/email">Download customer email draft</a>
        <form method="post" action="{base}/issue"><label>Sent message reference <input name="reference"></label>
        <label><input name="sent" type="checkbox" value="true" required>I sent this exact revision</label>
        <button>Record issuance</button></form>'''
    if quote['issued_at']:
        actions = f'''<form method="post" action="{base}/purchase">
        <label>Line <select name="line_id">{''.join(
          f'<option value="{escape(item["source"]["line"]["id"], quote=True)}">{escape(str(item["source"]["line"]["line_number"]))}</option>'
          for item in snapshot["items"])}</select></label>
        <label>Purchase evidence reference <input name="reference" required></label>
        <label>Actual delivered cost OMR <input name="cost" required></label>
        <label>Actual pieces bought <input name="pieces" type="number" min="1" required></label>
        <label>Purchase date <input name="purchased_on" type="date" required></label>
        <button>Record confirmed purchase</button></form>'''
    return f'''<a href="/enquiries/{enquiry_id}/quotes">All revisions</a><h1>Quotation revision {revision}</h1>
    <p>{status} · Customer {escape(snapshot['customer'])} · OMR {snapshot['total']} excluding VAT</p>
    <p>Pending: {escape(', '.join(snapshot['pending']))} · {escape(snapshot['permission'])}</p>
    <a href="{base}/pdf">Review customer PDF</a><ul>{details}</ul>{actions}'''


@router.post(PREFIX + '/{revision}/approve')
def approve(enquiry_id: int, revision: int, reviewed: bool = Form(), reason: str = Form(''),
            manager_exception: bool = Form(False)):
    with connect() as db:
        enquiry = intake(db, enquiry_id)
        quote = locate(db, enquiry_id, revision)
        if not quote['approved_at']:
            now = datetime.now(GST)
            revalidate(db, enquiry, quote, now)
            if not reviewed or (any(item['price']['below_floor'] for item in quote['snapshot']['items'])
                                and not (manager_exception and reason.strip())):
                raise HTTPException(422, 'Review the package and record any manager exception reason.')
            db.execute('UPDATE customer_quote SET approved_at=%s,exception_reason=%s WHERE enquiry_id=%s AND revision=%s',
                       (now, reason.strip(), enquiry_id, revision))
    return RedirectResponse(f'/enquiries/{enquiry_id}/quotes/{revision}', status_code=303)


@router.post(PREFIX + '/{revision}/issue')
def issue(enquiry_id: int, revision: int, sent: bool = Form(), reference: str = Form('')):
    with connect() as db:
        intake(db, enquiry_id)
        quote = locate(db, enquiry_id, revision)
        if not quote['released_at'] or not sent:
            raise HTTPException(422, 'Confirm manual sending of the approved revision.')
        if not quote['issued_at']:
            latest = db.execute('SELECT max(revision) AS revision FROM customer_quote WHERE enquiry_id=%s AND issued_at IS NOT NULL',
                                (enquiry_id,)).fetchone()['revision']
            if latest is not None and latest > revision:
                raise HTTPException(409, 'A later revision is already recorded as issued.')
            db.execute('UPDATE customer_quote SET issued_at=now(),sent_reference=%s WHERE enquiry_id=%s AND revision=%s',
                       (reference.strip(), enquiry_id, revision))
    return RedirectResponse(f'/enquiries/{enquiry_id}/quotes/{revision}', status_code=303)


@router.post(PREFIX + '/{revision}/purchase')
def purchase(enquiry_id: int, revision: int, line_id: str = Form(), reference: str = Form(),
             cost: Decimal = Form(), pieces: int = Form(), purchased_on: str = Form()):
    from datetime import date

    try:
        purchase_date = date.fromisoformat(purchased_on)
    except ValueError:
        raise HTTPException(422, 'Enter a valid purchase date.')
    if not reference.strip() or pieces <= 0 or not cost.is_finite() or not 0 < cost <= 10**9:
        raise HTTPException(422, 'Provide purchase evidence and positive actual cost and quantity.')
    with connect() as db:
        intake(db, enquiry_id)
        quote = locate(db, enquiry_id, revision)
        item = next((item for item in quote['snapshot']['items'] if item['source']['line']['id'] == line_id), None)
        if not quote['issued_at'] or not item:
            raise HTTPException(422, 'Select an issued quotation line.')
        details = {'cost_omr': str(cost), 'pieces': pieces, 'purchased_on': purchase_date.isoformat(),
                   'supplier': item['source']['supplier'], 'requirement': item['source']['line']}
        keys = (enquiry_id, revision, line_id, reference.strip())
        db.execute('INSERT INTO confirmed_purchase VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',
                   (*keys, Jsonb(details)))
        existing = db.execute('SELECT details FROM confirmed_purchase WHERE enquiry_id=%s AND revision=%s AND line_id=%s AND purchase_reference=%s', keys).fetchone()
        if existing['details'] != details:
            raise HTTPException(409, 'This purchase evidence reference already has different terms.')
    return RedirectResponse(f'/enquiries/{enquiry_id}/quotes/{revision}', status_code=303)


@router.get(PREFIX + '/{revision}/{kind}')
def download(enquiry_id: int, revision: int, kind: str):
    if kind not in {'pdf', 'email'}:
        raise HTTPException(404)
    with connect() as db:
        enquiry = intake(db, enquiry_id)
        quote = locate(db, enquiry_id, revision)
        if kind == 'email':
            if quote['issued_at']:
                raise HTTPException(409, 'This quotation is already issued. View its archived PDF.')
            if not quote['approved_at']:
                raise HTTPException(409, 'Approve the package first.')
            revalidate(db, enquiry, quote, datetime.now(GST))
            db.execute('UPDATE customer_quote SET released_at=now() WHERE enquiry_id=%s AND revision=%s AND released_at IS NULL',
                       (enquiry_id, revision))
    suffix, media = ('eml', 'message/rfc822') if kind == 'email' else ('pdf', 'application/pdf')
    return Response(quote[kind], media_type=media, headers={
        'Content-Disposition': f'attachment; filename="Q-{enquiry_id}-R{revision}.{suffix}"'
    })
