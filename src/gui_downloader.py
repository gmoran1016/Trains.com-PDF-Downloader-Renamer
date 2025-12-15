"""
Magazine Downloader GUI
A PyQt5-based GUI for downloading train magazines from trains.com
"""

import sys
import os
import json
import threading
import time
import pickle
import logging
import random
import concurrent.futures
from pathlib import Path
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QCheckBox, QFileDialog, QTextEdit,
    QProgressBar, QGroupBox, QGridLayout, QComboBox, QMessageBox, QSpinBox
)
from PyQt5.QtCore import Qt, pyqtSignal, QObject, QThread
from PyQt5.QtGui import QFont, QColor, QTextCursor
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    WebDriverException,
    InvalidSessionIdException
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('scraper.log')
    ]
)
logger = logging.getLogger(__name__)

# Configuration constants
DELAY_SECONDS = 2
LOGIN_TIMEOUT = 30

# ============================
# Download Worker Thread
# ============================
class DownloadSignals(QObject):
    """Signals emitted by the download worker"""
    progress = pyqtSignal(int)
    status = pyqtSignal(str)
    finished = pyqtSignal()
    error = pyqtSignal(str)
    started = pyqtSignal()

class DownloadWorker(QThread):
    """Worker thread for handling downloads"""
    signals = DownloadSignals()

    def __init__(self, magazine_type, download_dir, username, password, headless=True, rename_files=True, download_trackplans=False, test_mode=False):
        super().__init__()
        self.magazine_type = magazine_type
        self.download_dir = download_dir
        self.username = username
        self.password = password
        self.headless = headless
        self.rename_files = rename_files
        self.download_trackplans = download_trackplans
        self.test_mode = test_mode
        self.driver = None
        self.is_running = True

    def log_status(self, message):
        """Emit status message and log it"""
        logger.info(message)
        self.signals.status.emit(message)

    def log_error(self, message):
        """Emit error message and log it"""
        logger.error(message)
        self.signals.error.emit(message)

    def setup_driver(self):
        """Setup Chrome WebDriver with robust configuration"""
        try:
            self.log_status("Setting up Chrome WebDriver...")
            
            chrome_options = Options()
            
            # Performance and stability options
            chrome_options.add_argument("--start-maximized")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.page_load_strategy = 'normal'
            
            if self.headless:
                chrome_options.add_argument("--headless")
                chrome_options.add_argument("--window-size=1920,1080")
            
            # Download preferences
            download_path = os.path.abspath(self.download_dir)
            self.log_status(f"Download directory set to: {download_path}")
            chrome_options.add_experimental_option("prefs", {
                "download.default_directory": download_path,
                "download.prompt_for_download": False,
                "plugins.always_open_pdf_externally": True,
                "download.directory_upgrade": True,
                "safebrowsing.enabled": True
            })
            
            # Exclude automation flags
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            
            self.driver = webdriver.Chrome(options=chrome_options)
            
            # Execute script to remove webdriver property
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            self.log_status("WebDriver initialized successfully")
            return True
        except Exception as e:
            self.log_error(f"Failed to setup WebDriver: {e}")
            return False

    def create_driver(self):
        """Create a new Chrome WebDriver instance for multithreading"""
        try:
            chrome_options = Options()
            
            # Performance and stability options
            chrome_options.add_argument("--start-maximized")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.page_load_strategy = 'normal'
            
            # Always headless for worker threads to avoid conflicts
            chrome_options.add_argument("--headless")
            chrome_options.add_argument("--window-size=1920,1080")
            
            # Download preferences
            download_path = os.path.abspath(self.download_dir)
            chrome_options.add_experimental_option("prefs", {
                "download.default_directory": download_path,
                "download.prompt_for_download": False,
                "plugins.always_open_pdf_externally": True,
                "download.directory_upgrade": True,
                "safebrowsing.enabled": True
            })
            
            # Exclude automation flags
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            
            driver = webdriver.Chrome(options=chrome_options)
            
            # Execute script to remove webdriver property
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            return driver
        except Exception as e:
            self.log_error(f"Failed to create WebDriver: {e}")
            return None

    def load_cookies_for_driver(self, driver):
        """Load saved session cookies into a specific driver instance"""
        cookies_file = "session_cookies.pkl"
        if not os.path.exists(cookies_file):
            return False

        try:
            driver.get("https://www.trains.com/")
            time.sleep(1)

            with open(cookies_file, 'rb') as f:
                cookies = pickle.load(f)

            for cookie in cookies:
                try:
                    driver.add_cookie(cookie)
                except Exception as e:
                    logger.debug(f"Could not add cookie: {e}")

            return True
        except Exception as e:
            self.log_error(f"Failed to load cookies for driver: {e}")
            return False

    def get_magazine_url(self):
        """Get the appropriate URL based on magazine type"""
        urls = {
            "Model Railroader": "https://www.trains.com/mrr/magazine/archive-access/",
            "Trains Magazine": "https://www.trains.com/trn/magazine/archive-access/",
            "Classic Toy Trains": "https://www.trains.com/ctt/magazine/archive-access/",
            "Classic Trains": "https://www.trains.com/ctr/magazine/archive-access/",
            "Garden Railways": "https://www.trains.com/grw/magazine/archive-access/"
        }
        return urls.get(self.magazine_type, urls["Model Railroader"])

    def load_cookies(self):
        """Load saved session cookies (shared across all trains.com sites)"""
        cookies_file = "session_cookies.pkl"
        if not os.path.exists(cookies_file):
            self.log_status("No saved session cookies found")
            return False

        try:
            self.log_status("Loading saved session cookies...")
            self.driver.get("https://www.trains.com/")
            time.sleep(1)

            with open(cookies_file, 'rb') as f:
                cookies = pickle.load(f)

            for cookie in cookies:
                try:
                    self.driver.add_cookie(cookie)
                except Exception as e:
                    logger.debug(f"Could not add cookie: {e}")

            self.log_status("Session cookies loaded successfully (shared across all trains.com sites)")
            return True
        except Exception as e:
            self.log_error(f"Failed to load cookies: {e}")
            return False

    def save_cookies(self):
        """Save session cookies for future use (shared across all trains.com sites)"""
        cookies_file = "session_cookies.pkl"
        try:
            cookies = self.driver.get_cookies()
            with open(cookies_file, 'wb') as f:
                pickle.dump(cookies, f)
            self.log_status("Session cookies saved for future use (shared across all trains.com sites)")
            return True
        except Exception as e:
            self.log_error(f"Failed to save cookies: {e}")
            return False

    def verify_login(self):
        """Check if user is logged in using shared trains.com cookies"""
        try:
            # First check on main trains.com site (cookies are shared across all sites)
            self.driver.get("https://www.trains.com/")
            time.sleep(2)

            page_source = self.driver.page_source.lower()
            is_logged_in = "log out" in page_source or "logout" in page_source

            if is_logged_in:
                self.log_status("Login verified successfully (shared cookies)")
                return True

            # If not logged in on main site, also check the specific magazine URL
            # (some magazines might have different access requirements)
            url = self.get_magazine_url()
            self.driver.get(url)
            time.sleep(2)

            page_source = self.driver.page_source.lower()
            is_logged_in = "log out" in page_source or "logout" in page_source

            if is_logged_in:
                self.log_status("Login verified successfully")
            else:
                self.log_status("Not currently logged in - you may need to login manually")

            return is_logged_in
        except Exception as e:
            self.log_error(f"Error verifying login: {e}")
            return False

    def perform_login(self):
        """Perform login to trains.com with manual fallback"""
        try:
            self.log_status("Navigating to trains.com for login...")
            self.driver.get("https://www.trains.com/")
            time.sleep(3)

            # Try automatic login first if credentials provided
            if self.username and self.password:
                self.log_status("Attempting automatic login...")
                if self.try_automatic_login():
                    return True

            # Fall back to manual login
            self.log_status("Automatic login failed or no credentials provided")
            self.log_status("Waiting for you to login manually in the browser window...")
            self.log_status("Once logged in, the program will continue automatically")

            # Wait for user to login manually
            max_wait = LOGIN_TIMEOUT * 2  # 60 seconds
            start_time = time.time()

            while time.time() - start_time < max_wait:
                if not self.is_running:
                    return False

                try:
                    # Check if logout/account info is visible (indicates logged in)
                    # Since cookies are shared, we can check on main site
                    self.driver.get("https://www.trains.com/")
                    if self.verify_login():
                        self.save_cookies()
                        self.log_status("Login successful! Continuing with downloads...")
                        return True
                except:
                    pass

                time.sleep(2)

            self.log_error("Login timeout - user did not complete login in time")
            return False

        except Exception as e:
            self.log_error(f"Error during login: {e}")
            return False

    def try_automatic_login(self):
        """Attempt automatic login with provided credentials"""
        try:
            # Try to find and click login button
            login_selectors = [
                (By.XPATH, "//a[contains(text(), 'Login') or contains(text(), 'LOG IN') or contains(text(), 'log in')]"),
                (By.XPATH, "//button[contains(text(), 'Login') or contains(text(), 'LOG IN') or contains(text(), 'log in')]"),
                (By.CSS_SELECTOR, "a[href*='login']"),
                (By.CSS_SELECTOR, ".login-link")
            ]

            login_trigger = None
            for by_type, selector in login_selectors:
                try:
                    elements = self.driver.find_elements(by_type, selector)
                    for element in elements:
                        if element.is_displayed():
                            login_trigger = element
                            break
                    if login_trigger:
                        break
                except:
                    continue

            if login_trigger:
                self.driver.execute_script("arguments[0].scrollIntoView(true);", login_trigger)
                time.sleep(0.5)
                login_trigger.click()
                time.sleep(3)

            # Try to find login form
            wait = WebDriverWait(self.driver, 10)
            username_field = None

            # Check main page first
            try:
                username_field = wait.until(EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "input[type='email'], input[name='username'], input[name='email'], input[id='username'], input[id='email']")
                ))
            except TimeoutException:
                # Check iframes
                iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
                for iframe in iframes:
                    try:
                        self.driver.switch_to.frame(iframe)
                        username_field = wait.until(EC.presence_of_element_located(
                            (By.CSS_SELECTOR, "input[type='email'], input[name='username'], input[name='email'], input[id='username'], input[id='email']")
                        ))
                        break
                    except TimeoutException:
                        self.driver.switch_to.default_content()
                        continue

            if username_field:
                # Fill credentials
                username_field.clear()
                username_field.send_keys(self.username)
                time.sleep(0.5)

                password_field = self.driver.find_element(By.CSS_SELECTOR, "input[type='password'], input[name='password'], input[id='password']")
                password_field.clear()
                password_field.send_keys(self.password)
                time.sleep(0.5)

                # Submit form
                submit_selectors = [
                    (By.CSS_SELECTOR, "button[type='submit']"),
                    (By.XPATH, "//button[contains(text(), 'Sign In') or contains(text(), 'Login')]"),
                    (By.CSS_SELECTOR, "input[type='submit']")
                ]

                submit_button = None
                for by_type, selector in submit_selectors:
                    try:
                        submit_button = self.driver.find_element(by_type, selector)
                        if submit_button and submit_button.is_displayed():
                            break
                    except:
                        continue

                if submit_button:
                    submit_button.click()
                else:
                    password_field.send_keys("\n")

                time.sleep(5)
                self.driver.switch_to.default_content()

                if self.verify_login():
                    self.save_cookies()
                    self.log_status("Automatic login successful!")
                    return True

            return False

        except Exception as e:
            self.log_error(f"Automatic login failed: {e}")
            return False

    def wait_for_downloads(self, timeout=120):
        """Wait for downloads to complete and move files to correct location"""
        import shutil
        start_time = time.time()
        initial_files = set(os.listdir(self.download_dir))
        
        # Also check the user's Downloads folder
        user_downloads = os.path.join(os.path.expanduser("~"), "Downloads")
        initial_downloads_files = set(os.listdir(user_downloads)) if os.path.exists(user_downloads) else set()
        
        while time.time() - start_time < timeout:
            if not self.is_running:
                break
            
            time.sleep(1)
            
            # Check both the specified download dir and user's Downloads folder
            current_files = set(os.listdir(self.download_dir))
            current_downloads_files = set(os.listdir(user_downloads)) if os.path.exists(user_downloads) else set()
            
            # Check for temporary download files (.crdownload, .tmp)
            temp_files = [f for f in current_files if f.endswith(('.crdownload', '.tmp', '.download'))]
            temp_files_downloads = [f for f in current_downloads_files if f.endswith(('.crdownload', '.tmp', '.download'))]
            
            if temp_files or temp_files_downloads:
                if temp_files:
                    self.log_status(f"Download in progress: {temp_files[0]}")
                if temp_files_downloads:
                    self.log_status(f"Download in progress in Downloads: {temp_files_downloads[0]}")
                continue
            
            # Check for new PDF files in both locations
            new_files = current_files - initial_files
            new_downloads_files = current_downloads_files - initial_downloads_files
            
            pdf_files = [f for f in new_files if f.lower().endswith('.pdf')]
            pdf_files_downloads = [f for f in new_downloads_files if f.lower().endswith('.pdf')]
            
            if pdf_files:
                self.log_status(f"Download completed: {pdf_files[0]}")
                return True
            
            if pdf_files_downloads:
                # Move the file from Downloads to the intended directory
                for pdf_file in pdf_files_downloads:
                    src_path = os.path.join(user_downloads, pdf_file)
                    dst_path = os.path.join(self.download_dir, pdf_file)
                    try:
                        shutil.move(src_path, dst_path)
                        self.log_status(f"Moved download to correct location: {pdf_file}")
                    except Exception as e:
                        self.log_error(f"Failed to move {pdf_file}: {e}")
                
                if pdf_files_downloads:
                    return True
        
        self.log_status(f"Download timeout after {timeout} seconds")
        return False

    def download_magazines(self):
        """Download magazines from the archive using proper scraping logic"""
        try:
            url = self.get_magazine_url()
            self.log_status(f"Accessing {self.magazine_type} archive: {url}")
            self.driver.get(url)
            time.sleep(4)

            # Collect all issue links from archive pages
            all_issue_links = []
            page_number = 1
            max_pages = 5 if self.test_mode else 50  # Limit to 5 pages in test mode

            while page_number <= max_pages:
                try:
                    # Check if we're still on the archive page
                    current_url = self.driver.current_url
                    if "archive-access" not in current_url:
                        self.log_status("No longer on archive page, stopping pagination")
                        break

                    self.log_status(f"Scanning archive page {page_number}...")

                    # Get all links on current page
                    links = self.driver.find_elements(By.TAG_NAME, "a")
                    page_links = []

                    for link in links:
                        href = link.get_attribute("href")
                        if href and href.startswith(url) and href != url and "magazine" in href.lower():
                            page_links.append(href)

                    unique_page_links = list(set(page_links))
                    if not unique_page_links:
                        self.log_status(f"No more issue links found on page {page_number}")
                        break

                    all_issue_links.extend(unique_page_links)
                    self.log_status(f"Found {len(unique_page_links)} issues on page {page_number}")

                    # Try to go to next page
                    try:
                        # Look for "Next" or pagination links
                        next_selectors = [
                            "a.next",
                            "a[rel='next']",
                            ".pagination a:last-child",
                            "a:contains('Next')",
                            "a:contains('>')"
                        ]

                        next_found = False
                        for selector in next_selectors:
                            try:
                                if selector.startswith("a:contains"):
                                    text = selector.split("'")[1]
                                    next_link = self.driver.find_element(By.XPATH, f"//a[contains(text(), '{text}')]")
                                else:
                                    next_link = self.driver.find_element(By.CSS_SELECTOR, selector)

                                if next_link and next_link.is_displayed():
                                    next_link.click()
                                    time.sleep(3)
                                    next_found = True
                                    break
                            except:
                                continue

                        if not next_found:
                            # Try URL manipulation
                            next_url = f"{url}?_paged={page_number + 1}"
                            self.driver.get(next_url)
                            time.sleep(3)
                            next_found = True

                        if not next_found:
                            break

                    except Exception as e:
                        self.log_status(f"No more pages available: {e}")
                        break

                    page_number += 1

                except Exception as e:
                    self.log_error(f"Error on page {page_number}: {e}")
                    break

            # Remove duplicates
            all_issue_links = list(set(all_issue_links))
            self.log_status(f"Total unique issues found: {len(all_issue_links)}")

            if all_issue_links:
                # Limit to 5 issues in test mode
                if self.test_mode and len(all_issue_links) > 5:
                    all_issue_links = all_issue_links[:5]
                    self.log_status("Test mode: Limited to first 5 issues")
                
                self.signals.progress.emit(0)

                successful = 0
                failed = 0

                # Use multithreading for magazine downloads
                max_workers = 3 if not self.test_mode else 2  # Limit concurrent downloads
                self.log_status(f"Starting multithreaded download with {max_workers} concurrent workers...")
                
                def process_issue_with_driver(self, issue_url, worker_id):
                    """Process a single issue with its own driver instance"""
                    driver = None
                    try:
                        # Create a new driver instance for this thread
                        driver = self.create_driver()
                        
                        # Load existing session cookies
                        if not self.load_cookies_for_driver(driver):
                            self.log_status(f"Worker {worker_id}: Session cookies not available, skipping {issue_url}")
                            return False
                        
                        # Check for existing file first
                        issue_parts = issue_url.split('/')[-1].split('-')
                        if len(issue_parts) >= 2:
                            month = issue_parts[-2].capitalize()
                            year = issue_parts[-1][:4] if len(issue_parts[-1]) >= 4 else issue_parts[-1]
                            
                            for root, _, files in os.walk(self.download_dir):
                                for filename in files:
                                    if filename.lower().endswith('.pdf'):
                                        if (month.lower() in filename.lower() and 
                                            year in filename and 
                                            ('mrr' in filename.lower() or 'model' in filename.lower())):
                                            self.log_status(f"Worker {worker_id}: Issue already downloaded: {filename}")
                                            return True
                        
                        self.log_status(f"Worker {worker_id}: Processing {issue_url}")
                        
                        # Get initial files to detect new downloads
                        initial_files = set()
                        try:
                            initial_files = set(os.listdir(self.download_dir))
                        except Exception as e:
                            self.log_error(f"Worker {worker_id}: Failed to list download directory: {e}")
                            return False
                        self.log_status(f"Worker {worker_id}: Initial files in download dir: {len(initial_files)}")
                        
                        # Navigate to issue page
                        driver.get(issue_url)
                        time.sleep(DELAY_SECONDS + random.uniform(0, 1))
                        
                        # Click "Read Magazine" button
                        try:
                            read_span = driver.find_element(By.XPATH, "//span[contains(text(), 'Read Magazine')]")
                            driver.execute_script("arguments[0].scrollIntoView(true);", read_span)
                            time.sleep(0.5)
                            ActionChains(driver).move_to_element(read_span).click().perform()
                            self.log_status(f"Worker {worker_id}: Clicked 'Read Magazine' button")
                            time.sleep(DELAY_SECONDS * 2)
                        except Exception as e:
                            self.log_error(f"Worker {worker_id}: 'Read Magazine' button not found - {e}")
                            return False
                        
                        # Click "Download PDF" button
                        try:
                            download_button = driver.find_element(By.CSS_SELECTOR, "span[data-name='btnDownloadPdf']")
                            driver.execute_script("arguments[0].scrollIntoView(true);", download_button)
                            time.sleep(0.5)
                            ActionChains(driver).move_to_element(download_button).click().perform()
                            self.log_status(f"Worker {worker_id}: Clicked 'Download PDF' button")
                            
                            # Wait for download to complete (simplified for multithreading)
                            time.sleep(10)  # Wait 10 seconds for download
                            
                            # Check if PDF was downloaded
                            current_files = set(os.listdir(self.download_dir))
                            new_files = current_files - initial_files
                            pdf_files = [f for f in new_files if f.lower().endswith('.pdf')]
                            
                            if pdf_files:
                                self.log_status(f"Worker {worker_id}: Successfully downloaded PDF: {pdf_files[0]}")
                                return True
                            else:
                                self.log_error(f"Worker {worker_id}: PDF file not found after download")
                                return False
                                
                        except Exception as e:
                            self.log_error(f"Worker {worker_id}: 'Download PDF' button not found - {e}")
                            return False
                            
                    except Exception as e:
                        self.log_error(f"Worker {worker_id}: Error processing {issue_url}: {e}")
                        return False
                    finally:
                        if driver:
                            try:
                                driver.quit()
                            except:
                                pass
                
                # Process issues concurrently
                with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                    # Submit all tasks
                    future_to_url = {
                        executor.submit(process_issue_with_driver, self, url, i % max_workers): url 
                        for i, url in enumerate(all_issue_links)
                    }
                    
                    # Process completed tasks
                    for future in concurrent.futures.as_completed(future_to_url):
                        if not self.is_running:
                            break
                            
                        url = future_to_url[future]
                        try:
                            result = future.result()
                            if result:
                                successful += 1
                            else:
                                failed += 1
                                
                            # Update progress
                            completed = successful + failed
                            progress = int(completed / len(all_issue_links) * 100)
                            self.signals.progress.emit(progress)
                            
                        except Exception as e:
                            self.log_error(f"Error processing {url}: {e}")
                            failed += 1

                self.log_status(f"Download complete! Successful: {successful}, Failed: {failed}")
                if successful > 0:
                    self.log_status("PDFs have been downloaded successfully!")
                else:
                    self.log_status("No PDFs downloaded. Check that you're logged in and have access to the magazines.")
            else:
                self.log_status("No magazine issues found. You may need to be logged in to access them.")

        except Exception as e:
            self.log_error(f"Error during download: {e}")

    def process_issue(self, issue_url):
        """Process a single magazine issue and download PDF"""
        try:
            # Extract issue identifier from URL to check for existing file
            issue_parts = issue_url.split('/')[-1].split('-')
            if len(issue_parts) >= 2:
                month = issue_parts[-2].capitalize()
                year = issue_parts[-1][:4] if len(issue_parts[-1]) >= 4 else issue_parts[-1]
                expected_filename_pattern = f"*{month}*{year}*.pdf"
                
                # Check if file already exists (in any form)
                for root, _, files in os.walk(self.download_dir):
                    for filename in files:
                        if filename.lower().endswith('.pdf'):
                            # Check if this file matches the expected issue
                            if (month.lower() in filename.lower() and 
                                year in filename and 
                                ('mrr' in filename.lower() or 'model' in filename.lower())):
                                self.log_status(f"Issue already downloaded: {filename}")
                                return True
            
            self.log_status(f"Opening issue page: {issue_url}")
            # Get initial files to detect new downloads
            initial_files = set(os.listdir(self.download_dir))
            self.log_status(f"Initial files in download dir: {len(initial_files)}")

            self.driver.get(issue_url)
            time.sleep(DELAY_SECONDS + random.uniform(0, 1))

            # Click "Read Magazine" button
            try:
                read_span = self.driver.find_element(By.XPATH, "//span[contains(text(), 'Read Magazine')]")
                self.driver.execute_script("arguments[0].scrollIntoView(true);", read_span)
                time.sleep(0.5)
                ActionChains(self.driver).move_to_element(read_span).click().perform()
                self.log_status("Clicked 'Read Magazine' button")
                time.sleep(DELAY_SECONDS * 2)  # Allow viewer to load
            except Exception as e:
                self.log_error(f"'Read Magazine' button not found on: {issue_url} - {e}")
                return False

            # Click "Download PDF" button in the viewer
            try:
                download_button = self.driver.find_element(By.CSS_SELECTOR, "span[data-name='btnDownloadPdf']")
                self.driver.execute_script("arguments[0].scrollIntoView(true);", download_button)
                time.sleep(0.5)
                ActionChains(self.driver).move_to_element(download_button).click().perform()
                self.log_status("Clicked 'Download PDF' button")

                # Wait for download to complete
                if self.wait_for_downloads(timeout=120):
                    self.log_status(f"Successfully downloaded PDF from: {issue_url}")
                    return True
                else:
                    self.log_error(f"Download timeout for: {issue_url}")
                    return False

            except Exception as e:
                self.log_error(f"'Download PDF' button not found on: {issue_url} - {e}")
                # Try to find any PDF-related buttons
                try:
                    all_spans = self.driver.find_elements(By.TAG_NAME, "span")
                    pdf_spans = [s for s in all_spans if 'pdf' in s.get_attribute("data-name", "").lower() or 'download' in s.text.lower()]
                    if pdf_spans:
                        self.log_status(f"Found potential PDF spans: {[s.get_attribute('data-name') for s in pdf_spans[:3]]}")
                    else:
                        self.log_status("No PDF-related spans found")
                except:
                    pass
                return False

        except Exception as e:
            self.log_error(f"Error processing issue {issue_url}: {e}")
            return False

    def rename_and_organize_files(self):
        """Rename and organize downloaded PDF files"""
        try:
            self.log_status("Starting file organization...")
            
            # Import the renaming functions
            import re
            import shutil
            from calendar import month_abbr, month_name
            
            # Month lookup maps
            month_map = {abbr.upper(): name for abbr, name in zip(month_abbr, month_name) if abbr}
            month_num_map = {abbr.upper(): f"{i:02d}" for i, abbr in enumerate(month_abbr) if abbr}
            all_months = list(month_name)[1:]  # ['January', ..., 'December']
            
            def determine_prefix(filename):
                """Determine prefix based on filename containing 'train' or 'trn'."""
                if re.search(r"train|trn", filename, re.IGNORECASE):
                    return "TRN"
                elif re.search(r"CTR", filename, re.IGNORECASE):
                    return "CTR"
                return "MRR"
            
            def parse_filename(filepath):
                name, ext = os.path.splitext(os.path.basename(filepath))
                if ext.lower() != ".pdf":
                    return None

                prefix = determine_prefix(name)

                # 1️⃣ Numeric format _YYYY_MM or -YYYY-MM
                match_numeric = re.search(r"(?:^|_)(\d{4})[_-](\d{1,2})(?:\D|$)", name)
                if match_numeric:
                    year, month_num = match_numeric.groups()
                    year = int(year)
                    month_num = int(month_num)
                    if 1 <= month_num <= 12 and 1900 <= year <= 2099:
                        month_full = month_name[month_num]
                        return f"{prefix}-{month_num:02d}-{month_full}-{year}", str(year), month_full

                # 2️⃣ YYYYMM anywhere
                match_yyyymm = re.search(r"(\d{4})(\d{2})", name)
                if match_yyyymm:
                    year, month_num = match_yyyymm.groups()
                    year = int(year)
                    month_num = int(month_num)
                    if 1 <= month_num <= 12 and 1900 <= year <= 2099:
                        month_full = month_name[month_num]
                        return f"{prefix}-{month_num:02d}-{month_full}-{year}", str(year), month_full

                # 3️⃣ DDMMMYYYY or DDMMMYY
                match_ddmmmyyyy = re.search(r"(\d{1,2})?([A-Za-z]{3})[-_]?(\d{2,4})", name)
                if match_ddmmmyyyy:
                    _, month_abbr, year = match_ddmmmyyyy.groups()
                    month_abbr = month_abbr[:3].upper()
                    if month_abbr not in month_map:
                        return None
                    month_full = month_map[month_abbr]
                    month_num = month_num_map[month_abbr]

                    year = int(year)
                    if year < 100:
                        year += 2000
                    if not (1900 <= year <= 2099):
                        return None
                    return f"{prefix}-{month_num}-{month_full}-{year}", str(year), month_full

                # 4️⃣ MMMYY or MMMYYYY anywhere
                match_mmmyy = re.search(r"([A-Za-z]{3})(\d{2,4})", name)
                if match_mmmyy:
                    month_abbr, year = match_mmmyy.groups()
                    month_abbr = month_abbr[:3].upper()
                    if month_abbr not in month_map:
                        return None
                    month_full = month_map[month_abbr]
                    month_num = month_num_map[month_abbr]

                    year = int(year)
                    if year < 100:
                        year += 2000
                    if not (1900 <= year <= 2099):
                        return None
                    return f"{prefix}-{month_num}-{month_full}-{year}", str(year), month_full

                return None
            
            def get_unique_path(base_path):
                if not os.path.exists(base_path):
                    return base_path
                root, ext = os.path.splitext(base_path)
                counter = 1
                new_path = f"{root}-{counter}{ext}"
                while os.path.exists(new_path):
                    counter += 1
                    new_path = f"{root}-{counter}{ext}"
                return new_path
            
            # Organize PDFs in the download directory
            organized_count = 0
            skipped_count = 0
            for root, _, files in os.walk(self.download_dir):
                # Skip the Organized folder itself
                if "Organized" in root:
                    continue
                    
                for filename in files:
                    if not filename.lower().endswith('.pdf'):
                        continue
                        
                    filepath = os.path.join(root, filename)
                    parsed = parse_filename(filepath)
                    if not parsed:
                        self.log_status(f"Skipping {filename} (unexpected format)")
                        continue

                    new_name, year, month = parsed
                    year_folder = os.path.join(self.download_dir, "Organized", year)
                    os.makedirs(year_folder, exist_ok=True)

                    new_path = os.path.join(year_folder, new_name + ".pdf")
                    
                    # Check if already organized
                    if os.path.exists(new_path):
                        self.log_status(f"Already organized: {filename}")
                        skipped_count += 1
                        continue
                    
                    unique_path = get_unique_path(new_path)

                    shutil.move(filepath, unique_path)
                    self.log_status(f"Organized: {filename} -> {os.path.basename(unique_path)}")
                    organized_count += 1
            
            self.log_status(f"File organization completed! Organized {organized_count} files, skipped {skipped_count} already organized.")
            
        except Exception as e:
            self.log_error(f"Error during file organization: {e}")

    def download_trackplans_data(self):
        """Download trackplans from Model Railroader database"""
        try:
            self.log_status("Starting trackplan download...")
            
            # Import required modules
            import requests
            from bs4 import BeautifulSoup
            import re
            
            # Helper to sanitize folder names
            def clean_filename(name):
                return re.sub(r'[\\/*?:"<>|]', "_", name)
            
            # Get all subpage links from an index page
            def get_subpage_links(index_url):
                subpages = []
                try:
                    resp = requests.get(index_url)
                    resp.raise_for_status()
                    soup = BeautifulSoup(resp.text, "html.parser")
                    for a in soup.find_all("a", href=True):
                        href = a['href']
                        # Filter only track plan subpages
                        if "/track-plan-database/" in href and href.count("/") > 5:
                            if href.startswith('/'):
                                href = "https://www.trains.com" + href
                            subpages.append(href)
                except Exception as e:
                    self.log_error(f"Error fetching {index_url}: {e}")
                return list(set(subpages))  # Remove duplicates
            
            # Scrape a single subpage
            def scrape_subpage(subpage_url):
                try:
                    resp = requests.get(subpage_url)
                    resp.raise_for_status()
                    soup = BeautifulSoup(resp.text, "html.parser")

                    # Get title for folder name
                    h1 = soup.find("h1")
                    title = h1.text.strip() if h1 else "untitled"
                    folder_name = clean_filename(title)
                    folder_path = os.path.join(self.download_dir, "Trackplans", folder_name)
                    
                    # Check if already downloaded
                    if os.path.exists(folder_path):
                        self.log_status(f"Trackplan already downloaded: {title}")
                        return True
                    
                    os.makedirs(folder_path, exist_ok=True)

                    # Save article text
                    article_text = ""
                    entry_content = soup.find("div", class_="entry-content")
                    if entry_content:
                        article_text = entry_content.get_text(separator="\n").strip()
                    with open(os.path.join(folder_path, "article.txt"), "w", encoding="utf-8") as f:
                        f.write(article_text)

                    # Find PDF link
                    pdf_link = None
                    for a in soup.find_all("a", href=True):
                        if a['href'].lower().endswith(".pdf"):
                            pdf_link = a['href']
                            break

                    if pdf_link:
                        pdf_resp = requests.get(pdf_link)
                        pdf_resp.raise_for_status()
                        pdf_filename = os.path.basename(pdf_link)
                        pdf_path = os.path.join(folder_path, pdf_filename)
                        with open(pdf_path, "wb") as f:
                            f.write(pdf_resp.content)
                        self.log_status(f"Downloaded trackplan: {title}")
                        return True
                    else:
                        self.log_status(f"No PDF found for: {title}")
                        return False

                except Exception as e:
                    self.log_error(f"Error scraping {subpage_url}: {e}")
                    return False
            
            # Main trackplan download logic
            all_subpages = []
            
            # Crawl index pages (limited in test mode)
            max_index_pages = 5 if self.test_mode else 47
            for i in range(1, max_index_pages + 1):
                if i == 1:
                    index_url = "https://www.trains.com/mrr/how-to/track-plan-database/"
                else:
                    index_url = f"https://www.trains.com/mrr/how-to/track-plan-database/?_section=how-to%2Ctrack-plan-database&_paged={i}"
                self.log_status(f"Scanning trackplan index page {i}...")
                subpages = get_subpage_links(index_url)
                all_subpages.extend(subpages)

            # Remove duplicates
            all_subpages = list(set(all_subpages))
            self.log_status(f"Found {len(all_subpages)} trackplan pages.")
            
            # Limit to 5 trackplans in test mode
            if self.test_mode and len(all_subpages) > 5:
                all_subpages = all_subpages[:5]
                self.log_status("Test mode: Limited to first 5 trackplans")
            
            # Scrape each subpage concurrently
            successful = 0
            self.log_status(f"Starting to download {len(all_subpages)} trackplans...")
            
            # Use multithreading for trackplan downloads
            max_workers = 5 if not self.test_mode else 2  # More workers for trackplans since they use requests
            self.log_status(f"Starting multithreaded trackplan download with {max_workers} concurrent workers...")
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Submit all tasks
                future_to_url = {
                    executor.submit(scrape_subpage, url): url 
                    for url in all_subpages
                }
                
                # Process completed tasks
                for future in concurrent.futures.as_completed(future_to_url):
                    if not self.is_running:
                        break
                        
                    url = future_to_url[future]
                    try:
                        result = future.result()
                        if result:
                            successful += 1
                            
                    except Exception as e:
                        self.log_error(f"Error processing trackplan {url}: {e}")
            
            self.log_status(f"Trackplan download completed! Downloaded {successful}/{len(all_subpages)} trackplans.")
            
        except Exception as e:
            self.log_error(f"Error during trackplan download: {e}")

    def run(self):
        """Main worker thread execution"""
        try:
            self.signals.started.emit()
            
            # Create download directory
            os.makedirs(self.download_dir, exist_ok=True)

            # Setup driver
            if not self.setup_driver():
                self.log_error("Failed to setup WebDriver")
                self.signals.finished.emit()
                return

            # Try to load existing session
            if not self.load_cookies():
                # Need to login
                if not self.perform_login():
                    self.log_error("Login failed or was cancelled")
                    self.signals.finished.emit()
                    return

            # Verify login
            if not self.verify_login():
                self.log_status("Warning: Could not verify login, attempting downloads anyway...")

            # Download magazines
            self.download_magazines()

            # Rename and organize files if requested
            if self.rename_files:
                self.rename_and_organize_files()

            # Download trackplans if requested and magazine is Model Railroader
            if self.download_trackplans and self.magazine_type == "Model Railroader":
                self.download_trackplans_data()

            self.log_status("All operations completed!")

        except Exception as e:
            self.log_error(f"Unexpected error in worker thread: {e}")
        finally:
            # Cleanup
            self.is_running = False  # Mark as not running
            if self.driver:
                try:
                    self.driver.quit()
                except:
                    pass
            self.signals.finished.emit()

    def stop(self):
        """Stop the worker thread"""
        self.is_running = False
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass


