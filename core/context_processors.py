"""
Makes the company details from settings.COMPANY available to every template
as {{ company.email }}, {{ company.phone_link }} and so on.
"""

import re
from urllib.parse import quote_plus

from django.conf import settings


def company(request):
    info = dict(settings.COMPANY)
    # "tel:" links need the number without spaces: +44 7404 741045 -> +447404741045
    info["phone_link"] = re.sub(r"[^0-9+]", "", info.get("phone", ""))
    info["map_url"] = "https://www.google.com/maps/search/?api=1&query=" + quote_plus(info.get("address", ""))
    return {"company": info}
