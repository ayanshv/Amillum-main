"""Small, deterministic title classifier. No model, network, or document body."""
import re

SIGNALS = {
    'Employment agreement': r'\b(employment|contractor|consulting) (agreement|contract)\b',
    'Lease or tenancy': r'\b(lease|tenancy|rental agreement)\b',
    'Confidentiality agreement': r'\b(nda|non.disclosure|confidentiality agreement)\b',
    'Legal notice': r'\b(legal notice|notice to vacate|eviction notice|demand letter)\b',
    'Agreement': r'\b(contract|agreement|terms and conditions|terms of service)\b',
}


def classify_title(title):
    if not isinstance(title, str):
        return None
    for category, pattern in SIGNALS.items():
        if re.search(pattern, title[:300], re.I):
            return {'label': category, 'score': .85, 'suggestion': 'Select a section to review'}
    return None
