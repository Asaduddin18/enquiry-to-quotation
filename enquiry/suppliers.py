import csv
import hashlib
import json
import re
from html import escape
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from psycopg.types.json import Jsonb

from .requirements_review import current, intake
from .store import connect

supplier_router = APIRouter()
DATA = Path(__file__).resolve().parents[1] / 'artifacts/trading-fixtures/reference-data'
FAMILIES = {
    'HEX_BOLT': r'\bhex(?:[ -]head)?[ -]+bolts?\b',
    'LOCK_NUT': r'\b(?:lock[ -]?nuts?|locking[ -]nuts?)\b',
}
GRADES = {'A2-70': r'\bA2[ -]+70\b', 'A2': r'\bA2\b(?![ -]+70\b)',
          '8.8': r'(?<![\w.])8\.8(?![\w.])', '10.9': r'(?<![\w.])10\.9(?![\w.])'}


def classify(line):
    description = line.get('description') or ''
    combined = description + ' ' + (line.get('specification') or '')
    families = [key for key, pattern in FAMILIES.items() if re.search(pattern, combined, re.I)]
    grades = [key for key, pattern in GRADES.items() if re.search(pattern, combined, re.I)]
    return (families[0] if len(families) == 1 else '',
            grades[0] if len(grades) == 1 else '')


def load_directory():
    with (DATA / 'suppliers.csv').open(newline='') as file:
        directory = {row['supplier_id']: row for row in csv.DictReader(file)
                     if row.get('active', 'true').lower() == 'true'}
    with (DATA / 'supplier-coverage.csv').open(newline='') as file:
        coverage = {(row['supplier_id'], row['family'], row['grade'])
                    for row in csv.DictReader(file)}
    return directory, coverage


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def suggest(directory, coverage, family, grade):
    return {supplier for supplier in directory if (supplier, family, grade) in coverage}


def approval_context(db, enquiry_id, line_id):
    enquiry = intake(db, enquiry_id)
    _, lines = current(db, enquiry)
    line = next((line for line in lines if line['id'] == line_id), None)
    if line is None:
        raise HTTPException(404, 'Enquiry line not found.')
    approvals = db.execute(
        'SELECT * FROM supplier_approval WHERE enquiry_id=%s AND line_id=%s ORDER BY id DESC',
        (enquiry_id, line_id),
    ).fetchall()
    return line, approvals


def current_recipient_approval(line, approvals, directory):
    if line['status'] != 'confirmed' or not approvals:
        return None
    latest = approvals[0]
    if latest['requirement_key'] != fingerprint(line):
        return None
    if any(directory.get(recipient['id'], {}).get('email') != recipient['email']
           for recipient in latest['selection']['recipients']):
        return None
    return latest


def approval_token(line, directory, coverage, latest_id):
    return fingerprint([line, directory, sorted(coverage), latest_id])


def options(values, selected):
    return '<option value="">Select</option>' + ''.join(
        f'<option value="{key}" {"selected" if key == selected else ""}>{key}</option>'
        for key in values
    )


