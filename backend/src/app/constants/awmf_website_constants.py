import re

DEFAULT_URL_AWMF_GUIDELINE_SEARCH = "https://register.awmf.org/de/suche#versionlabel=Guideline&doctype=longVersion&association=007&sorting=relevance"

PATTERN_GUIDELINE_DETAIL_PAGE = re.compile(r'^https://register\.awmf\.org/de/leitlinien/detail/\d{3}-\d{3}[A-Z]*$')
PATTERN_GUIDELINE_REGISTRATION_PAGE = re.compile(
    r'^https://register\.awmf\.org/de/leitlinien/detail/\d{3}-\d{3}[A-Z]*#anmeldung$',
)
