"""
Template helper that renders a form field with Bootstrap CSS classes.

Usage in a template:  {% load form_tags %}  {{ form.hours|bootstrap }}
"""

from django import forms, template

register = template.Library()


@register.filter
def bootstrap(field):
    widget = field.field.widget
    if isinstance(widget, forms.CheckboxInput):
        css = "form-check-input"
    elif isinstance(widget, forms.Select):
        css = "form-select"
    else:
        css = "form-control"
    if field.errors:
        css += " is-invalid"
    return field.as_widget(attrs={"class": css})


@register.filter
def is_checkbox(field):
    return isinstance(field.field.widget, forms.CheckboxInput)
