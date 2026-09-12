"""Apple Vision OCR runs entirely locally on the already-approved region image."""


def recognize_region(image, *, details=False):
    import Vision
    import math
    import unicodedata
    request = Vision.VNRecognizeTextRequest.alloc().init()
    request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    request.setUsesLanguageCorrection_(True)
    handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(image, {})
    ok, error = handler.performRequests_error_([request], None)
    if not ok:
        raise RuntimeError('Local text recognition failed. Try a clearer or smaller selection.')
    pieces, confidences = [], []
    for observation in request.results() or []:
        candidates = observation.topCandidates_(1)
        if candidates:
            line=''.join(c for c in str(candidates[0].string()) if not unicodedata.category(c).startswith('C')).strip()
            confidence=float(candidates[0].confidence())
            if line:
                pieces.append(line)
                confidences.append(min(1.0,max(0.0,confidence)) if math.isfinite(confidence) else 0.0)
    text = '\n'.join(pieces)
    if len(text) > 12000:
        raise RuntimeError('Select a smaller section (up to 12,000 characters).')
    confidence=sum(confidences)/len(confidences) if confidences else 0.0
    # Very uncertain OCR is not useful enough to offer as a reviewable passage.
    if text and confidence < .35:
        raise RuntimeError('Text recognition was too uncertain. Try larger text or a clearer region.')
    return {'text':text, 'confidence':confidence, 'needs_review':confidence < .75} if details else text
