"""Bounded Accessibility preflight for one explicitly approved region.

No text value is requested until all intersecting elements have been checked.
Incomplete metadata fails closed. Browser URLs are used only for exclusions.
"""
import time
from urllib.parse import urlsplit
from native.macos.accessibility import AccessibilityReader
from core.privacy import domain_excluded
from native.macos.secure_field_filter import sensitive_metadata

BROWSERS = frozenset({'com.apple.Safari', 'com.google.Chrome', 'com.microsoft.edgemac',
                      'org.mozilla.firefox', 'com.brave.Browser', 'company.thebrowser.Browser'})
CONTAINERS = frozenset({'AXWindow', 'AXGroup', 'AXWebArea', 'AXScrollArea', 'AXSplitGroup',
    'AXLayoutArea', 'AXLayoutItem', 'AXToolbar', 'AXTabGroup', 'AXTable', 'AXRow', 'AXCell',
    'AXList', 'AXOutline', 'AXApplication', 'AXSheet', 'AXDrawer'})
LEAVES = frozenset({'AXStaticText', 'AXTextArea', 'AXImage', 'AXButton', 'AXLink', 'AXCheckBox',
    'AXRadioButton', 'AXPopUpButton', 'AXMenuButton', 'AXScrollBar', 'AXSlider', 'AXHeading',
    'AXValueIndicator', 'AXProgressIndicator', 'AXSplitter', 'AXDisclosureTriangle'})


class ReadBlocked(Exception):
    pass


def contains(outer, inner):
    x, y, w, h = outer
    a, b, c, d = inner
    return a >= x and b >= y and a+c <= x+w and b+d <= y+h


def intersects(first, second):
    x, y, w, h = first
    a, b, c, d = second
    return min(x+w, a+c) > max(x, a) and min(y+h, b+d) > max(y, b)


def screen_rect(rect, primary_height):
    return (rect.x, primary_height - rect.y - rect.height, rect.width, rect.height)


