from datetime import datetime
from decimal import Decimal
from email import policy
from email.parser import BytesParser
from pathlib import Path

import pytest

from enquiry.offers import GST, compare, read_terms

FIXTURES = Path('artifacts/trading-fixtures/cases/practice/shutdown')
LINE = {'description': 'Hex bolt', 'specification': 'M10 x 50 A2-70', 'unit': 'EA', 'quantity': 500}
NOW = datetime(2026, 11, 9, tzinfo=GST)
DEADLINE = datetime(2026, 11, 12, 14, tzinfo=GST)


@pytest.mark.parametrize(('pattern', 'expected'), [
    ('05-*.eml', '210.000'), ('06-*.eml', '340.000'), ('10-*.eml', '170.000'),
    ('14-*.eml', '165.000'),
])
def test_supplier_workbook_commercial_cost(pattern, expected):
    raw = next(FIXTURES.glob(pattern)).read_bytes()
    message = BytesParser(policy=policy.default).parsebytes(raw)
    terms = read_terms(next(message.iter_attachments()).get_payload(decode=True))
    assert compare(LINE, terms, DEADLINE, NOW)['total'] == Decimal(expected)


def test_missing_pack_size_stays_unresolved():
    raw = next(FIXTURES.glob('11-*.eml')).read_bytes()
    message = BytesParser(policy=policy.default).parsebytes(raw)
    terms = read_terms(next(message.iter_attachments()).get_payload(decode=True))
    with pytest.raises(ValueError, match='pack size'):
        compare(LINE, terms, DEADLINE, NOW)
