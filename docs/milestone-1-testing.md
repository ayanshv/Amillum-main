# Amillum on your Mac — Milestone 1

## Scope

Global shortcut → transparent native selection → animated dashed border → Cancel.
All new application code is Python. Existing NiceGUI/PyWebView pages and document
analysis remain in place. No screen capture, Accessibility text reads, OCR, AI
requests, permission prompts, continuous detection, or mascot animation are added.

Amillum must be running. Minimize its window or use another application to work
in the background. Closing the main window retains the existing behavior: the
application exits and its shortcuts are released. Login launch, closing-to-menu-bar,
the menu bar, and the in-app shortcut settings UI belong to later stages.

## Try it

1. Launch `python app.py` in the project's native Python environment, or open the
   newly built `Amillum.app`. Run only one new instance to avoid shortcut conflicts.
2. Switch to another app. Press **Command + Shift + A** (Control + Shift + A is an
   alternate shortcut when the default is configured).
3. Drag a rectangle. The desktop remains live behind the transparent overlay.
4. Release the mouse. The dashed border moves gently. Nothing is captured.
5. Click **Cancel** or press **Escape**. The panels and coordinates are discarded.

Selection is possible on any connected display, but a drag is clamped to the
display on which it began. Cross-display rectangles are intentionally deferred.
A rectangle smaller than 8 points on either axis is discarded so the user can retry.
While selection mode is active, the overlay consumes mouse interaction; cancellation
does not click through into the underlying application.

## Configuration

Set `AMILLUM_SHORTCUT=cmd+option+a` before launch to override the primary shortcut.
Supported modifiers: `cmd`, `ctrl`, `option`, `shift`; supported keys: A–Z and 0–9.
At least Command, Control, or Option is required. Modifiers can appear in any order.
Keys use macOS ANSI virtual key positions; non-US keyboard layouts need physical
keyboard validation before release. Set `AMILLUM_CONTROL_SHORTCUT=0` to disable
the Control alias. A custom primary shortcut does not register the default alias.

macOS exclusive registration detects conflicting global registrations. An unavailable
shortcut displays an explanatory native sheet; the existing document UI keeps working.
Ordinary application menu shortcuts may share these keys and are intentionally
superseded while Amillum owns the global registration.

No Screen Recording, Accessibility, or Input Monitoring permission is requested
by this milestone. If a future change needs one, request it only at the relevant
stage. Selection geometry is not consent to capture or analyze.

## Architecture

- `app.py` configures NiceGUI's native `start_args` during module import, including
  when macOS multiprocessing reimports the entry point.
- `native.macos.start_native` runs in PyWebView's startup worker and schedules
  `runtime.install` with `AppHelper.callAfter` onto the Cocoa main thread.
- `frozen_hook.py` is a PyInstaller runtime hook that restores this configuration
  in frozen multiprocessing children, which dispatch before `app.py` is reimported.
  It configures the callback only and does not initialize AppKit or launch windows.
- `runtime.py` retains the overlay, registered hotkeys, and lifecycle observers
  inside the existing PyWebView process. It does not replace the application delegate.
- `global_hotkey.py` binds Carbon's named hotkey API with `ctypes`. It retains C
  callbacks, suppresses repeated press events until release, and unregisters on close.
- `overlay.py` owns transparent nonactivating `NSPanel` windows and `CAShapeLayer`
  borders. The existing web interface does not handle selection or screen coordinates.
- `selection.py` holds only display metadata and rectangles in bottom-left-origin
  desktop points. Retina scale is metadata; geometry is never multiplied by scale
  while drawing. Any future pixel/AX coordinate conversion must be explicit.
- `mascot_anchor.py` holds only a point at the lower middle of the border. It renders
  nothing and clears on cancellation. There is no mascot state machine yet.

Screen arrangement changes, Space changes, application switches, sleep/session
interruptions and shutdown cancel selection. Reduce Motion disables dash animation.
No selection data is persisted, exposed to a page, or passed to the backend.

## Automated checks

Run from the repository root:

```sh
./vn/bin/python -B -m unittest discover -s tests -v
```

Real native tests require a logged-in macOS desktop and briefly show panels:

```sh
AMILLUM_NATIVE_TESTS=1 ./vn/bin/python -B -m unittest discover -s tests -p test_macos_integration.py -v
```

They exercise actual transparent panels, the Cancel button, Escape's responder
action, repeated session cleanup, interruption handling, and Carbon conflict/release.
They do not synthesize global keystrokes or capture screenshots.

## Manual release checks

- Test physical shortcut activation in Preview, Safari, Chrome, a browser PDF,
  TextEdit and Word where available. Test both default shortcuts and a custom one.
- Drag each direction; test a click without a drag, tiny rectangles, and edges.
- Cancel before dragging, during dragging, and after selecting; click Cancel too.
- Invoke repeatedly; hold the shortcut; quit/reopen. No duplicate or orphan panels.
- Test full-screen apps and separate Spaces without an unwanted Space switch.
- Test multiple displays above/below/left of the primary, mixed Retina scales,
  unplugging a display, and changing resolution while selecting.
- Check light/dark underlying content, system Reduce Motion, label readability,
  and border/control placement near each display edge.
- Verify the underlying document did not change and focus returns appropriately.
- Repeat with the packaged application and without screen/input/accessibility grants.
- Open the existing upload page. Test its normal document flow separately with
  explicitly approved test documents; this milestone must not send documents itself.

Physical global shortcuts must be tested with a keyboard. Some automation tools
deliver app-targeted keystrokes that bypass Carbon's global registration.

## Packaging

The existing `Amicus.spec` now emits `Amillum.app` and includes the native modules.
Its existing bundle identifier `Amicus` is retained to avoid inventing an owned
reverse-DNS identity. It is an ad hoc signed development build. A production bundle
identifier, branded macOS icon, Developer ID signing and notarization remain separate
distribution work. The existing Gemini key is not bundled.