class RegionReader(AccessibilityReader):
    def bounds(self, element):
        import math
        p, s = self.attribute(element, 'AXPosition'), self.attribute(element, 'AXSize')
        if p is None or s is None:
            return None
        ok, point = self.api.AXValueGetValue(p, self.api.kAXValueCGPointType, None)
        ok2, size = self.api.AXValueGetValue(s, self.api.kAXValueCGSizeType, None)
        if not ok or not ok2:
            return None
        result = (float(point.x), float(point.y), float(size.width), float(size.height))
        if not all(math.isfinite(v) and abs(v) < 1_000_000 for v in result) or result[2] < 0 or result[3] < 0:
            return None
        return result

    def window(self, pid):
        if not self.api.AXIsProcessTrusted():
            raise ReadBlocked('Accessibility permission is required to check for sensitive fields. Set it up in Privacy & control.')
        app = self.api.AXUIElementCreateApplication(pid)
        self.api.AXUIElementSetMessagingTimeout(app, .1)
        focused = self.attribute(app, 'AXFocusedUIElement')
        if focused is not None:
            self.check_role(focused)
        window = self.attribute(app, 'AXFocusedWindow')
        if window is None:
            raise ReadBlocked('This app does not expose a readable window. Upload the document instead.')
        return window

    def check_role(self, element):
        role = self.attribute(element, 'AXRole')
        subrole = self.attribute(element, 'AXSubrole')
        if role in ('AXTextField', 'AXComboBox', 'AXSecureTextField') or any(word in str(subrole).lower() for word in ('secure', 'password')):
            raise ReadBlocked('This selection includes a protected input field. Amillum did not read or capture it. Click outside the input and select document text only.')
        if role not in CONTAINERS | LEAVES:
            raise ReadBlocked('This app does not expose enough field metadata to verify this selection safely. Upload the document instead.')
        if sensitive_metadata(self.attribute(element,name) for name in
                              ('AXDescription','AXHelp','AXTitle','AXIdentifier','AXDOMIdentifier')):
            raise ReadBlocked('This selection includes a sensitive field or context. Nothing was read or captured.')
        return role

    def preflight(self, pid, identifier, rect, excluded_domains):
        window = self.window(pid)
        bounds = self.bounds(window)
        if bounds is None or not contains(bounds, rect):
            raise ReadBlocked('Keep the selection inside the active document window, then try again.')
        deadline = time.monotonic() + 2.0
        pending = [(window, 0)]
        candidates, urls, ranged = [], [], []
        count = 0
        partial_text = False
        while pending:
            element, depth = pending.pop()
            count += 1
            if count > 700 or depth > 24 or time.monotonic() > deadline:
                raise ReadBlocked('This region is too complex to check safely. Select a smaller section or upload the document.')
            b = self.bounds(element)
            if b is not None and not intersects(b, rect):
                continue
            role = self.check_role(element)
            if role == 'AXWebArea':
                url = self.attribute(element, 'AXURL')
                if url:
                    urls.append(str(url))
            children = self.attribute(element, 'AXChildren') or []
            pending.extend((child, depth+1) for child in reversed(children))
            if role == 'AXTextArea' and not children:
                ranged.append((b, element))
            elif role == 'AXStaticText':
                if b is not None and contains(rect, b) and not children:
                    candidates.append((b, element))
                else:
                    partial_text = True
        if identifier in BROWSERS:
            if not urls:
                document_url = self.attribute(window, 'AXDocument')
                if document_url:
                    urls.append(str(document_url))
            if not urls or not all(urlsplit(url).scheme in ('http', 'https', 'file') for url in urls):
                raise ReadBlocked('The browser did not expose this page’s address for privacy checks. Use a supported document viewer or upload the file.')
            if any(domain_excluded(url, excluded_domains) for url in urls):
                raise ReadBlocked('This website is excluded in Privacy & control. Nothing was read or captured.')
        return {'window': window, 'bounds': bounds, 'candidates': candidates, 'partial': partial_text, 'ranged': ranged, 'rect': rect}

    def extract(self, checked):
        # Prefer OCR rather than returning a misleading fragment of a larger text element.
        if checked['partial'] or not (checked['candidates'] or checked['ranged']):
            return ''
        pieces = []
        for bounds, element in sorted(checked['candidates'], key=lambda item: (item[0][1], item[0][0])):
            self.check_role(element)  # Roles can change after preflight.
            current = self.bounds(element)
            if current != bounds:
                raise ReadBlocked('The document moved. Select the region again.')
            value = self.attribute(element, 'AXValue')
            if isinstance(value, str) and value.strip():
                pieces.append(value)
            if sum(map(len, pieces)) > 12000:
                raise ReadBlocked('Select a smaller section (up to 12,000 characters).')
        for bounds, element in checked['ranged']:
            text = self.range_text(element, checked['rect'])
            if not text:
                return ''
            pieces.append(text)
            if sum(map(len,pieces)) > 12000:
                raise ReadBlocked('Select a smaller section (up to 12,000 characters).')
        return '\n'.join(pieces)

    def parameter(self, element, name, value):
        error, result = self.api.AXUIElementCopyParameterizedAttributeValue(element, name, value, None)
        return result if error == 0 else None

    def range_text(self, element, rect):
        # Never AXValue on an editable area: it can include off-screen document text.
        if not hasattr(self.api, 'AXUIElementCopyParameterizedAttributeValue'):
            return ''
        self.check_role(element)
        api = self.api
        x, y, w, h = rect
        selected=self.attribute(element,'AXSelectedTextRange')
        if selected is not None:
            ok, r=api.AXValueGetValue(selected,api.kAXValueCFRangeType,None)
            if ok and r[0] >= 0 and 0 < r[1] <= 12000:
                box=self.parameter(element,'AXBoundsForRange',selected)
                if box is not None:
                    ok, box=api.AXValueGetValue(box,api.kAXValueCGRectType,None)
                    b=(box.origin.x,box.origin.y,box.size.width,box.size.height) if ok else None
                    if b and contains(rect,b):
                        self.check_role(element)
                        current=self.parameter(element,'AXBoundsForRange',selected)
                        ok2,current=api.AXValueGetValue(current,api.kAXValueCGRectType,None) if current is not None else (False,None)
                        if not ok2 or current != box:
                            raise ReadBlocked('The selection moved. Select the region again.')
                        text=self.parameter(element,'AXStringForRange',selected)
                        if isinstance(text,str):
                            return text
        visible = self.attribute(element, 'AXVisibleCharacterRange')
        if visible is None:
            return ''
        ok, visible = api.AXValueGetValue(visible, api.kAXValueCFRangeType, None)
        if not ok or visible[1] <= 0:
            return ''
        first = self.parameter(element, 'AXLineForIndex', visible[0])
        last = self.parameter(element, 'AXLineForIndex', visible[0]+visible[1]-1)
        if first is None or last is None or int(last)-int(first) > 200:
            return ''
        approved = []
        total = 0
        for line in range(int(first), int(last)+1):
            value = self.parameter(element, 'AXRangeForLine', line)
            if value is None:
                return ''
            ok, r = api.AXValueGetValue(value, api.kAXValueCFRangeType, None)
            if not ok:
                return ''
            a, b = max(visible[0], r[0]), min(visible[0]+visible[1], r[0]+r[1])
            if b <= a:
                continue
            value = api.AXValueCreate(api.kAXValueCFRangeType, (a, b-a))
            box = self.parameter(element, 'AXBoundsForRange', value)
            if box is None:
                return ''
            ok, box = api.AXValueGetValue(box, api.kAXValueCGRectType, None)
            bounds = (box.origin.x, box.origin.y, box.size.width, box.size.height) if ok else None
            if bounds is None:
                return ''
            if not intersects(rect, bounds):
                continue
            if not contains(rect, bounds):
                return ''
            total += b-a
            if total > 12000:
                return ''
            approved.append((value, bounds))
        pieces = []
        for value, original_bounds in approved:
            self.check_role(element)
            current_box = self.parameter(element, 'AXBoundsForRange', value)
            if current_box is None:
                return ''
            ok, current_box = api.AXValueGetValue(current_box, api.kAXValueCGRectType, None)
            current_bounds = (current_box.origin.x, current_box.origin.y, current_box.size.width, current_box.size.height) if ok else None
            if current_bounds != original_bounds:
                raise ReadBlocked('The document moved. Select the region again.')
            text = self.parameter(element, 'AXStringForRange', value)
            if not isinstance(text, str):
                return ''
            pieces.append(text)
            if sum(map(len,pieces)) > 12000:
                raise ReadBlocked('Select a smaller section (up to 12,000 characters).')
        return ''.join(pieces)