@supplier_router.get('/enquiries/{enquiry_id}/lines/{line_id}/suppliers', response_class=HTMLResponse)
def supplier_page(enquiry_id: int, line_id: str, family: str | None = None, grade: str | None = None):
    with connect() as db:
        line, approvals = approval_context(db, enquiry_id, line_id)
    directory, coverage = load_directory()
    ready = current_recipient_approval(line, approvals, directory)
    inferred_family, inferred_grade = classify(line)
    saved = ready['selection'] if ready else {}
    family = family if family in FAMILIES else saved.get('family', inferred_family)
    grade = grade if grade in GRADES else saved.get('grade', inferred_grade)
    suggested = suggest(directory, coverage, family, grade)
    checked = {recipient['id'] for recipient in ready['selection']['recipients']} if ready else suggested
    history = ''.join(
        f"<li>Approval {entry['id']}: "
        + escape(', '.join(recipient['email'] for recipient in entry['selection']['recipients']))
        + f" · {escape(entry['selection']['reason'])}</li>" for entry in approvals
    )
    header = f'''<h1>Supplier selection</h1><a href="/enquiries/{enquiry_id}">Back to enquiry</a>
    <p>{escape(str(line.get('description')))} · {escape(str(line.get('specification')))} ·
    {escape(str(line.get('quantity')))} {escape(str(line.get('unit')))}</p>'''
    if line['status'] != 'confirmed':
        return header + f'<p>Confirm the requirement before approving recipients.</p><ul>{history}</ul>'
    url = f'/enquiries/{enquiry_id}/lines/{line_id}/suppliers'
    choices = ''.join(
        f'<label><input type="checkbox" name="supplier_ids" value="{escape(key, quote=True)}" '
        f'{"checked" if key in checked else ""}>{escape(row["name"])} · {escape(row["email"])} · '
        f'{f"Covers {family} / {grade}" if key in suggested else "Outside suggested coverage"}</label><br>'
        for key, row in directory.items()
    )
    token = approval_token(line, directory, coverage, approvals[0]['id'] if approvals else None)
    rfq = f'<a href="{url.removesuffix("/suppliers")}/rfq">Prepare or review RFQ package</a>' if ready else ''
    return header + f'''{rfq}
    <form action="{url}">
      <label>Family <select name="family">{options(FAMILIES, family)}</select></label>
      <label>Grade <select name="grade">{options(GRADES, grade)}</select></label>
      <button>Refresh suggestions</button>
    </form>
    <p>{"Recipients approved" if ready else "Recipient approval required"}.
    {"No matching coverage. " if not suggested else ""}Confirm stock and terms in the RFQ.</p>
    <form method="post" action="{url}">
      <input type="hidden" name="token" value="{token}">
      <input type="hidden" name="family" value="{family}">
      <input type="hidden" name="grade" value="{grade}">
      {choices}
      <label>Override reason <input name="reason" value="{escape(ready['selection']['reason'] if ready else '', quote=True)}"></label>
      <button>Approve recipients</button>
    </form>
    <h2>Approval history</h2><ul>{history}</ul>'''


@supplier_router.post('/enquiries/{enquiry_id}/lines/{line_id}/suppliers')
def approve(enquiry_id: int, line_id: str, token: str = Form(), family: str = Form(''),
            grade: str = Form(''), supplier_ids: Annotated[list[str] | None, Form()] = None,
            reason: str = Form('')):
    with connect() as db:
        line, approvals = approval_context(db, enquiry_id, line_id)
        if line['status'] != 'confirmed':
            raise HTTPException(409, 'Confirm the requirement before approving recipients.')
        directory, coverage = load_directory()
        selected = set(supplier_ids or [])
        if family not in FAMILIES or grade not in GRADES or not selected or selected - directory.keys():
            raise HTTPException(422, 'Select a family, grade and at least one active supplier.')
        if selected - suggest(directory, coverage, family, grade) and not reason.strip():
            raise HTTPException(422, 'Give a reason for recipients outside suggested coverage.')
        selection = {'family': family, 'grade': grade, 'reason': reason.strip(),
                     'recipients': [{'id': key, 'email': directory[key]['email']} for key in sorted(selected)]}
        latest = approvals[0] if approvals else None
        ready = current_recipient_approval(line, approvals, directory)
        previous_id = approvals[1]['id'] if len(approvals) > 1 else None
        if ready and ready['selection'] == selection and token == approval_token(line, directory, coverage, previous_id):
            return RedirectResponse(f'/enquiries/{enquiry_id}/lines/{line_id}/suppliers', status_code=303)
        if token != approval_token(line, directory, coverage, latest['id'] if latest else None):
            raise HTTPException(409, 'The requirement, directory or approval changed. Reload the selection.')
        if not ready or ready['selection'] != selection:
            db.execute(
                'INSERT INTO supplier_approval (enquiry_id,line_id,requirement_key,selection) VALUES (%s,%s,%s,%s)',
                (enquiry_id, line_id, fingerprint(line), Jsonb(selection)),
            )
    return RedirectResponse(f'/enquiries/{enquiry_id}/lines/{line_id}/suppliers', status_code=303)
