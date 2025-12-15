# Authentication Guide

This guide explains how to use the login and cookie management features to access subscriber-only content on trains.com.

## How Login Works

**Manual Login (Simple & Reliable):**
1. Script opens browser to https://www.trains.com/
2. You click the login button and enter your credentials
3. Script saves your session cookies
4. Future runs use saved cookies - no login needed!

This approach is **100% reliable** and only needed once.

## Quick Start

### First Time Setup (Do This Once)
```bash
python Magazine-Downloader.py --login --save-cookies
```

**What happens:**
1. Browser window opens
2. You see clear instructions in terminal
3. You manually login in the browser
4. Press Enter in terminal when done
5. Cookies saved automatically!

### All Future Runs (Super Easy)
```bash
python Magazine-Downloader.py --use-cookies
```

No login needed - uses your saved session!

## Authentication Methods

### Method 1: Manual Login with Cookie Save (Recommended)
The most reliable way - only do this once:

```bash
python Magazine-Downloader.py --login --save-cookies
```

This will:
1. Prompt you for your username/email
2. Prompt you for your password (hidden input)
3. Attempt to login automatically
4. Save cookies for future use
5. If automatic login fails, allow you to login manually in the browser

### Method 2: Login with Command-Line Credentials (Less Secure)
Provide credentials via command line (not recommended as password is visible):

```bash
python Magazine-Downloader.py --login --username "your@email.com" --password "yourpassword" --save-cookies
```

**Warning:** This method exposes your password in command history!

### Method 3: Use Saved Cookies (Best for Repeated Use)
Once you've logged in and saved cookies, reuse them:

```bash
python Magazine-Downloader.py --use-cookies
```

This will:
1. Load saved cookies from `session_cookies.pkl`
2. Verify you're still logged in
3. Proceed with downloading

### Method 4: Custom Cookie File Location
Specify a custom cookie file:

```bash
python Magazine-Downloader.py --login --save-cookies --cookies-file "my_cookies.pkl"
```

Later, reuse those cookies:

```bash
python Magazine-Downloader.py --use-cookies --cookies-file "my_cookies.pkl"
```

## Common Usage Scenarios

### First Time Setup
1. Login and save cookies:
   ```bash
   python Magazine-Downloader.py --login --save-cookies
   ```

2. Enter your credentials when prompted

3. Cookies are saved to `session_cookies.pkl`

### Regular Downloads
After first-time setup, just use saved cookies:

```bash
python Magazine-Downloader.py --use-cookies
```

### Cookie Expired? Re-login
If cookies expire, login again:

```bash
python Magazine-Downloader.py --login --save-cookies
```

### Headless Mode with Authentication
Run in background with saved cookies:

```bash
python Magazine-Downloader.py --use-cookies --headless
```

### Complete Example: First-Time Full Download
```bash
# Step 1: Login and save cookies
python Magazine-Downloader.py --login --save-cookies --start-page 1 --end-page 10

# Step 2: Continue with cookies (no re-login needed)
python Magazine-Downloader.py --use-cookies --start-page 11 --end-page 20
```

## How It Works

### Cookie Management
- **Cookies are saved** to `session_cookies.pkl` (or custom file)
- **Cookies persist** your login session between script runs
- **Cookies expire** after some time (usually days/weeks)
- **Re-login required** when cookies expire

### Login Verification
The script checks if you're logged in by:
1. Looking for "log out" / "sign out" text on the page
2. Checking if "log in" / "sign in" buttons are present

### Automatic vs Manual Login
1. **Automatic**: Script tries to find and fill login form automatically
2. **Manual**: If automatic fails, browser stays open for you to login manually
3. After manual login, press Enter to continue

## Troubleshooting

### Login Fails Automatically
If automatic login doesn't work:
1. Browser window stays open
2. Manually login on the website
3. Press Enter in the terminal when done
4. Script continues and saves cookies

### Cookies Not Working
If saved cookies don't work:
```bash
# Delete old cookies and re-login
rm session_cookies.pkl
python Magazine-Downloader.py --login --save-cookies
```

### Want to Use Different Account
```bash
# Use different cookie file for different accounts
python Magazine-Downloader.py --login --save-cookies --cookies-file "account1.pkl"
python Magazine-Downloader.py --login --save-cookies --cookies-file "account2.pkl"

# Then use specific account
python Magazine-Downloader.py --use-cookies --cookies-file "account1.pkl"
```

### Check All Authentication Options
```bash
python Magazine-Downloader.py --help
```

## Security Notes

1. **Cookie files contain your session** - keep them secure
2. **Don't share cookie files** - they give access to your account
3. **Use interactive login** instead of command-line password
4. **Cookies expire** - you'll need to re-login periodically
5. **Don't commit cookies to git** - they're in `.gitignore` by default

## Command Reference

| Flag | Description |
|------|-------------|
| `--login` | Perform login (prompts for credentials) |
| `--username USER` | Provide username/email |
| `--password PASS` | Provide password (not recommended) |
| `--use-cookies` | Load and use saved cookies |
| `--save-cookies` | Save cookies after login |
| `--cookies-file PATH` | Specify cookie file path |

## Examples by Use Case

### Download with subscription (first time)
```bash
python Magazine-Downloader.py --login --save-cookies
```

### Download with subscription (subsequent runs)
```bash
python Magazine-Downloader.py --use-cookies
```

### Automated/scheduled downloads
```bash
# Setup once with login
python Magazine-Downloader.py --login --save-cookies

# Use in cron/scheduled task
python Magazine-Downloader.py --use-cookies --headless
```

### Debug login issues
```bash
# Run without headless to see what's happening
python Magazine-Downloader.py --login --save-cookies
```

### Download specific range with authentication
```bash
python Magazine-Downloader.py --use-cookies --start-page 50 --end-page 60
```
