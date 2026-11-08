import re
from email.utils import parseaddr
from html import escape

from fastapi import APIRouter, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from psycopg.types.json import Jsonb

from .store import connect

review_router = APIRouter()
EDITABLE = ('description', 'specification', 'quantity', 'unit', 'substitution')
UNITS = {'EA', 'PC', 'PCS', 'BOX', 'PACK'}


def intake(db, enquiry_id):
    row = db.execute('SELECT * FROM enquiry_intake WHERE id=%s FOR UPDATE',
                     (enquiry_id,)).fetchone()
    if not row or row['candidate'] is None:
        raise HTTPException(404, 'No extracted enquiry found.')
    return row


def current(db, row):
    entry = db.execute(
        'SELECT version, snapshot FROM enquiry_review WHERE enquiry_id=%s ORDER BY version DESC LIMIT 1',
        (row['id'],),
    ).fetchone()
    if entry:
        return entry['version'], entry['snapshot']
    return 0, [{**line, 'status': 'needs review', 'source_id': row['id']}
               for line in row['candidate']['lines']]


def save(db, enquiry_id, version, lines, revision_id=None):
    db.execute(
        'INSERT INTO enquiry_review (enquiry_id,version,snapshot,revision_id) VALUES (%s,%s,%s,%s)',
        (enquiry_id, version + 1, Jsonb(lines), revision_id),
    )


def redirect(enquiry_id):
    return RedirectResponse(f'/enquiries/{enquiry_id}', status_code=303)


@review_router.post('/enquiries/{enquiry_id}/lines/{line_id}/review')
def decide(enquiry_id: int, line_id: str, version: int = Form(), decision: str = Form(),
           description: str = Form(''), specification: str = Form(''), quantity: str = Form(''),
           unit: str = Form(''), substitution: str = Form(''), reason: str = Form('')):
    with connect() as db:
        row = intake(db, enquiry_id)
        latest, lines = current(db, row)
        line = next((item for item in lines if item['id'] == line_id), None)
        if not line:
            raise HTTPException(404, 'Line not found.')
        if decision not in {'confirmed', 'awaiting clarification'}:
            raise HTTPException(422, 'Choose a review decision.')
        try:
            count = int(quantity) if quantity.strip() else None
        except ValueError:
            raise HTTPException(422, 'Quantity must be a whole number.')
        values = dict(description=description.strip() or None,
                      specification=specification.strip() or None, quantity=count,
                      unit=unit.strip().upper() or None, substitution=substitution.strip() or None)
        if decision == 'confirmed' and (
            not values['description'] or not values['specification']
            or not count or count < 0 or values['unit'] not in UNITS
        ):
            raise HTTPException(422, 'Confirm a description, specification, positive quantity and supported unit.')
        updated = {**line, **values, 'status': decision, 'reason': reason.strip()}
        if updated == line and latest in {version, version + 1}:
            return redirect(enquiry_id)
        if latest != version:
            raise HTTPException(409, 'This review is out of date. Reopen the enquiry.')
        if (decision == 'awaiting clarification' or any(line.get(k) != v for k, v in values.items())) and not reason.strip():
            raise HTTPException(422, 'Give a reason for the correction or clarification.')
        lines[lines.index(line)] = {**updated, 'requirement_version': latest + 1}
        save(db, enquiry_id, latest, lines)
    return redirect(enquiry_id)


def suggested_parent(db, row):
    source = row['source']
    headers = source.get('reply_headers', [])
    references = re.findall(r'<[^<>]+>', ' '.join(headers))
    sender = parseaddr(source['sender'])[1].lower()
    candidate = row['candidate']
    matches = db.execute("""
        SELECT id,source,candidate FROM enquiry_intake
        WHERE id <> %s AND candidate IS NOT NULL
          AND (message_key = ANY(%s) OR
               (candidate->>'customer_reference' = %s AND
                COALESCE(jsonb_array_length(source->'reply_headers'),0)=0))
    """, (row['id'], references, candidate.get('customer_reference'))).fetchall()
    ids = {m['id'] for m in matches if parseaddr(m['source']['sender'])[1].lower() == sender}
    return next(iter(ids)) if len(ids) == 1 else None