# ============================
# Main GUI Application
# ============================
class MagazineDownloaderGUI(QMainWindow):
    """Main GUI window for magazine downloader"""

    def __init__(self):
        super().__init__()
        self.worker = None
        self.worker_thread = None
        self.selected_magazines = []
        self.current_magazine_index = 0
        self.init_ui()
        self.setWindowTitle("Train Magazine Downloader")
        self.setGeometry(100, 100, 900, 700)

    def init_ui(self):
        """Initialize the user interface"""
        # Central widget and main layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(15, 15, 15, 15)

        # Title
        title = QLabel("Train Magazine Downloader")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title.setFont(title_font)
        main_layout.addWidget(title)

        # Magazine Selection Group
        mag_group = self.create_magazine_group()
        main_layout.addWidget(mag_group)

        # Credentials Group
        cred_group = self.create_credentials_group()
        main_layout.addWidget(cred_group)

        # Download Settings Group
        settings_group = self.create_settings_group()
        main_layout.addWidget(settings_group)

        # Additional Options Group
        options_group = self.create_options_group()
        main_layout.addWidget(options_group)

        # Progress Group
        progress_group = self.create_progress_group()
        main_layout.addWidget(progress_group)

        # Buttons
        buttons_layout = QHBoxLayout()
        
        self.start_button = QPushButton("Start Download")
        self.start_button.setStyleSheet("background-color: #4CAF50; color: white; padding: 8px; font-weight: bold;")
        self.start_button.clicked.connect(self.start_download)
        buttons_layout.addWidget(self.start_button)

        self.stop_button = QPushButton("Stop")
        self.stop_button.setStyleSheet("background-color: #f44336; color: white; padding: 8px; font-weight: bold;")
        self.stop_button.clicked.connect(self.stop_download)
        self.stop_button.setEnabled(False)
        buttons_layout.addWidget(self.stop_button)

        main_layout.addLayout(buttons_layout)
        main_layout.addStretch()

    def create_magazine_group(self):
        """Create magazine selection group"""
        group = QGroupBox("Select Magazines")
        layout = QVBoxLayout()

        self.magazine_checkboxes = {}
        magazines = [
            "Model Railroader",
            "Trains Magazine",
            "Classic Toy Trains",
            "Classic Trains",
            "Garden Railways"
        ]
        layout.addWidget(QLabel("Select one or more magazines:"))
        for mag in magazines:
            cb = QCheckBox(mag)
            self.magazine_checkboxes[mag] = cb
            layout.addWidget(cb)

        group.setLayout(layout)
        return group

    def create_credentials_group(self):
        """Create credentials input group"""
        group = QGroupBox("Credentials")
        layout = QGridLayout()

        layout.addWidget(QLabel("Username/Email:"), 0, 0)
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Enter your trains.com username or email")
        layout.addWidget(self.username_input, 0, 1)

        layout.addWidget(QLabel("Password:"), 1, 0)
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Enter your password (optional)")
        self.password_input.setEchoMode(QLineEdit.Password)
        layout.addWidget(self.password_input, 1, 1)

        self.use_saved_login = QCheckBox("Use saved login session if available")
        self.use_saved_login.setChecked(True)
        layout.addWidget(self.use_saved_login, 2, 0, 1, 2)

        layout.setColumnStretch(1, 1)
        group.setLayout(layout)
        return group

    def create_settings_group(self):
        """Create download settings group"""
        group = QGroupBox("Download Settings")
        layout = QGridLayout()

        layout.addWidget(QLabel("Download Location (auto-set per magazine):"), 0, 0)
        self.download_path = QLineEdit()
        self.download_path.setReadOnly(True)
        layout.addWidget(self.download_path, 0, 1)

        self.headless_checkbox = QCheckBox("Run browser in background (headless)")
        self.headless_checkbox.setChecked(True)
        layout.addWidget(self.headless_checkbox, 1, 0, 1, 2)

        layout.setColumnStretch(1, 1)
        group.setLayout(layout)
        return group

    def create_progress_group(self):
        """Create progress tracking group"""
        group = QGroupBox("Progress")
        layout = QVBoxLayout()

        layout.addWidget(QLabel("Status:"))
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        layout.addWidget(QLabel("Log Output:"))
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setMaximumHeight(200)
        layout.addWidget(self.log_output)

        group.setLayout(layout)
        return group

    def create_options_group(self):
        """Create additional options group"""
        group = QGroupBox("Additional Options")
        layout = QVBoxLayout()

        # Rename files after download checkbox
        self.rename_checkbox = QCheckBox("Rename and organize files after download")
        self.rename_checkbox.setChecked(True)
        layout.addWidget(self.rename_checkbox)

        # Download trackplans checkbox (only enabled for Model Railroader)
        self.trackplans_checkbox = QCheckBox("Download trackplans (Model Railroader only)")
        self.trackplans_checkbox.setChecked(False)
        self.trackplans_checkbox.setEnabled(False)  # Initially disabled
        layout.addWidget(self.trackplans_checkbox)

        # Test mode checkbox
        self.test_mode_checkbox = QCheckBox("Test mode (limit to 5 pages/issues)")
        self.test_mode_checkbox.setChecked(False)
        layout.addWidget(self.test_mode_checkbox)

        # Multithreading info
        multithreading_info = QLabel("⚡ Downloads use multithreading for faster processing\n   (3 concurrent magazine downloads, 5 concurrent trackplans)")
        multithreading_info.setStyleSheet("color: #666; font-size: 10px;")
        layout.addWidget(multithreading_info)

        group.setLayout(layout)
        return group


    def get_default_download_path(self, magazine_type):
        """Get default download path based on magazine type"""
        paths = {
            "Model Railroader": os.path.abspath("downloads-MRR"),
            "Trains Magazine": os.path.abspath("downloads-Trains"),
            "Classic Toy Trains": os.path.abspath("downloads-CTT"),
            "Classic Trains": os.path.abspath("downloads-CTR"),
            "Garden Railways": os.path.abspath("downloads-GRW")
        }
        return paths.get(magazine_type, os.path.abspath("downloads"))



    def log_message(self, message):
        """Add message to log output"""
        self.log_output.moveCursor(QTextCursor.End)
        self.log_output.insertPlainText(message + "\n")
        self.log_output.moveCursor(QTextCursor.End)

    def start_download(self):
        """Start the download process"""
        # Get selected magazines
        selected_magazines = [mag for mag, cb in self.magazine_checkboxes.items() if cb.isChecked()]
        if not selected_magazines:
            QMessageBox.warning(self, "Error", "Please select at least one magazine")
            return

        # Validate inputs
        username = self.username_input.text().strip()

        # Disable start button, enable stop button
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.progress_bar.setValue(0)
        self.log_output.setPlainText("")

        # Enable trackplans checkbox only if Model Railroader is selected
        self.trackplans_checkbox.setEnabled("Model Railroader" in selected_magazines)
        if "Model Railroader" not in selected_magazines:
            self.trackplans_checkbox.setChecked(False)

        # Set up for sequential downloads
        self.selected_magazines = selected_magazines
        self.current_magazine_index = 0
        self.start_next_download()

    def start_next_download(self):
        """Start the next magazine download in the sequence"""
        if self.current_magazine_index >= len(self.selected_magazines):
            # All downloads completed
            self.start_button.setEnabled(True)
            self.stop_button.setEnabled(False)
            self.log_message("All downloads completed!")
            QMessageBox.information(self, "Complete", "All downloads have completed!")
            return

        magazine = self.selected_magazines[self.current_magazine_index]
        download_dir = self.get_default_download_path(magazine)
        self.download_path.setText(download_dir)

        self.log_message(f"Starting download for {magazine} ({self.current_magazine_index + 1}/{len(self.selected_magazines)})")

        # Create and start worker thread
        password = self.password_input.text()

        self.worker = DownloadWorker(
            magazine_type=magazine,
            download_dir=download_dir,
            username=self.username_input.text().strip(),
            password=password,
            headless=self.headless_checkbox.isChecked(),
            rename_files=self.rename_checkbox.isChecked(),
            download_trackplans=self.trackplans_checkbox.isChecked() and magazine == "Model Railroader",
            test_mode=self.test_mode_checkbox.isChecked()
        )

        # Connect signals
        self.worker.signals.progress.connect(self.on_progress_update)
        self.worker.signals.status.connect(self.log_message)
        self.worker.signals.error.connect(self.on_download_error)
        self.worker.signals.finished.connect(self.on_download_finished)
        self.worker.signals.started.connect(self.on_download_started)

        # Start worker thread
        self.worker.start()

    def stop_download(self):
        """Stop the download process"""
        if self.worker:
            self.log_message("Stopping download...")
            self.worker.stop()

    def on_download_started(self):
        """Called when download starts"""
        self.progress_bar.setValue(0)
        self.log_message("Download started...")

    def on_progress_update(self, value):
        """Update progress bar"""
        self.progress_bar.setValue(value)

    def on_download_error(self, error_message):
        """Handle download error"""
        self.log_message(f"ERROR: {error_message}")

    def on_download_finished(self):
        """Called when download finishes"""
        current_magazine = self.selected_magazines[self.current_magazine_index]
        self.log_message(f"Download for {current_magazine} completed!")
        self.worker = None

        # Start next download
        self.current_magazine_index += 1
        self.start_next_download()

    def closeEvent(self, event):
        """Handle window close event"""
        if self.worker and self.worker.is_running:
            reply = QMessageBox.question(
                self, "Confirm Exit",
                "Download is in progress. Do you want to stop and exit?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.worker.stop()
                self.worker.wait()
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()


def main():
    """Main entry point"""
    app = QApplication(sys.argv)
    window = MagazineDownloaderGUI()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
