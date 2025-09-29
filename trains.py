from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
import time
import os

# ----------------------------
# Config
# ----------------------------
BASE_URL = "https://www.trains.com/ctr/magazine/archive-access/"
DELAY_SECONDS = 2
DOWNLOAD_DIR = "downloads-ctr"

os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# ----------------------------
# Setup Selenium
# ----------------------------
chrome_options = Options()
chrome_options.add_argument("--start-maximized")
chrome_options.add_experimental_option("prefs", {
    "download.default_directory": os.path.abspath(DOWNLOAD_DIR),
    "download.prompt_for_download": False,
    "plugins.always_open_pdf_externally": True
})

driver = webdriver.Chrome(options=chrome_options)

# ----------------------------
# Helper Functions
# ----------------------------
def get_issue_links(page_number):
    driver.get(f"{BASE_URL}?_paged={page_number}")
    time.sleep(DELAY_SECONDS)
    links = driver.find_elements(By.CSS_SELECTOR, "a")
    issue_links = []
    for a in links:
        href = a.get_attribute("href")
        # Only include URLs that look like actual magazine issues
        if href and href.startswith(BASE_URL) and href != f"{BASE_URL}?_paged={page_number}":
            issue_links.append(href)
    return list(set(issue_links))  # Remove duplicates

def process_issue(issue_url):
    driver.get(issue_url)
    time.sleep(DELAY_SECONDS)
    try:
        # Click "Read Magazine"
        read_span = driver.find_element(By.XPATH, "//span[contains(text(), 'Read Magazine')]")
        driver.execute_script("arguments[0].scrollIntoView(true);", read_span)
        ActionChains(driver).move_to_element(read_span).click().perform()
        print(f"Clicked Read Magazine on: {issue_url}")
        time.sleep(DELAY_SECONDS * 2)  # Allow viewer to load

        # Click "Download PDF" button
        try:
            download_button = driver.find_element(By.CSS_SELECTOR, "span[data-name='btnDownloadPdf']")
            driver.execute_script("arguments[0].scrollIntoView(true);", download_button)
            ActionChains(driver).move_to_element(download_button).click().perform()
            print("Clicked Download PDF button.")
            time.sleep(DELAY_SECONDS)
        except Exception as e:
            print(f"Download PDF button not found or not clickable: {e}")

    except Exception as e:
        print(f"No 'Read Magazine' button on: {issue_url} — {e}")

# ----------------------------
# Main Loop
# ----------------------------
all_issue_links = []
for page in range(1, 92):  # Example: first 4 archive pages, increase as needed
    links = get_issue_links(page)
    print(f"[Page {page}] Found {len(links)} issue links")
    all_issue_links.extend(links)

all_issue_links = list(set(all_issue_links))  # Remove duplicates
print(f"Total issues to process: {len(all_issue_links)}")

for i, issue_url in enumerate(all_issue_links, 1):
    print(f"[{i}/{len(all_issue_links)}] Processing: {issue_url}")
    process_issue(issue_url)

driver.quit()
