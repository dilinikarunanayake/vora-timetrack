"""
Optional images ("image slots").

    {% optional_image "img/photos/team" as team_photo %}
    {% if team_photo %}<img src="{{ team_photo }}" ...>{% endif %}

Looks for img/photos/team.svg / .png / .webp / .jpg / .jpeg in the static
folder. Drop a file with that name in place and it appears on the site; take
it away and the page falls back to the built-in illustration or text.
"""

from django import template
from django.contrib.staticfiles import finders
from django.templatetags.static import static

register = template.Library()

EXTENSIONS = ("svg", "png", "webp", "jpg", "jpeg")


@register.simple_tag
def optional_image(basename):
    for ext in EXTENSIONS:
        path = f"{basename}.{ext}"
        if finders.find(path):
            return static(path)
    return ""
