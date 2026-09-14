"""Local offer policy over the existing classifier scores; no content or IO."""
import math
import os
from collections import OrderedDict
from dataclasses import dataclass

@dataclass(frozen=True)
class AssistanceConfig:
    indicator: float = .70
    suggestion: float = .90
    global_cooldown: float = 30
    dismissal_base: float = 300

    def __post_init__(self):
        if not (0 < self.indicator < self.suggestion <= 1):raise ValueError('Assistance thresholds must satisfy 0 < indicator < suggestion <= 1.')
        if not all(math.isfinite(v) and 1 <= v <= 3600 for v in (self.global_cooldown,self.dismissal_base)):raise ValueError('Assistance intervals must be between 1 and 3600 seconds.')

    @classmethod
    def from_environment(cls):
        return cls(*(float(os.getenv(key,default)) for key,default in [
            ('AMILLUM_INDICATOR_THRESHOLD','.70'),('AMILLUM_SUGGESTION_THRESHOLD','.90'),
            ('AMILLUM_OFFER_INTERVAL_SECONDS','30'),('AMILLUM_DISMISSAL_SECONDS','300')]))

class AssistancePolicy:
    """Uses the detector's clock and cooldown map. Only hashes and decisions persist in RAM."""
    def __init__(self,detector,config=None):
        self.detector=detector
        self.config=config or AssistanceConfig.from_environment()
        self.memory=OrderedDict()
        self.accepted=OrderedDict()
        self.active=None
        self.current=None
        self.last_offer=-math.inf

    def reset(self):
        self.memory.clear();self.accepted.clear();self.active=self.current=None
        self.last_offer=-math.inf

    def evaluate(self,result,fingerprint,document):
        score=result.get('confidence',0)
        self.current=(fingerprint,document)
        if not isinstance(score,(int,float)) or not math.isfinite(score) or score<self.config.indicator:
            self.active=None
            return None
        offer=dict(result,assistance='indicator')
        now=self.detector.clock()
        record=self.memory.get(document,{'count':0,'until':0})
        if fingerprint in self.accepted or now<record['until']:
            self.active=None
            return None
        if score<self.config.suggestion:
            self.active=None
            return offer
        if self.active == (fingerprint,document):return dict(offer,assistance='suggestion')
        self.active=None
        if now-self.last_offer<self.config.global_cooldown or now-self.detector.seen.get(fingerprint,-math.inf)<self.detector.config.cooldown:
            return offer
        self.detector.seen[fingerprint]=now
        self.detector.seen.move_to_end(fingerprint)
        while len(self.detector.seen)>64:self.detector.seen.popitem(last=False)
        self.last_offer=now;self.active=(fingerprint,document)
        return dict(offer,assistance='suggestion')

    def feedback(self,accepted=False):
        if self.active is None:return False
        fingerprint,document=self.active
        self.active=None
        if accepted:
            self.accepted[fingerprint]=True
            while len(self.accepted)>64:self.accepted.popitem(last=False)
        else:
            count=min(self.memory.get(document,{'count':0})['count']+1,5)
            self.memory[document]={'count':count,'until':self.detector.clock()+min(3600,self.config.dismissal_base*2**(count-1))}
            self.memory.move_to_end(document)
            while len(self.memory)>64:self.memory.popitem(last=False)
        return True

    def hide(self):
        self.active=None
