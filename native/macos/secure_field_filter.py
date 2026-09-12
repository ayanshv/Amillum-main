"""Conservative structural filtering before any value or geometry access.

Metadata cannot prove that arbitrary text fields do not contain payment details,
codes, keys or credentials. Generic single-line inputs are therefore all blocked.
This filter does not inspect field values to decide whether they are sensitive.
"""

KNOWN_ROLES = frozenset({'AXTextArea', 'AXStaticText', 'AXGroup', 'AXWebArea',
                         'AXTextField', 'AXComboBox', 'AXSecureTextField', 'AXButton',
                         'AXCheckBox', 'AXPopUpButton', 'AXRadioButton', 'AXTable',
                         'AXScrollArea', 'AXLink', 'AXImage', 'AXList'})


def block_reason(role, subrole):
    if role == 'AXSecureTextField' or subrole == 'AXSecureTextField':
        return 'secure_field'
    if role in {'AXTextField', 'AXComboBox'}:
        return 'input_field'
    if role not in KNOWN_ROLES:
        return 'unknown_element'
    if subrole and ('secure' in str(subrole).lower() or 'password' in str(subrole).lower()):
        return 'secure_field'
    return None



def sensitive_metadata(values):
    import re
    text=' '.join(str(v)[:250] for v in values if v is not None)
    return bool(re.search(r'password|passcode|credit.?card|card.?number|cvv|cvc|one.?time|verification.?code|security.?code|private.?key|secret.?key|bank.?login|bank.?credential|routing.?number|account.?number|recovery.?phrase|seed.?phrase',text,re.I))
