from decimal import Decimal

from enquiry.quotes import price_line


def test_shutdown_target_totals_and_margin_exception():
    line20 = price_line(200, Decimal('100.000'))
    for cost, total in [('210.000', '387.500'), ('170.000', '337.500')]:
        line10 = price_line(500, Decimal(cost))
        assert Decimal(line10['total']) + Decimal(line20['total']) == Decimal(total)
        assert Decimal(line10['margin']) >= Decimal('0.20')
    discounted = price_line(500, Decimal('210.000'), '0.480')
    assert discounted['total'] == '240.000'
    assert Decimal(discounted['margin']) == Decimal('0.125')
    assert discounted['below_floor']


def test_rounding_preserves_target_margin():
    result = price_line(3, Decimal('1.000'))
    assert result['unit_price'] == '0.417'
    assert result['total'] == '1.251'
    assert Decimal(result['margin']) >= Decimal('0.20')
