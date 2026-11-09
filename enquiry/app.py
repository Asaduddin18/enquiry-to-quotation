from contextlib import asynccontextmanager
from html import escape

import httpx
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from psycopg.types.json import Jsonb
from pydantic import ValidationError
from pypdf.errors import PdfReadError

from .extraction import deepseek, review
from .intake import parse_email, read_pdf
from .store import connect, initialize
from .suppliers import supplier_router
from .rfq import router as rfq_router
from .offers import router as offers_router
from .quotes import router as quote_router
from .requirements_review import review_router, review_controls

MAX_EMAIL = 10 * 1024 * 1024


@asynccontextmanager
async def lifespan(app):
    initialize()
    yield


app = FastAPI(lifespan=lifespan)
app.state.extract = deepseek
app.include_router(review_router)
app.include_router(supplier_router)
app.include_router(rfq_router)
app.include_router(offers_router)
app.include_router(quote_router)


def load(enquiry_id):
    with connect() as db:
        row = db.execute('SELECT * FROM enquiry_intake WHERE id = %s', (enquiry_id,)).fetchone()
    if row is None:
        raise HTTPException(404, 'Enquiry not found.')
    return row


def process(enquiry_id):
    with connect() as db:
        row = db.execute(
            'SELECT * FROM enquiry_intake WHERE id = %s FOR UPDATE', (enquiry_id,)
        ).fetchone()
        if row['status'] not in {'received', 'retry'}:
            return
        candidate = None
        try:
            _, pages = read_pdf(row['raw_email'])
        except (ValueError, PdfReadError) as error:
            status, issues = 'needs source review', [str(error)]
        else:
            try:
                result = app.state.extract(row['source'], pages)
                issues = review(result, row['source'], pages)
                candidate = result.model_dump(mode='json')
                for index, line in enumerate(candidate['lines'], 1):
                    line['id'] = f'{enquiry_id}-{index}'
                status = 'ready for buyer review'
            except (httpx.HTTPError, ValidationError, RuntimeError, ValueError, KeyError, IndexError):
                status, issues = 'retry', ['Extraction could not complete. Check model configuration and retry.']
        db.execute(
            'UPDATE enquiry_intake SET status=%s, candidate=%s, issues=%s WHERE id=%s',
            (status, Jsonb(candidate), Jsonb(issues), enquiry_id),
        )
        db.execute(
            'INSERT INTO enquiry_extraction_attempt (enquiry_id,status,issues) VALUES (%s,%s,%s)',
            (enquiry_id, status, Jsonb(issues)),
        )


@app.get('/', response_class=HTMLResponse)
def home():
    return '''<h1>Import customer enquiry</h1>
    <form action="/enquiries/import" method="post" enctype="multipart/form-data">
    <input type="file" name="email" accept=".eml" required><button>Import</button></form>'''


@app.post('/enquiries/import')
def import_enquiry(email: UploadFile):
    raw = email.file.read(MAX_EMAIL + 1)
    if not raw or len(raw) > MAX_EMAIL:
        raise HTTPException(413, 'Upload a non-empty email up to 10 MiB.')
    key, digest, source = parse_email(raw)
    if not source['sender'] or not source['date']:
        raise HTTPException(422, 'Email must have From and Date headers.')
    with connect() as db:
        db.execute(
            'INSERT INTO enquiry_intake (message_key,digest,raw_email,source) '
            'VALUES (%s,%s,%s,%s) ON CONFLICT (message_key) DO NOTHING',
            (key, digest, raw, Jsonb(source)),
        )
        row = db.execute('SELECT id,digest,status FROM enquiry_intake WHERE message_key=%s', (key,)).fetchone()
    if row['digest'] != digest:
        raise HTTPException(409, 'Message ID already exists with different content. Review both emails.')
    if row['status'] == 'received':
        process(row['id'])
    return RedirectResponse(f"/enquiries/{row['id']}", status_code=303)


@app.post('/enquiries/{enquiry_id}/retry')
def retry(enquiry_id: int):
    load(enquiry_id)
    process(enquiry_id)
    return RedirectResponse(f'/enquiries/{enquiry_id}', status_code=303)


@app.get('/enquiries/{enquiry_id}/pdf')
def pdf(enquiry_id: int):
    row = load(enquiry_id)
    try:
        data, _ = read_pdf(row['raw_email'])
    except (ValueError, PdfReadError):
        raise HTTPException(404, 'No readable PDF.')
    return Response(data, media_type='application/pdf', headers={'X-Content-Type-Options': 'nosniff'})


@app.get('/enquiries/{enquiry_id}', response_class=HTMLResponse)
def enquiry(enquiry_id: int):
    row = load(enquiry_id)
    source = row['source']
    candidate = row['candidate'] or {}

    def fields(record):
        parts = []
        for key, value in record.items():
            if key in {'id', 'lines', 'evidence', 'conflicts'} or value is None:
                continue
            evidence = record.get('evidence', {}).get(key)
            citation = ''
            if evidence:
                location = f"PDF page {evidence['page']}" if evidence['source'] == 'pdf' else 'Email'
                citation = f"<small>{escape(location)} · {escape(evidence['excerpt'])}</small>"
            parts.append(f'<dt>{escape(key.replace("_", " ").title())}</dt><dd>{escape(str(value))} {citation}</dd>')
        return '<dl>' + ''.join(parts) + '</dl>'

    issues = ''.join(f'<li>{escape(issue)}</li>' for issue in row['issues'])
    lines = ''.join(f'<section><h3>Candidate item</h3>{fields(line)}</section>' for line in candidate.get('lines', []))
    retry_form = f'<form method="post" action="{enquiry_id}/retry"><button>Retry extraction</button></form>' if row['status'] == 'retry' else ''
    return f'''<!doctype html><meta charset="utf-8"><title>Enquiry review</title>
    <style>body{{font:16px system-ui;max-width:75rem;margin:2rem auto;padding:0 1rem}}
    main{{display:grid;grid-template-columns:1fr 1fr;gap:2rem}}pre{{white-space:pre-wrap}}
    small{{display:block;color:#475569}}dt{{font-weight:bold}}dd{{margin:0 0 .6rem}}</style>
    <a href="/">Import another enquiry</a><h1>{escape(source['subject'])}</h1>
    <p>Status: {escape(row['status'])}. Candidate values require buyer confirmation.</p>
    {retry_form}<main><section><h2>Source email</h2><p>{escape(source['sender'])} · {escape(source['date'])}</p>
    <pre>{escape(source['body'])}</pre><a href="{enquiry_id}/pdf">Open requirement PDF</a></section>
    <section><h2>Review issues</h2><ul>{issues}</ul><h2>Candidate requirements</h2>
    {fields(candidate)}{lines}</section></main>{review_controls(row)}<p><a href="/enquiries/{enquiry_id}/quotes">Customer quotation workspace</a></p>'''
