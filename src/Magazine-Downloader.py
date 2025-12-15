from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    WebDriverException,
    InvalidSessionIdException
)
import time
import os
import json
import logging
import argparse
import random
import pickle
import getpass
from functools import wraps

# ----------------------------
# Setup Logging
# ----------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('scraper.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ----------------------------
# Config
# ----------------------------
BASE_URL = "https://www.trains.com/mrr/magazine/archive-access/"
MAIN_SITE_URL = "https://www.trains.com/"
DELAY_SECONDS = 2
DOWNLOAD_DIR = "downloads-MRR"
PROGRESS_FILE = "download_progress.json"
COOKIES_FILE = "session_cookies.pkl"
MAX_RETRY_ATTEMPTS = 3
DOWNLOAD_TIMEOUT = 120  # seconds to wait for download
LOGIN_TIMEOUT = 30  # seconds to wait for login

os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# ----------------------------
# Global Driver Variable
# ----------------------------
driver = None

# ----------------------------
# Progress Tracking Functions
# ----------------------------
def load_progress():
    """Load download progress from JSON file"""
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError:
            logger.warning(f"Could not parse {PROGRESS_FILE}, starting fresh")
    return {"completed": [], "failed": [], "skipped": []}

def save_progress(progress):
    """Save download progress to JSON file"""
    try:
        with open(PROGRESS_FILE, 'w') as f:
            json.dump(progress, f, indent=2)
        logger.debug("Progress saved successfully")
    except Exception as e:
        logger.error(f"Failed to save progress: {e}")

# ----------------------------
# Cookie Management Functions
# ----------------------------
def save_cookies(driver, filepath=COOKIES_FILE):
    """Save browser cookies to file"""
    try:
        cookies = driver.get_cookies()
        with open(filepath, 'wb') as f:
            pickle.dump(cookies, f)
        logger.info(f"Cookies saved to {filepath}")
        return True
    except Exception as e:
        logger.error(f"Failed to save cookies: {e}")
        return False

def load_cookies(driver, filepath=COOKIES_FILE):
    """Load cookies from file into browser"""
    if not os.path.exists(filepath):
        logger.warning(f"Cookie file {filepath} not found")
        return False

    try:
        with open(filepath, 'rb') as f:
            cookies = pickle.load(f)

        # Navigate to domain first before adding cookies
        driver.get(BASE_URL)
        time.sleep(1)

        for cookie in cookies:
            try:
                driver.add_cookie(cookie)
            except Exception as e:
                logger.debug(f"Could not add cookie {cookie.get('name', 'unknown')}: {e}")

        logger.info(f"Cookies loaded from {filepath}")
        return True
    except Exception as e:
        logger.error(f"Failed to load cookies: {e}")
        return False

def verify_login(driver):
    """Verify if user is logged in by checking for subscriber content"""
    try:
        driver.get(BASE_URL)
        time.sleep(2)

        # Check for common indicators of being logged in
        # You may need to adjust these selectors based on the actual site
        page_source = driver.page_source.lower()

        # Check for login/logout indicators
        if "log out" in page_source or "logout" in page_source or "sign out" in page_source:
            logger.info("Login verification successful - user is logged in")
            return True

        # Check if login/sign-in button is present (indicates not logged in)
        if "log in" in page_source or "sign in" in page_source:
            logger.warning("Login verification failed - user appears to be logged out")
            return False

        # If uncertain, assume logged in
        logger.info("Login status uncertain - proceeding with assumption of logged in")
        return True

    except Exception as e:
        logger.error(f"Error verifying login: {e}")
        return False

