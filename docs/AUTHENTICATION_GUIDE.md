# Authentication Guide

The desktop application accesses subscriber-only magazine archives through a
logged-in trains.com browser session. An active trains.com subscription is
required.

## First-time setup

1. Launch the application.
2. Leave the **COOKIE FILE** field set to `session_cookies.json`, or use
   **Browse…** to choose a JSON cookie-file location.
3. Leave **Hide download browser** unchecked.
4. Select at least one magazine and click **Start Download**.
5. Chrome opens to trains.com. Complete the subscription login in that visible
   browser window.
6. The application waits for the authenticated session, then saves the
   session cookies as JSON for later runs.

The application stores no username or password. Login detection waits for up
to five minutes. If login is not detected, keep the browser open until the
account page is complete and try again.

## Later runs

When the JSON cookie file is present and still valid, the application loads it
and checks the session automatically. The log reports **Authenticated via saved
cookies.** when the session is accepted.

If the saved cookies no longer authenticate, the application reports that they
did not authenticate and asks for an interactive login. Leave the browser
visible, complete login again, and the JSON file will be refreshed.

## Headless operation

**Hide download browser** runs downloads without displaying Chrome. Use it only
after a saved JSON cookie file has successfully authenticated an interactive
run. If headless mode is enabled without a valid session, the application stops
before collecting issues and instructs you to disable headless mode.

The organizer panel’s **Hide browser for missing-issue downloads** setting has
the same prerequisite when using **Download Missing**. It does not affect a
local **Organize PDFs** run that does not download anything.

## Cookie-file security

JSON cookies represent an authenticated session. Treat the file like a
password:

- do not commit it to Git;
- do not upload or share it;
- store it somewhere accessible only to the intended Windows user;
- delete it and repeat interactive login if you suspect it was exposed.

Pickle cookie files are not supported. Use a JSON export or let the
application create a fresh JSON session file.

## Troubleshooting

### Chrome does not open

Confirm that Google Chrome is installed and that **Hide download browser** is
unchecked. Close any stale application instance and try again.

### Login is not detected

Finish the trains.com subscription login in the browser window and wait for
the account page to load. If the five-minute wait expires, start again with
headless mode disabled.

### Headless mode stops immediately

Run one interactive session first so the application can save valid JSON
cookies. Then enable **Hide download browser** on the next run.

### A cookie file is rejected

Check that the selected file is readable JSON and contains the current
trains.com session. If it is old, deleted, or invalid, choose a new path or
remove it and complete interactive login again.