@review_router.post('/enquiries/{revision_id}/apply-revision')
def apply_revision(revision_id: int, parent_id: int = Form(), version: int = Form(),
                   scope_confirmed: bool = Form(False)):
    if parent_id == revision_id or not scope_confirmed:
        raise HTTPException(422, 'Confirm the parent enquiry and listed-line revision scope.')
    with connect() as db:
        # Lock in a consistent order for simultaneous revision submissions.
        records = {id_: intake(db, id_) for id_ in sorted((parent_id, revision_id))}
        parent, revision = records[parent_id], records[revision_id]
        applied = db.execute('SELECT enquiry_id FROM enquiry_review WHERE revision_id=%s',
                             (revision_id,)).fetchone()
        if applied:
            if applied['enquiry_id'] == parent_id:
                return redirect(parent_id)
            raise HTTPException(409, 'This revision is already linked to another enquiry.')
        latest, lines = current(db, parent)
        if latest != version:
            raise HTTPException(409, 'The parent changed. Recheck the revision preview.')
        if parseaddr(parent['source']['sender'])[1].lower() != parseaddr(revision['source']['sender'])[1].lower():
            raise HTTPException(422, 'The revision sender differs from the original customer.')
        shared_fields = ('quote_deadline', 'delivery_deadline', 'partial_quote_permission')
        if any(revision['candidate'].get(field) is not None
               and revision['candidate'][field] != parent['candidate'].get(field)
               for field in shared_fields):
            raise HTTPException(422, 'Shared terms may have changed. Resolve them before applying a line-only revision.')
        changes = revision['candidate']['lines']
        if not changes:
            raise HTTPException(422, 'No revision lines were extracted.')
        updates = {}
        for change in changes:
            matches = [line for line in lines if change['line_number']
                       and line['line_number'] == change['line_number']]
            if len(matches) != 1 or matches[0]['id'] in updates:
                raise HTTPException(422, 'The revised line reference is missing or ambiguous.')
            previous = matches[0]
            updates[previous['id']] = {**change, 'id': previous['id'], 'status': 'needs review',
                                       'source_id': revision_id, 'requirement_version': latest + 1}
        save(db, parent_id, latest, [updates.get(line['id'], line) for line in lines], revision_id)
    return redirect(parent_id)


@review_router.get('/enquiries/{revision_id}/revision-preview')
def revision_preview(revision_id: int, parent_id: int):
    if parent_id == revision_id:
        raise HTTPException(422, 'Select the original enquiry.')
    with connect() as db:
        parent = intake(db, parent_id)
        revision = intake(db, revision_id)
        version, lines = current(db, parent)
    rows = []
    for change in revision['candidate']['lines']:
        before = [line for line in lines if change['line_number'] and line['line_number'] == change['line_number']]
        old = before[0] if len(before) == 1 else {}
        details = ''.join(f'<li>{key}: {escape(str(old.get(key)))} → {escape(str(change.get(key)))}</li>'
                          for key in EDITABLE)
        rows.append(f"<h3>Line {escape(str(change['line_number']))}</h3><ul>{details}</ul>")
    return HTMLResponse(f'''<h1>Review revision for enquiry {parent_id}</h1>
    <p>Original: {escape(parent['source']['subject'])}</p>
    <p>Revision: {escape(revision['source']['subject'])}</p>
    <a href="/enquiries/{revision_id}">Inspect revision email and PDF</a>
    {''.join(rows)}
    <form method="post" action="/enquiries/{revision_id}/apply-revision">
    <input type="hidden" name="parent_id" value="{parent_id}">
    <input type="hidden" name="version" value="{version}">
    <label><input type="checkbox" name="scope_confirmed" value="true" required>
    Apply the listed lines only. Confirm shared deadlines and terms are unchanged.</label>
    <button>Apply revision</button></form>''')


def review_controls(row):
    if not row['candidate']:
        return ''
    enquiry_id = row['id']
    with connect() as db:
        version, lines = current(db, row)
        parent_id = suggested_parent(db, row)
        history = db.execute(
            'SELECT version,snapshot FROM enquiry_review WHERE enquiry_id=%s ORDER BY version DESC',
            (enquiry_id,),
        ).fetchall()
    forms = []
    for line in lines:
        inputs = ''.join(
            f'<label>{key.title()} <input name="{key}" value="{escape(str(line.get(key) or ""), quote=True)}"></label><br>'
            for key in EDITABLE
        )
        forms.append(f'''<form method="post" action="/enquiries/{enquiry_id}/lines/{line['id']}/review">
        <h3>Line {escape(str(line['line_number']))} · {escape(line['status'])}</h3>
        <a href="/enquiries/{line['source_id']}">Source email and PDF</a><br>
        <a href="/enquiries/{enquiry_id}/lines/{line['id']}/suppliers">Supplier selection and history</a><br>
        <input type="hidden" name="version" value="{version}">
        {inputs}<label>Reason <input name="reason" value="{escape(line.get('reason', ''), quote=True)}"></label>
        <button name="decision" value="confirmed">Confirm line</button>
        <button name="decision" value="awaiting clarification">Await clarification</button></form>''')
    versions = ''.join(
        f"<details><summary>Review version {entry['version']}</summary><ul>"
        + ''.join(
            f"<li>Line {escape(str(line['line_number']))}: {escape(str(line.get('description')))} · "
            f"{escape(str(line.get('specification')))} · {escape(str(line.get('quantity')))} "
            f"{escape(str(line.get('unit')))} · {escape(line['status'])} "
            f"{escape(line.get('reason', ''))} <a href='/enquiries/{line['source_id']}'>Source</a></li>"
            for line in entry['snapshot']
        ) + '</ul></details>'
        for entry in history
    )
    return f'''<section><h2>Buyer decisions</h2>{''.join(forms)}
    <h2>Review history</h2>{versions}
    <h2>Link a customer revision</h2>
    <form action="/enquiries/{enquiry_id}/revision-preview">
    <label>Original enquiry ID <input type="number" name="parent_id" value="{parent_id or ''}" required></label>
    <button>Preview revision</button></form></section>'''