# ----------------------------
# Login Functions
# ----------------------------
def perform_login(driver, username=None, password=None):
    """
    Perform interactive or automated login to trains.com
    Handles popup/modal login forms

    Args:
        driver: Selenium WebDriver instance
        username: Optional username (if None, prompts user)
        password: Optional password (if None, prompts user)

    Returns:
        bool: True if login successful, False otherwise
    """
    try:
        logger.info("Navigating to trains.com...")
        driver.get(MAIN_SITE_URL)
        time.sleep(3)

        # Prompt user to login manually (most reliable method)
        logger.info("\n" + "="*60)
        logger.info("MANUAL LOGIN REQUIRED")
        logger.info("="*60)
        logger.info("")
        logger.info("The browser window has opened to trains.com")
        logger.info("")
        logger.info("Please follow these steps:")
        logger.info("  1. Look at the browser window")
        logger.info("  2. Click the 'Login' or 'Sign In' button")
        logger.info("  3. Enter your username/email and password in the popup")
        logger.info("  4. Complete the login process")
        logger.info("  5. Wait for the page to fully load after login")
        logger.info("  6. Then come back here and press Enter")
        logger.info("")
        logger.info("Your session will be saved so you won't need to")
        logger.info("login again in future runs!")
        logger.info("")
        logger.info("="*60 + "\n")

        input("Press Enter after you have successfully logged in...")

        # Verify manual login
        try:
            driver.switch_to.default_content()
        except:
            pass

        if verify_login(driver):
            logger.info("Manual login successful!")
            save_cookies(driver)
            return True
        else:
            logger.warning("Could not verify login status")
            logger.info("Proceeding anyway - downloads will show if authentication is needed")
            save_cookies(driver)  # Save cookies anyway
            return True  # Return True to continue

    except Exception as e:
        logger.error(f"Error during login process: {e}")
        # Make sure we're back to default content
        try:
            driver.switch_to.default_content()
        except:
            pass
        return False

