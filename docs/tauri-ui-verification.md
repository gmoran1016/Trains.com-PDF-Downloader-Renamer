# Tauri UI replacement verification

Date: 2026-10-09. Version candidate: 1.10.0.

## Scope and result

Replaced the egui interface with Tauri 2, React, and TypeScript. Retained the Python engine, protocol v1, portable data policy, settings compatibility, three workflows, organizer findings, safe missing downloads, cache clearing, tray, and cooperative cancellation.

| Check | Local Windows result |
|---|---|
| Python engine, browser-adapter and worker tests | 97 passed |
| Rust controller/settings/protocol/bundle tests | 34 passed |
| Native shell data-location test | 1 passed |
| Rendered interaction/layout tests | 25 passed |
| Rust formatting and Clippy with warnings denied | Passed |
| TypeScript and Vite production build | Passed |
| Shared version check | All six surfaces match 1.10.0 |
| Bundled worker smoke check | Passed |
| Windows portable and NSIS build | Produced; final review rebuild pending |
| Production startup and normal close | Passed in an isolated data directory |

## Rendered evidence

Playwright checks both themes at 640×480, 800×620, 1120×760, and 1440×900, with long paths/status messages and a saved expanded Activity height. Every work area is captured. Critical controls stay inside the viewport; the form scrolls independently and never intersects its action footer. All six outcomes are labeled. Settings support Escape and return focus. Separate destinations, shared account path, options, missing-download safety, filtering, clipboard commands, and all three running-close commands are exercised.

The first screenshot inspection revealed that an unquoted font family containing a numeral did not parse. A rendered font-loading assertion reproduced the defect before correction; Source Sans 3 now loads in both the browser and native WebView2. Settings-save failure and partial-result retention regressions likewise reproduced before fixes. The confirming screenshot batch showed the intended font, themed controls, equal navigation, and a readable event row in the smallest running layout. Tests reject page and console errors.

Local captures live in the ignored `desktop-ui/test-results/` directory. CI retains rendered-test evidence as artifacts. Browser fixtures are development-only and cannot be used in the production bundle.

## Native Windows checks

The built app was inspected through Windows accessibility and screenshot capture at a 1120×760 client size in light mode and an 800×620 saved client size in dark mode with expanded Activity. WebView2 loaded embedded `http://tauri.localhost/` assets without a development server. The navigation, form, action footer, Activity and font rendered correctly. Native folder selection opened in the isolated source directory and cancellation left the selection intact.

A separate verification build required both `--qa` and `--data-dir` to use a sample worker. An organizer job completed and exposed all counts, the full report and safe Download Missing action. Stop produced Cancelled, kept partial findings, and removed the unsafe follow-up action. Closing during a job exposed Cancel, Minimize to Tray and Stop & Quit; Stop & Quit cancelled and exited. An unknown settings field remained intact after UI saves.

The production package also launched its real embedded Python worker through the UI against newly created empty temporary folders. It returned a complete scan with zero counts and the distinct No results outcome. No live login, cookie contents, network archive download, or user library changes were used. Production is built without the fake-worker feature.

## Platform and release boundaries

Windows requires WebView2; the portable executable uses the installed runtime, while the per-user installer provides its bootstrapper. Chrome is required for download jobs. Linux AppImage and macOS DMG builds are configured in CI, with Linux based on Ubuntu 22.04. AppImage data stays beside the original image; macOS data stays beside the `.app` folder, which must be in a writable location. Packages are unsigned unless signing is configured.

Local Windows checks do not establish Linux/macOS runtime behavior or a real subscribed download. GitHub publication is gated on every matrix build succeeding. Final independent review, rebuild hashes, and the exact GitHub run will be recorded below when complete.
