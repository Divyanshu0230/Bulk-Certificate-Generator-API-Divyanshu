import re

DEFAULT_DESCRIPTION = "has successfully completed"
DEFAULT_SIGNATORY_TITLE = "Authorized signatory"
CERTIFICATE_NUMBER_RE = re.compile(r"^CERT-\d{4}-[A-F0-9]{12}$")
