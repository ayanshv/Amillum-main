"""Small transient AX text samples after the existing region privacy preflight.

No OCR, selection capture, full-document AXValue reads, storage, or networking.
"""
from native.macos.region_reader import RegionReader, ReadBlocked
from core.privacy import sensitive_text_reason

MAX_SAMPLE = 1200

class DetectionReader(RegionReader):
    def sample(self, checked, valid=lambda: True):
        pieces=[]
        remaining=MAX_SAMPLE
        # At most three already checked elements; never walk another document tree.
        entries=list(checked.get('ranged',[]))+list(checked.get('candidates',[]))
        for original,element in entries[:3]:
            if not valid():raise ReadBlocked('Context changed')
            self.check_role(element)
            if self.bounds(element)!=original:raise ReadBlocked('Context moved')
            role=self.attribute(element,'AXRole')
            visible=self.attribute(element,'AXVisibleCharacterRange')
            text=None
            if visible is not None:
                ok,r=self.api.AXValueGetValue(visible,self.api.kAXValueCFRangeType,None)
                if ok and r[0]>=0 and r[1]>0:
                    bounded=self.api.AXValueCreate(self.api.kAXValueCFRangeType,(r[0],min(r[1],remaining)))
                    if not valid():raise ReadBlocked('Context changed')
                    text=self.parameter(element,'AXStringForRange',bounded)
            elif role=='AXStaticText':
                # Only a known-small static leaf can use AXValue as a fallback.
                length=self.attribute(element,'AXNumberOfCharacters')
                if isinstance(length,int) and 0<length<=remaining:
                    if not valid():raise ReadBlocked('Context changed')
                    text=self.attribute(element,'AXValue')
            if not valid():raise ReadBlocked('Context changed')
            self.check_role(element)
            if self.bounds(element)!=original:raise ReadBlocked('Context moved')
            if isinstance(text,str):
                text=text[:remaining]
                if sensitive_text_reason(text):raise ReadBlocked('Sensitive content')
                pieces.append(text);remaining-=len(text)
            if remaining<=0:break
        return '\n'.join(pieces)[:MAX_SAMPLE] or None