def perform_login_old_auto(driver, username=None, password=None):
    """
    OLD AUTOMATIC LOGIN METHOD - Kept for reference but not used
    The automatic detection is unreliable with modern popup-based logins
    """
    try:
        logger.info("Navigating to trains.com...")
        driver.get(MAIN_SITE_URL)
        time.sleep(3)

        # Get credentials if not provided
        if username is None:
            username = input("Enter your trains.com username/email: ")
        if password is None:
            password = getpass.getpass("Enter your password: ")

        logger.info(f"Attempting login for user: {username}")

        # Try to find and click login button to open popup
        try:
            # Try multiple possible selectors for the login button (XPath and CSS)
            login_trigger_selectors = [
                # XPath selectors for text-based searches
                (By.XPATH, "//a[contains(text(), 'Login') or contains(text(), 'LOG IN') or contains(text(), 'log in')]"),
                (By.XPATH, "//button[contains(text(), 'Login') or contains(text(), 'LOG IN') or contains(text(), 'log in')]"),
                (By.XPATH, "//a[contains(text(), 'Sign In') or contains(text(), 'SIGN IN') or contains(text(), 'sign in')]"),
                (By.XPATH, "//button[contains(text(), 'Sign In') or contains(text(), 'SIGN IN') or contains(text(), 'sign in')]"),
                (By.XPATH, "//span[contains(text(), 'Login') or contains(text(), 'LOG IN')]/ancestor::a"),
                (By.XPATH, "//span[contains(text(), 'Sign In') or contains(text(), 'SIGN IN')]/ancestor::a"),
                # CSS selectors
                (By.CSS_SELECTOR, "a[href*='login']"),
                (By.CSS_SELECTOR, "button[href*='login']"),
                (By.CSS_SELECTOR, ".login-link"),
                (By.CSS_SELECTOR, "#login-link"),
                (By.CSS_SELECTOR, "a[class*='login']"),
                (By.CSS_SELECTOR, "button[class*='login']"),
                (By.CSS_SELECTOR, "a[class*='sign-in']"),
                (By.CSS_SELECTOR, "button[class*='sign-in']")
            ]

            login_trigger = None
            for by_type, selector in login_trigger_selectors:
                try:
                    elements = driver.find_elements(by_type, selector)
                    for element in elements:
                        # Check if element is visible and clickable
                        if element.is_displayed():
                            login_trigger = element
                            logger.info(f"Found login button using: {selector}")
                            break
                    if login_trigger:
                        break
                except NoSuchElementException:
                    continue
                except Exception as e:
                    logger.debug(f"Error trying selector {selector}: {e}")
                    continue

            if login_trigger:
                logger.info("Clicking login button to open popup...")
                driver.execute_script("arguments[0].scrollIntoView(true);", login_trigger)
                time.sleep(0.5)
                ActionChains(driver).move_to_element(login_trigger).click().perform()
                logger.debug("Login popup triggered")
                time.sleep(3)  # Wait longer for popup to appear
            else:
                logger.warning("Could not find login button automatically - will try to find form directly")

            # Try to find and fill login form (in popup/modal or iframe)
            # Wait for login form to appear (using explicit wait)
            wait = WebDriverWait(driver, 10)

            # Check if login form is in an iframe
            iframes = driver.find_elements(By.TAG_NAME, "iframe")
            form_found = False
            username_field = None

            # Try main page first with explicit wait
            try:
                logger.debug("Waiting for login form on main page...")
                username_field = wait.until(EC.presence_of_element_located(
                    (By.CSS_SELECTOR,
                     "input[type='email'], input[name='username'], input[name='email'], "
                     "input[id='username'], input[id='email'], input[placeholder*='email' i], "
                     "input[placeholder*='username' i]")))
                form_found = True
                logger.debug("Login form found on main page")
            except TimeoutException:
                logger.debug("Login form not found on main page, checking iframes...")
                # Try iframes
                for iframe in iframes:
                    try:
                        driver.switch_to.frame(iframe)
                        logger.debug(f"Checking iframe for login form...")
                        username_field = wait.until(EC.presence_of_element_located(
                            (By.CSS_SELECTOR,
                             "input[type='email'], input[name='username'], input[name='email'], "
                             "input[id='username'], input[id='email'], input[placeholder*='email' i], "
                             "input[placeholder*='username' i]")))
                        form_found = True
                        logger.debug("Login form found in iframe")
                        break
                    except TimeoutException:
                        driver.switch_to.default_content()
                        continue

            if form_found:
                # Fill username
                username_field.clear()
                username_field.send_keys(username)
                logger.debug("Username entered")
                time.sleep(0.5)

                # Find and fill password field
                password_field = driver.find_element(By.CSS_SELECTOR,
                    "input[type='password'], input[name='password'], input[id='password']")
                password_field.clear()
                password_field.send_keys(password)
                logger.debug("Password entered")
                time.sleep(0.5)

                # Find and click submit button
                submit_selectors = [
                    (By.CSS_SELECTOR, "button[type='submit']"),
                    (By.CSS_SELECTOR, "input[type='submit']"),
                    (By.XPATH, "//button[contains(text(), 'Sign In') or contains(text(), 'SIGN IN') or contains(text(), 'sign in')]"),
                    (By.XPATH, "//button[contains(text(), 'Login') or contains(text(), 'LOG IN') or contains(text(), 'login')]"),
                    (By.XPATH, "//button[contains(text(), 'Submit') or contains(text(), 'SUBMIT')]"),
                    (By.XPATH, "//input[@value='Sign In' or @value='Login' or @value='Submit']"),
                    (By.CSS_SELECTOR, "button[name='login']"),
                    (By.CSS_SELECTOR, "button[class*='login']"),
                    (By.CSS_SELECTOR, "button[class*='submit']"),
                    (By.CSS_SELECTOR, "input[class*='submit']")
                ]

                submit_button = None
                for by_type, selector in submit_selectors:
                    try:
                        submit_button = driver.find_element(by_type, selector)
                        if submit_button and submit_button.is_displayed():
                            logger.debug(f"Found submit button using: {selector}")
                            break
                    except NoSuchElementException:
                        continue
                    except Exception:
                        continue

                if submit_button:
                    submit_button.click()
                    logger.info("Login form submitted, waiting for authentication...")
                else:
                    # Try pressing Enter on password field
                    password_field.send_keys("\n")
                    logger.info("Submitted login via Enter key...")

                # Switch back to main content if we were in iframe
                driver.switch_to.default_content()

                # Wait for login to complete
                time.sleep(5)

                # Verify login was successful
                if verify_login(driver):
                    logger.info("Login successful!")
                    save_cookies(driver)
                    return True
                else:
                    logger.error("Login verification failed - credentials may be incorrect")
                    return False
            else:
                raise NoSuchElementException("Could not find login form")

        except (NoSuchElementException, TimeoutException) as e:
            logger.error(f"Could not find login form elements automatically: {e}")
            logger.info("\n" + "="*60)
            logger.info("MANUAL LOGIN REQUIRED")
            logger.info("="*60)
            logger.info("")
            logger.info("The browser window is open to trains.com")
            logger.info("")
            logger.info("Please follow these steps:")
            logger.info("  1. Click the 'Login' or 'Sign In' button in the browser")
            logger.info("  2. Enter your username/email and password")
            logger.info("  3. Complete the login process")
            logger.info("  4. Wait for the page to load after login")
            logger.info("  5. Press Enter in this terminal to continue")
            logger.info("")
            logger.info("="*60 + "\n")
            input("Press Enter after you have logged in...")

            # Switch back to main content if needed
            try:
                driver.switch_to.default_content()
            except:
                pass

            # Verify manual login
            if verify_login(driver):
                logger.info("Manual login successful!")
                save_cookies(driver)
                return True
            else:
                logger.error("Manual login verification failed")
                return False

    except Exception as e:
        logger.error(f"Error during login process: {e}")
        # Make sure we're back to default content
        try:
            driver.switch_to.default_content()
        except:
            pass
        return False

