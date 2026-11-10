import hashlib
import math
import os
import re
from datetime import date
from decimal import Decimal
from statistics import median
from typing import Literal

import psycopg
from fastapi import APIRouter
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from .store import connect
from .suppliers import classify

router = APIRouter()
BUDGET = 25
BASIS = 'delivered_omr_ex_vat'


class HistoryRecord(BaseModel):
    id: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=1, max_length=1000)
    kind: Literal['purchase', 'offer', 'quote']
    spec: str | None = None
    verified: bool = False
    date: date
    pieces: int = Field(gt=0)
    price: Decimal = Field(gt=0, allow_inf_nan=False)
    pack: int | None = Field(default=None, gt=0)
    basis: str


def signature(line):
    text = ' '.join(line.get(key) or '' for key in ('description', 'specification'))
    family, grade = classify(line)
    dimensions = set(re.findall(r'\bm\s*(\d+)\s*(?:mm)?(?:\s*[x×]\s*(\d+))?', text.lower()))
    if not family or not grade or len(dimensions) != 1 or line.get('substitution'):
        return None
    # Standards, brands and extra constraints need independently verified history fields.
    if re.search(r'\b(?:DIN|ISO|ASTM|ASME|ANSI|EN|brand|origin|thread|coating)\b', text, re.I):
        return None
    diameter, length = next(iter(dimensions))
    return f'{family}|{diameter}|{length}|{grade}'


def vector(text):
    normal = re.sub(r'[^a-z0-9]', '', text.casefold().replace('stainless steel', 'ss')
                    .replace('stainless', 'ss').replace('hex head', 'hex').replace('screw', 'bolt')
                    .replace('×', 'x'))
    bins = [0] * 128
    for index in range(len(normal) - 2):
        gram = normal[index:index + 3].encode()
        bins[hashlib.blake2b(gram, digest_size=1).digest()[0] % len(bins)] += 1
    norm = math.sqrt(sum(count * count for count in bins)) or 1
    return '[' + ','.join(str(count / norm) for count in bins) + ']'


def vector_enabled(db):
    return db.execute("SELECT to_regtype('vector') IS NOT NULL AS enabled").fetchone()['enabled']


@router.post('/history/import')
def import_history(records: list[HistoryRecord]):
    with connect() as db:
        for record in records:
            data = record.model_dump(mode='json')
            data['vector'] = vector(record.description)
            db.execute("""
                INSERT INTO historical_price (source_id,record) VALUES (%s,%s)
                ON CONFLICT (source_id) DO UPDATE SET record=excluded.record
                WHERE historical_price.record IS DISTINCT FROM excluded.record
            """, ('legacy:' + record.id, Jsonb(data)))
    return {'processed': len(records)}


def candidates(db, spec, description):
    exact = db.execute("""
        SELECT source_id, record FROM historical_price
        WHERE record->>'spec'=%s AND record->>'verified'='true'
        ORDER BY source_id LIMIT %s
    """, (spec, BUDGET)).fetchall()
    nearest = []
    remaining = BUDGET - len(exact)
    if remaining and vector_enabled(db):
        nearest = db.execute("""
            SELECT source_id,record FROM historical_price
            WHERE record ? 'vector' AND NOT (source_id = ANY(%s))
            ORDER BY (record->>'vector')::vector <=> %s::vector, source_id LIMIT %s
        """, ([row['source_id'] for row in exact], vector(description), remaining)).fetchall()
    purchases = db.execute("""
        SELECT DISTINCT ON (enquiry_id,line_id,purchase_reference)
               enquiry_id,line_id,purchase_reference,details
        FROM confirmed_purchase
        ORDER BY enquiry_id,line_id,purchase_reference,revision DESC
    """).fetchall()
    native = []
    for row in purchases:
        details = row['details']
        line = details['requirement']
        if signature(line) != spec:
            continue
        source_id = f"purchase:{row['enquiry_id']}:{row['line_id']}:{row['purchase_reference']}"
        native.append({'source_id': source_id, 'record': {
            'kind': 'purchase', 'verified': True, 'spec': spec, 'basis': BASIS,
            'date': details['purchased_on'], 'pieces': details['pieces'],
            'price': details['cost_omr'], 'pack': details['pieces'],
            'description': line['description'],
        }})
    return native[:BUDGET] + (exact + nearest)[:max(0, BUDGET - len(native))]


def benchmark(rows, spec, quantity, current_price, today, months=12,
              lower=Decimal('0.5'), upper=Decimal('2')):
    year, month = divmod(today.year * 12 + today.month - 1 - months, 12)
    from calendar import monthrange

    start = date(year, month + 1, min(today.day, monthrange(year, month + 1)[1]))
    included, excluded = [], []
    for row in rows:
        record = row['record']
        if record['kind'] != 'purchase':
            reason = 'Not a confirmed purchase'
        elif not record['verified'] or record['spec'] != spec:
            reason = 'Critical specification differs or is unverified'
        elif record['basis'] != BASIS or not record['pack']:
            reason = 'Delivered price or pack conversion is unverified'
        elif not start <= date.fromisoformat(record['date']) <= today:
            reason = 'Outside the purchase date window'
        elif not quantity * lower <= record['pieces'] <= quantity * upper:
            reason = 'Outside the purchase quantity window'
        else:
            included.append({'id': row['source_id'], 'description': record['description'],
                             'date': record['date'], 'pieces': record['pieces'],
                             'unit_price': Decimal(record['price']) / record['pack']})
            continue
        excluded.append({'id': row['source_id'], 'reason': reason})
    result = {'status': 'insufficient history', 'included': included, 'excluded': excluded,
              'months': months, 'lower': lower, 'upper': upper, 'flag': False}
    if len(included) >= 3:
        midpoint = median(row['unit_price'] for row in included)
        difference = (current_price - midpoint) / midpoint * 100
        result.update(status='available', median=midpoint, difference=difference,
                      flag=abs(difference) > 25)
    return result


def for_offer(line, quantity, price, today):
    spec = signature(line)
    if not spec:
        return {'status': 'insufficient verified specifications'}
    try:
        with connect() as db:
            rows = candidates(db, spec, line['description'] + ' ' + line['specification'])
        return benchmark(rows, spec, quantity, price, today,
                         months=int(os.getenv('HISTORY_LOOKBACK_MONTHS', '12')),
                         lower=Decimal(os.getenv('HISTORY_QUANTITY_MIN', '0.5')),
                         upper=Decimal(os.getenv('HISTORY_QUANTITY_MAX', '2')))
    except psycopg.Error:
        return {'status': 'history unavailable'}


@router.get('/history/evidence')
def evidence(source_id: str):
    with connect() as db:
        row = db.execute('SELECT record - \'vector\' AS record FROM historical_price WHERE source_id=%s',
                         (source_id,)).fetchone()
        if row:
            return row['record']
        if source_id.startswith('purchase:'):
            try:
                _, enquiry, line, reference = source_id.split(':', 3)
                enquiry_id = int(enquiry)
            except ValueError:
                enquiry_id = None
            row = db.execute("""
                SELECT details FROM confirmed_purchase
                WHERE enquiry_id=%s AND line_id=%s AND purchase_reference=%s
                ORDER BY revision DESC LIMIT 1
            """, (enquiry_id, line if enquiry_id is not None else '', reference if enquiry_id is not None else '')).fetchone()
            if row:
                return row['details']
    from fastapi import HTTPException
    raise HTTPException(404, 'Historical record not found.')
