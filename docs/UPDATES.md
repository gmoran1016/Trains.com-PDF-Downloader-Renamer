# Desktop update releases

The Tauri updater checks the `latest.json` asset on the newest GitHub Release. It verifies each platform signature against the public key embedded in `desktop-ui/src-tauri/tauri.conf.json`. Keep the matching private key for the life of these installed builds; a different key will not be accepted by existing installations.

## Signing key

Generate the key once from `desktop-ui` with the Tauri CLI:

```powershell
npm run tauri -- signer generate --write-keys "$env:USERPROFILE/.tauri/trains-com-archive.key"
```

The CLI creates a private key and a `.pub` public key file. The public key is embedded in the Tauri config. Never commit or share the private key. Keep an encrypted backup outside the repository and store its password separately. The key and password must remain available for every future signed release.

In the repository's GitHub **Settings → Secrets and variables → Actions**, create these repository secrets:

- `TAURI_SIGNING_PRIVATE_KEY`: the private key file contents.
- `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`: the password used when creating the key.

The build workflow exposes these secrets only to the Tauri bundle signing step. Do not put them in workflow files, `.env` files, release assets, or a source commit. The local `scripts/build-desktop.ps1` build disables signature artifact generation when the signing values are not set in its process.

If the private key is lost or replaced, users must manually install a build containing the new public key before in-app updates can resume.

## Publishing a release

For each version:

1. Set the engine, Rust, desktop UI, Tauri bundle, and npm lockfile versions to the same semantic version. Run `python scripts/check_app_versions.py`.
2. Add `docs/releases/v<version>.md`. The text is shown in the update offer and used as the GitHub release description.
3. Push the release commit to `main` or `master`, or dispatch the **Build Desktop Applications** workflow with **Publish the verified artifacts to GitHub Releases** enabled.

The workflow builds and signs the Windows NSIS installer, Linux AppImage, and macOS app archives for Apple Silicon and Intel. It keeps the Windows portable executable and existing DMG downloads, publishes detached signatures, builds `latest.json` from the collected artifacts, and attaches all update assets to the versioned release. The app reads the newest stable release manifest from GitHub.

## First update

Existing v1.x applications do not have the updater code. Install v2.0.0 manually once from the GitHub Releases page. Later versions can be checked and installed from Settings or the startup offer.

Windows portable builds do not run the NSIS updater. They open the portable executable download and explain how to close the app, replace the executable, and keep adjacent data files in place.
