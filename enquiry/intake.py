import hashlib
import io
from email import policy
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
from pathlib import Path

from pypdf import PdfReader


def parse_email(raw):
    message = BytesParser(policy=policy.default).parsebytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    body = message.get_body(preferencelist=('plain', 'html'))
    source = {
        'sender': str(message.get('From', '')),
        'subject': str(message.get('Subject', '')),
        'date': str(message.get('Date', '')),
        'body': body.get_content() if body else '',
    }
    return str(message.get('Message-ID') or digest).strip(), digest, source


def read_pdf(raw):
    message = BytesParser(policy=policy.default).parsebytes(raw)
    pdfs = [part for part in message.iter_attachments()
            if Path(part.get_filename() or '').suffix.lower() == '.pdf']
    if len(pdfs) != 1:
        raise ValueError('Expected exactly one requirement PDF. Check the original email.')
    data = pdfs[0].get_payload(decode=True)
    if not data or not data.startswith(b'%PDF-'):
        raise ValueError('The attachment is not a readable PDF.')
    reader = PdfReader(io.BytesIO(data))
    if reader.is_encrypted or len(reader.pages) > 25:
        raise ValueError('The PDF is encrypted or exceeds the 25-page limit.')
    pages = [page.extract_text() for page in reader.pages]
    if not any(page.strip() for page in pages):
        raise ValueError('The PDF has no readable text.')
    return data, pages


def dated_source(source):
    timestamp = parsedate_to_datetime(source['date'])
    if timestamp.tzinfo is None:
        raise ValueError('The email timestamp has no time zone.')
    return timestamp