# ----------------------------
# Retry Decorator
# ----------------------------
def retry(max_attempts=MAX_RETRY_ATTEMPTS, delay=2, exceptions=(Exception,)):
    """Retry decorator with exponential backoff"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    if attempt == max_attempts - 1:
                        logger.error(f"{func.__name__} failed after {max_attempts} attempts: {e}")
                        raise
                    wait_time = delay * (2 ** attempt) + random.uniform(0, 1)
                    logger.warning(f"{func.__name__} attempt {attempt + 1} failed: {e}. Retrying in {wait_time:.2f}s...")
                    time.sleep(wait_time)
            return None
        return wrapper
    return decorator

# ----------------------------
# Browser Management
# ----------------------------
def create_driver(headless=False):
    """Create and configure Chrome WebDriver"""
    chrome_options = Options()

    # Performance and stability options
    chrome_options.add_argument("--start-maximized")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.page_load_strategy = 'normal'

    if headless:
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--window-size=1920,1080")

    # Download preferences
    chrome_options.add_experimental_option("prefs", {
        "download.default_directory": os.path.abspath(DOWNLOAD_DIR),
        "download.prompt_for_download": False,
        "plugins.always_open_pdf_externally": True,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True
    })

    # Exclude automation flags
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)

    logger.info("Creating Chrome WebDriver...")
    return webdriver.Chrome(options=chrome_options)

def recreate_driver(headless=False):
    """Recreate the WebDriver after a crash"""
    global driver
    logger.warning("Recreating WebDriver due to session loss...")
    try:
        if driver:
            driver.quit()
    except:
        pass
    driver = create_driver(headless)
    return driver

# ----------------------------
# Download Verification
# ----------------------------
def wait_for_download(download_dir, timeout=DOWNLOAD_TIMEOUT, initial_files=None):
    """Wait for a new PDF download to complete"""
    if initial_files is None:
        initial_files = set(os.listdir(download_dir))

    logger.debug(f"Waiting for download to complete (timeout: {timeout}s)...")
    start_time = time.time()

    while time.time() - start_time < timeout:
        time.sleep(1)
        current_files = set(os.listdir(download_dir))

        # Check for .crdownload or .tmp files (download in progress)
        temp_files = [f for f in current_files if f.endswith(('.crdownload', '.tmp'))]
        if temp_files:
            logger.debug(f"Download in progress: {temp_files[0]}")
            continue

        # Check for new PDF files
        new_files = current_files - initial_files
        pdf_files = [f for f in new_files if f.endswith('.pdf')]

        if pdf_files:
            logger.info(f"Download completed: {pdf_files[0]}")
            return True

    logger.warning(f"Download timeout after {timeout}s")
    return False

def get_existing_downloads():
    """Get list of already downloaded PDF files"""
    try:
        return set([f for f in os.listdir(DOWNLOAD_DIR) if f.endswith('.pdf')])
    except Exception as e:
        logger.error(f"Error reading download directory: {e}")
        return set()

# ----------------------------
# Scraping Functions
# ----------------------------
@retry(max_attempts=3, exceptions=(WebDriverException, TimeoutException))
def get_issue_links(page_number):
    """Get all issue links from a specific archive page"""
    global driver

    try:
        url = f"{BASE_URL}?_paged={page_number}"
        logger.debug(f"Fetching page {page_number}: {url}")
        driver.get(url)

        # Random delay to avoid rate limiting
        time.sleep(DELAY_SECONDS + random.uniform(0, 1))

        links = driver.find_elements(By.CSS_SELECTOR, "a")
        issue_links = []

        for a in links:
            href = a.get_attribute("href")
            # Only include URLs that look like actual magazine issues
            if href and href.startswith(BASE_URL) and href != url:
                issue_links.append(href)

        unique_links = list(set(issue_links))
        logger.info(f"[Page {page_number}] Found {len(unique_links)} issue links")
        return unique_links

    except InvalidSessionIdException as e:
        logger.error(f"Browser session lost on page {page_number}: {e}")
        recreate_driver()
        raise

@retry(max_attempts=3, exceptions=(NoSuchElementException, TimeoutException))
def process_issue(issue_url, progress):
    """Process a single magazine issue and download PDF"""
    global driver

    # Check if already processed
    if issue_url in progress["completed"]:
        logger.info(f"Skipping already completed: {issue_url}")
        progress["skipped"].append(issue_url)
        return True

    try:
        logger.info(f"Processing: {issue_url}")

        # Get initial file list
        initial_files = set(os.listdir(DOWNLOAD_DIR))

        driver.get(issue_url)
        time.sleep(DELAY_SECONDS + random.uniform(0, 1))

        # Click "Read Magazine" button
        try:
            read_span = driver.find_element(By.XPATH, "//span[contains(text(), 'Read Magazine')]")
            driver.execute_script("arguments[0].scrollIntoView(true);", read_span)
            time.sleep(0.5)
            ActionChains(driver).move_to_element(read_span).click().perform()
            logger.debug(f"Clicked 'Read Magazine' button")
            time.sleep(DELAY_SECONDS * 2)  # Allow viewer to load
        except NoSuchElementException:
            logger.warning(f"'Read Magazine' button not found on: {issue_url}")
            progress["failed"].append({"url": issue_url, "reason": "No Read Magazine button"})
            save_progress(progress)
            return False

        # Click "Download PDF" button
        try:
            download_button = driver.find_element(By.CSS_SELECTOR, "span[data-name='btnDownloadPdf']")
            driver.execute_script("arguments[0].scrollIntoView(true);", download_button)
            time.sleep(0.5)
            ActionChains(driver).move_to_element(download_button).click().perform()
            logger.info("Clicked 'Download PDF' button")

            # Wait for download to complete
            if wait_for_download(DOWNLOAD_DIR, initial_files=initial_files):
                logger.info(f"Successfully downloaded: {issue_url}")
                progress["completed"].append(issue_url)
                save_progress(progress)
                return True
            else:
                logger.error(f"Download timeout for: {issue_url}")
                progress["failed"].append({"url": issue_url, "reason": "Download timeout"})
                save_progress(progress)
                return False

        except NoSuchElementException:
            logger.warning(f"'Download PDF' button not found on: {issue_url}")
            progress["failed"].append({"url": issue_url, "reason": "No Download button"})
            save_progress(progress)
            return False

    except InvalidSessionIdException as e:
        logger.error(f"Browser session lost on {issue_url}: {e}")
        recreate_driver()
        raise

    except WebDriverException as e:
        logger.error(f"WebDriver error on {issue_url}: {e}")
        recreate_driver()
        raise

    except Exception as e:
        logger.error(f"Unexpected error processing {issue_url}: {e}")
        progress["failed"].append({"url": issue_url, "reason": str(e)})
        save_progress(progress)
        return False

# ----------------------------
# Main Function
# ----------------------------
def main():
    """Main execution function"""
    global driver

    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='Download magazine PDFs from trains.com')
    parser.add_argument('--start-page', type=int, default=1, help='Starting page number (default: 1)')
    parser.add_argument('--end-page', type=int, default=92, help='Ending page number (default: 92)')
    parser.add_argument('--headless', action='store_true', help='Run browser in headless mode')
    parser.add_argument('--retry-failed', action='store_true', help='Retry previously failed downloads')

    # Authentication options
    auth_group = parser.add_argument_group('authentication options')
    auth_group.add_argument('--login', action='store_true', help='Perform login (will prompt for credentials)')
    auth_group.add_argument('--username', type=str, help='Username/email for login')
    auth_group.add_argument('--password', type=str, help='Password for login (not recommended, use prompt instead)')
    auth_group.add_argument('--use-cookies', action='store_true', help='Load and use saved session cookies')
    auth_group.add_argument('--save-cookies', action='store_true', help='Save session cookies after login')
    auth_group.add_argument('--cookies-file', type=str, default=COOKIES_FILE, help=f'Cookie file path (default: {COOKIES_FILE})')

    args = parser.parse_args()

    logger.info("="*60)
    logger.info("Magazine PDF Downloader Starting")
    logger.info(f"Pages: {args.start_page} to {args.end_page}")
    logger.info(f"Headless mode: {args.headless}")
    logger.info(f"Download directory: {os.path.abspath(DOWNLOAD_DIR)}")
    logger.info("="*60)

    # Load progress
    progress = load_progress()
    logger.info(f"Loaded progress: {len(progress['completed'])} completed, {len(progress['failed'])} failed")

    try:
        # Create WebDriver
        driver = create_driver(headless=args.headless)

        # Handle authentication
        logged_in = False

        # Try to load cookies first if requested
        if args.use_cookies or os.path.exists(args.cookies_file):
            logger.info("Attempting to load saved cookies...")
            if load_cookies(driver, args.cookies_file):
                if verify_login(driver):
                    logged_in = True
                    logger.info("Successfully authenticated using saved cookies")
                else:
                    logger.warning("Saved cookies are invalid or expired")

        # Perform login if requested or cookies failed
        if args.login and not logged_in:
            logger.info("Performing login...")
            if perform_login(driver, args.username, args.password):
                logged_in = True
                if args.save_cookies:
                    save_cookies(driver, args.cookies_file)
            else:
                logger.error("Login failed!")
                if not args.headless:
                    response = input("Continue without login? (y/n): ")
                    if response.lower() != 'y':
                        logger.info("Exiting due to failed login")
                        return
                else:
                    logger.warning("Continuing without authentication (downloads may fail)")

        # Save cookies if requested and logged in
        if logged_in and args.save_cookies and not args.use_cookies:
            save_cookies(driver, args.cookies_file)

        if logged_in:
            logger.info("Proceeding with authenticated session")
        else:
            logger.warning("Proceeding without authentication - subscriber content may not be accessible")

        # Collect all issue links
        logger.info(f"Collecting issue links from pages {args.start_page} to {args.end_page}...")
        all_issue_links = []

        for page in range(args.start_page, args.end_page + 1):
            try:
                links = get_issue_links(page)
                all_issue_links.extend(links)
            except Exception as e:
                logger.error(f"Failed to get links from page {page}: {e}")
                continue

        # Remove duplicates
        all_issue_links = list(set(all_issue_links))
        logger.info(f"Total unique issues found: {len(all_issue_links)}")

        # Filter out already completed unless retry-failed is set
        if not args.retry_failed:
            issues_to_process = [url for url in all_issue_links if url not in progress["completed"]]
        else:
            # Retry failed ones
            failed_urls = [item["url"] if isinstance(item, dict) else item for item in progress["failed"]]
            issues_to_process = [url for url in all_issue_links if url in failed_urls or url not in progress["completed"]]
            progress["failed"] = []  # Clear failed list

        logger.info(f"Issues to process: {len(issues_to_process)}")

        # Process each issue
        successful = 0
        failed = 0

        for i, issue_url in enumerate(issues_to_process, 1):
            logger.info(f"\n[{i}/{len(issues_to_process)}] Processing: {issue_url}")

            try:
                if process_issue(issue_url, progress):
                    successful += 1
                else:
                    failed += 1
            except Exception as e:
                logger.error(f"Failed to process {issue_url}: {e}")
                failed += 1
                continue

        # Final summary
        logger.info("\n" + "="*60)
        logger.info("Download Session Complete")
        logger.info(f"Successfully downloaded: {successful}")
        logger.info(f"Failed: {failed}")
        logger.info(f"Skipped (already completed): {len(progress.get('skipped', []))}")
        logger.info(f"Total completed overall: {len(progress['completed'])}")
        logger.info(f"Total failed overall: {len(progress['failed'])}")
        logger.info("="*60)

    except KeyboardInterrupt:
        logger.info("\nScript interrupted by user")

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)

    finally:
        # Clean up
        logger.info("Cleaning up...")
        try:
            if driver:
                driver.quit()
                logger.info("Browser closed successfully")
        except Exception as e:
            logger.error(f"Error closing browser: {e}")

        logger.info("Script finished")

# ----------------------------
# Entry Point
# ----------------------------
if __name__ == "__main__":
    main()
