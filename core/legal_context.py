"""Local classification of metadata and bounded transient samples; no model calls."""
import hashlib
import math
import os
import re
import time
from collections import OrderedDict
from dataclasses import dataclass

SIGNALS = {
    'Employment agreement': r'\b(?:employment|contractor|consulting|severance)\s+(?:agreement|contract)\b',
    'Lease or tenancy': r'\b(?:residential|commercial|rental|tenancy)\s+(?:lease|agreement)\b|\blease\s+agreement\b',
    'Confidentiality agreement': r'\b(?:non[ -]?disclosure|confidentiality)\s+agreement\b',
    'Legal notice': r'\b(?:legal notice|notice to vacate|eviction notice|demand letter|summons)\b',
    'Insurance document': r'\b(?:insurance policy|policy schedule|coverage agreement|insurance claim denial)\b',
    'Government or legal form': r'\b(?:court filing|immigration form|power of attorney|affidavit|form i-?130|form i-?485)\b',
    'Business agreement': r'\b(?:service|purchase|partnership|shareholder|operating|licen[cs]e)\s+agreement\b',
    'Agreement': r'\b(?:terms and conditions|terms of service|binding agreement|executed contract)\b',
}
TYPES = dict(zip(SIGNALS, ('employment','lease','contract','legal_notice','insurance','government_form','business_agreement','contract')))
EDITORS = frozenset({'com.microsoft.VSCode','com.todesktop.230313mzl4w4u92','com.sublimetext.4','com.apple.dt.Xcode'})
NEGATIVE = re.compile(r'\b(?:tutorial|definition|meaning|example|examples|template|news|what is|how to|blog|dictionary|recipe|lyrics)\b', re.I)

@dataclass(frozen=True)
class DetectionConfig:
    threshold: float = .82
    cooldown: float = 120.0

    def __post_init__(self):
        if not math.isfinite(self.threshold) or not .65 <= self.threshold <= 1:
            raise ValueError('Detection threshold must be between 0.65 and 1.')
        if not math.isfinite(self.cooldown) or not 1 <= self.cooldown <= 3600:
            raise ValueError('Detection cooldown must be between 1 and 3600 seconds.')

    @classmethod
    def from_environment(cls):
        return cls(float(os.getenv('AMILLUM_DETECTION_THRESHOLD', '.82')),
                   float(os.getenv('AMILLUM_DETECTION_COOLDOWN_SECONDS', '120')))


def classify_context(title, source_application='', config=None, accessible_text=None):
    config = config or DetectionConfig()
    result = {'legal_context':False, 'context_type':'unknown', 'confidence':0.0,
              'reason':'Insufficient legal-document metadata', 'source_application':source_application}
    if source_application in EDITORS:
        return result
    title = title[:300] if isinstance(title,str) else ''
    if NEGATIVE.search(title):
        return result
    from core.privacy import sensitive_text_reason
    if sensitive_text_reason(title):
        return result
    if isinstance(accessible_text,str) and accessible_text.strip():
        text=accessible_text[:1200]
        if sensitive_text_reason(text):return result
        families = [
            r'\b(?:employer|employee|landlord|tenant|licensor|licensee|the parties|both parties)\b',
            r'\b(?:shall|must|is required to|agrees to|obligations?|required notice)\b',
            r'\b(?:termination|liability|indemnif\w*|governing law|breach|confidentiality|severance)\b',
            r'\b(?:agreement|contract|lease|legal notice|insurance policy)\b',
            r'(?m)^\s*(?:\d+[.)]|section\s+\d|whereas\b)|\b(?:effective date|entered into|pursuant to|in witness whereof)\b',
        ]
        hits=sum(bool(re.search(pattern,text,re.I)) for pattern in families)
        score=min(.96,.34+.14*hits) if hits>=3 else .2
        if NEGATIVE.search(text[:100]):score=min(score,.5)
        label=next((label for label,pattern in SIGNALS.items() if re.search(pattern,text,re.I)), 'Agreement')
        if label=='Agreement':
            if re.search(r'\b(?:employee|employer|severance)\b',text,re.I):label='Employment agreement'
            elif re.search(r'\b(?:tenant|landlord|lease)\b',text,re.I):label='Lease or tenancy'
        result.update(legal_context=score>=config.threshold,context_type=TYPES[label],confidence=score,
                      reason='Multiple local legal-language signals' if hits>=3 else 'Accessible text does not corroborate a legal context',
                      label=label,score=score,suggestion='Select a section to review')
        return result
    document = bool(re.search(r'\.(?:pdf|docx?|odt|rtf)\b', title, re.I))
    for label, pattern in SIGNALS.items():
        match = re.search(pattern, title, re.I)
        if not match:
            continue
        # Compound document names are stronger than isolated ambiguous words.
        score = .84 if len(match.group().split()) >= 2 else .68
        if document: score = min(.96,score+.08)
        result.update(legal_context=score >= config.threshold, context_type=TYPES[label],
                      confidence=score, reason='Specific legal-document title' + (' and document format' if document else ''),
                      label=label,score=score,suggestion='Select a section to review')
        return result
    return result


def classify_title(title):
    """Compatibility for existing title-only callers."""
    result=classify_context(title)
    return result if result['legal_context'] else None


class ContextDetector:
    """Bounded, memory-only duplicate suppression; no title/history persistence."""
    def __init__(self, config=None, clock=time.monotonic):
        self.config=config or DetectionConfig.from_environment()
        self.clock=clock
        self.seen=OrderedDict()
        self.current=None
        self.result=None

    def detect(self,title,source_application,accessible_text=None):
        fingerprint=hashlib.sha256((source_application+'\0'+str(title)[:300]).encode()).digest()
        return self.decide(classify_context(title,source_application,self.config,accessible_text),fingerprint)

    def decide(self,result,fingerprint):
        if fingerprint == self.current and result['legal_context'] and self.result:
            return self.result
        self.current=fingerprint
        self.result=None
        now=self.clock()
        if result['legal_context'] and now-self.seen.get(fingerprint,-math.inf) >= self.config.cooldown:
            self.seen[fingerprint]=now
            self.seen.move_to_end(fingerprint)
            while len(self.seen)>64:self.seen.popitem(last=False)
            self.result=result
        return self.result

    def clear_current(self):
        self.current=self.result=None
