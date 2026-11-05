# GitHub In-App Updater Design

## Intent

Let users learn when a newer stable desktop release is available and, after they approve it, install and restart into that release without leaving the app.

## Goals

- Check for stable updates at startup and from an explicit **Check for updates** action in Settings.
- Tell the user when the app is current, when an update is available, and when checking or installing fails.
- Ask before downloading or installing. Show release notes and download progress, then restart into the installed version after acceptance.
- Preserve the user's local data and settings across updates.
- Support the existing Windows NSIS installer, Linux AppImage, and macOS app bundle with signed in-app installation.
- Detect a new release for Windows portable users and offer the portable executable download, with instructions to replace the executable while keeping its adjacent data files.

## Non-goals

- Updating the separate source-code development build.
- Installing prereleases or downgrading the application.
- Updating the bundled Python engine independently of the desktop app.

## Approaches

1. **Tauri's signed updater (recommended and approved).** Use the official Tauri updater plugin, a static manifest attached to GitHub Releases, and signed per-platform update artifacts. It verifies each artifact before installation and handles the platform-specific replacement and restart. The release workflow must keep a permanent private signing key in GitHub Actions secrets and publish its signatures and manifest.
2. **Release-page notification.** Query the GitHub Releases API and offer a link to the platform's existing installer. This avoids signing-key and release-workflow setup, but the user must download, install, and relaunch manually; the app cannot apply the update itself.

Approach 1 is selected because the requested experience is to approve and apply an update within the application. The existing packages already cover the target platforms, and the official updater handles their platform-specific installation.

## Behavior and implementation boundaries

- The React interface starts a non-blocking update check once the desktop snapshot is ready. Network errors do not prevent normal app use.
- Settings provides a manual check and displays the installed version. A detected release opens an in-app confirmation with version and release notes. **Later** dismisses the offer; **Update** starts download and verified installation, reports progress, and relaunches after success.
- The update offer includes a direct portable `.exe` download for Windows users who run the portable edition; the UI explains that they must close the app, replace the executable, and keep the data files in the same folder.
- Rust registers the updater plugin; the frontend updater API is permitted by the Tauri capability. The configured endpoint serves the manifest for the latest stable GitHub release.
- GitHub Actions signs Windows NSIS, Linux AppImage, and macOS application update bundles, then publishes the bundles, detached signatures, and a `latest.json` manifest alongside the existing downloadable packages. The private key is supplied only through Actions secrets; its public half is embedded in the app configuration.
- Align the repository's release-version sources at v2.0.0. The release includes the v1.10.1 PDF-naming work and the signed GitHub updater. Existing v1.x installations lack updater code and need one manual installation of v2.0.0; later releases can update in-app.
- Keep current unrelated workspace edits intact.

## Constraints and remaining implementation choices

- GitHub's latest stable release is currently v1.10.0 and has no updater manifest or signatures; the current checkout has pending v1.10.1 work.
- The signing key must remain stable across releases. The builder must establish it once, store the private key and password as GitHub Actions secrets, and keep only the public key in the repository.
- The builder may choose the exact Settings placement and concise progress/error wording, using the existing modal and button patterns.
