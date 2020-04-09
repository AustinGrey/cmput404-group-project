"""
Utilities for working with Author IDs, that may be needed by multiple files
"""
import re

def author_id_strip_dashes(author_id):
    """
    Given an author id of the form {service}/author/{uuid},
    safely convert the uuid of form xxxxx-xxxx-xxxx-xxxxxxxxxxxxxxxxxxxxx to one without dashes
    """
    author_dash_free = author_id.split('/')
    author_dash_free[-1] = re.sub('-', '', author_dash_free[-1])
    author_dash_free = '/'.join(author_dash_free)
    return author_dash_free
