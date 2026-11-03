"""
{{ amount|money }}  ->  £1,234.50   (currency symbol comes from settings)
{{ hours|hours }}   ->  1,234.50
"""

from decimal import Decimal, InvalidOperation

from django import template
from django.conf import settings

register = template.Library()


@register.filter
def money(value):
    try:
        return f"{settings.BILLING_CURRENCY_SYMBOL}{Decimal(value):,.2f}"
    except (InvalidOperation, TypeError, ValueError):
        return "–"


@register.filter
def hours(value):
    try:
        return f"{Decimal(value or 0):,.2f}"
    except (InvalidOperation, TypeError, ValueError):
        return "–"
