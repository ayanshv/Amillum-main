"""Persist exclusions, never application activity or screen/document content."""

import json
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import urlsplit


# Defense in depth: app-level exclusions precede any future field inspection.
PROTECTED_APPLICATIONS = frozenset({
    'com.apple.Passwords', 'com.apple.keychainaccess',
    'com.1password.1password', 'com.agilebits.onepassword7',
    'com.bitwarden.desktop', 'com.lastpass.LastPass', 'com.dashlane.Dashlane',
    'com.keepassxc.keepassxc',
})


def valid_bundle_id(value):
    return isinstance(value, str) and len(value) <= 180 and bool(re.fullmatch(r'[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*', value))


def normalize_domain(value):
    value = value.strip().lower().rstrip('.')
    if not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?', value) or '.' not in value or len(value) > 253 or '..' in value:
        raise ValueError('Enter a domain such as example.com, without a URL path.')
    return value


def domain_excluded(url, excluded):
    host = (urlsplit(url).hostname or '').lower().rstrip('.')
    return any(host == domain or host.endswith('.' + domain) for domain in excluded)


class PrivacyPreferences:
    def __init__(self, path=None):
        self.path = Path(path) if path else Path.home() / 'Library/Application Support/Amillum/privacy.json'
        self.excluded = set()
        self.domains = set()
        self.load_error = False
        try:
            if self.path.exists():
                data = json.loads(self.path.read_text())
                if not isinstance(data, dict) or not isinstance(data.get('excluded'), list):
                    raise ValueError('Invalid privacy preferences')
                if len(data['excluded']) > 64 or not all(valid_bundle_id(item) for item in data['excluded']):
                    raise ValueError('Invalid application identifier')
                self.excluded = set(data['excluded'])
                domains = data.get('domains', [])
                if not isinstance(domains, list) or len(domains) > 64 or not all(isinstance(v, str) and normalize_domain(v) == v for v in domains):
                    raise ValueError('Invalid domains')
                self.domains = set(domains)
        except (OSError, ValueError, TypeError):
            # Do not quietly discard exclusions and allow awareness to start.
            self.load_error = True

    def save(self, excluded, domains=None):
        domains = self.domains if domains is None else domains
        if len(domains) > 64:
            raise ValueError("You can exclude up to 64 domains.")
        if len(excluded) > 64:
            raise ValueError('You can add up to 64 application exclusions.')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix='.privacy-', dir=str(self.path.parent))
        try:
            with os.fdopen(fd, 'w') as stream:
                json.dump({'version': 1, 'excluded': sorted(excluded), 'domains': sorted(domains)}, stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            self.excluded = set(excluded)
            self.domains = set(domains)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


# Local safeguards only. Matched values never enter logs or error messages.
def sensitive_text_reason(text):
    if not isinstance(text, str):
        return 'invalid_content'
    if re.search(r'-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----', text, re.I):
        return 'private_key'
    if re.search(r'\b(?:password|passcode|api[_ -]?key|secret[_ -]?key|access[_ -]?token|recovery[_ -]?(?:code|phrase)|seed phrase|cvv|cvc|security code|verification code|one[- ]time (?:code|password)|bank (?:login|password))\s*[:=]\s*\S+', text, re.I):
        return 'credentials_or_security_code'
    for candidate in re.findall(r'(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)', text):
        digits=[int(c) for c in candidate if c.isdigit()]
        if len(set(digits)) < 2:
            continue
        total=0
        for i,n in enumerate(reversed(digits)):
            if i % 2:
                n*=2
                if n>9: n-=9
            total+=n
        if total % 10 == 0:
            return 'payment_card'
    return None


def require_safe_text(text):
    if sensitive_text_reason(text):
        raise ValueError('This content may contain credentials, security codes, payment details, or a private key. It was not sent for analysis. Select a different passage.')
