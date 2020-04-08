"""
MarkdownX is licensed under the 2-clause BSD license, and Open Source Initiative approved license.
Copyright (c) 2016, Adrian Drzewicki (adriandrzewicki@gmail.com)
All rights reserved.
"""

from django import template
from markdownx.utils import markdownify

register = template.Library()

@register.filter
def show_markdown(value):
    return markdownify(value)