import re

def validate_regex(pattern):
    try:
        re.compile(pattern)
        return True
    except re.error:
        return False
