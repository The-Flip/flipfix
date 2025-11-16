from django import template
from django.utils import timezone
from django.utils.html import format_html

register = template.Library()


@register.filter
def smart_date(value):
    if not value:
        return ""
    if timezone.is_naive(value):
        value = timezone.make_aware(value)
    iso_format = value.isoformat()
    return format_html(
        '<time datetime="{}" class="smart-date">{}</time>',
        iso_format,
        iso_format,
    )
