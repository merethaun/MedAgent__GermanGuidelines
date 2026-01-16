import re
import shutil
import subprocess
import time
from datetime import date
from typing import List, Tuple

from pydantic import HttpUrl
from selenium import webdriver
from selenium.common import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.ui import WebDriverWait

from app.constants.awmf_website_constants import PATTERN_GUIDELINE_DETAIL_PAGE, PATTERN_GUIDELINE_REGISTRATION_PAGE
from app.exceptions.knowledge.guidelines import WebsiteNotAsExpectedError, handle_website_not_as_excepted_error
from app.models.knowledge.guidelines import (
    AWMFSearchResult, AWMFExtractedGuidelineMetadata, GuidelineEntry, GuidelineValidityInformation,
    OrganizationEntry, GuidelineDownloadInformation,
)
from app.utils.logger import setup_logger

logger = setup_logger(__name__)
chrome_driver_setup_logger = setup_logger("chrome_driver_setup", log_to_console=False)


class AWMFWebsiteInteractionService:
    """
    Service layer to manage interactions with AWMF-website (fetching information, etc.)
    """
    
    @staticmethod
    def _setup_driver():
        """
        Initializes a headless Chrome webdriver for scraping.
        """
        logger.debug("Setting up Chrome webdriver with headless options")
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        
        # Make sure chromedriver is available
        if shutil.which("chromedriver") is None:
            logger.info("Installing chromedriver...")
            try:
                logger.debug("Running apt update...")
                apt_update = subprocess.run(["apt", "update"], capture_output=True, text=True, check=True)
                chrome_driver_setup_logger.debug("apt update output:\n" + apt_update.stdout)
                
                logger.debug("Installing chromium-driver package...")
                apt_install = subprocess.run(
                    ["apt", "install", "-y", "chromium-driver"], capture_output=True, text=True, check=True,
                )
                chrome_driver_setup_logger.debug("apt install output:\n" + apt_install.stdout)
            except subprocess.CalledProcessError as e:
                error_msg = f"Failed to install chromedriver: {str(e)}"
                chrome_driver_setup_logger.error(error_msg)
                logger.error(error_msg)
                raise RuntimeError(error_msg) from e
            logger.info("Chromedriver installation complete")
        else:
            logger.debug("Chromedriver already installed")
        
        logger.debug("Initializing Chrome webdriver service...")
        webdriver_service = Service("/usr/bin/chromedriver")
        driver = webdriver.Chrome(service=webdriver_service, options=chrome_options)
        logger.debug("Chromedriver initialized successfully")
        return driver
    
    def _close_driver(self, driver):
        """
        Properly shuts down the Chrome driver.
        """
        logger.debug("Closing Chrome webdriver...")
        driver.quit()
        logger.debug("Chrome webdriver closed successfully")
    
    def extract_detail_urls_from_search(self, url: str) -> AWMFSearchResult:
        """
        Extracts all guideline detail page URLs from a given AWMF search URL.
        """
        logger.info(f"Starting URL extraction from search page: {url}")
        driver = self._setup_driver()
        try:
            logger.debug(f"Navigating to search URL: {url}")
            driver.get(url)
            
            expected_count = self._extract_expected_guideline_count(url, driver)
            self._scroll_to_reveal_all(url, driver)
            detail_urls, non_pdf_containing_urls = self._extract_detail_links(url, driver)
            
            result = AWMFSearchResult(
                expected_count=expected_count,
                valid_found=len(detail_urls),
                non_pdf_found=len(non_pdf_containing_urls),
                extracted_guideline_pdf_urls=[
                    HttpUrl(url) for url in detail_urls
                ],
                extracted_guideline_registration_urls=[
                    HttpUrl(url) for url in non_pdf_containing_urls
                ],
            )
            logger.info(
                f"Successfully extracted {result.valid_found} valid and {result.non_pdf_found} non-PDF URLs from search",
            )
            return result
        except Exception as e:
            logger.error(f"Failed to extract detail URLs from search at {url}: {str(e)}", exc_info=True)
            raise
        finally:
            self._close_driver(driver)
    
    @handle_website_not_as_excepted_error(logger=logger)
    def _extract_expected_guideline_count(self, url: str, driver) -> int:
        logger.debug("Extracting expected guideline count...")
        expected_text = WebDriverWait(driver, 15).until(
            lambda d: (t := d.find_element(By.XPATH, "//*[contains(text(), 'Treffer')]")).text.strip() or None,
        )
        match = re.search(r"\d+", expected_text)
        if match:
            count = int(match.group())
            logger.debug(f"Successfully extracted expected guideline count: {count}")
            return count
        else:
            error_msg = f"Could not extract number of guidelines from 'Treffer' text: {expected_text}"
            logger.error(error_msg)
            raise WebsiteNotAsExpectedError(url=url, concrete_problem=error_msg)
    
    @handle_website_not_as_excepted_error(logger=logger)
    def _scroll_to_reveal_all(self, url: str, driver):
        logger.debug("Starting scroll process to reveal all guidelines...")
        wait = WebDriverWait(driver, 30)
        
        def scroll():
            logger.debug("Executing single scroll action...")
            container = wait.until(
                expected_conditions.presence_of_element_located(
                    (
                        By.CSS_SELECTOR,
                        "#menu_content_container > app-tabs > ion-tabs > div > ion-router-outlet > app-suche > ion-content",
                    ),
                ),
            )
            scrollable = driver.execute_script(
                "return arguments[0].shadowRoot.querySelector('main.inner-scroll.scroll-y');",
                container,
            )
            previous = driver.execute_script("return arguments[0].scrollTop;", scrollable)
            driver.execute_script("arguments[0].scrollTop += 5000;", scrollable)
            time.sleep(2)
            current = driver.execute_script("return arguments[0].scrollTop;", scrollable)
            scroll_progress = current > previous
            logger.debug(f"Scroll action completed - Progress made: {scroll_progress}")
            return scroll_progress
        
        max_attempts_per_scrolling = 3
        attempts_remaining = max_attempts_per_scrolling
        while True:
            logger.debug(f"Scroll attempt remaining: {attempts_remaining}")
            if scroll():
                attempts_remaining = max_attempts_per_scrolling
            else:
                attempts_remaining -= 1
            
            try:
                no_more_results_text = driver.find_element(
                    By.XPATH, "//*[contains(text(), 'Ihre Suche lieferte keine weiteren Treffer.')]",
                )
                if no_more_results_text:
                    logger.info("Search completed: No more results text found")
                    break
            except:
                logger.debug("No 'end of results' text found yet")
            
            if attempts_remaining == 0:
                logger.warning("Maximum scroll attempts reached, proceeding with current results")
                break
        
        logger.info("Scroll process completed")
    
    @handle_website_not_as_excepted_error(logger=logger)
    def _extract_detail_links(self, url, driver) -> Tuple[List[str], List[str]]:
        logger.debug("Starting extraction of detail links...")
        elements = driver.find_elements(By.XPATH, "//a[text() = @title]")
        if not elements:
            error_msg = "No elements with matching @title found on page — selector may be broken"
            logger.error(error_msg)
            raise WebsiteNotAsExpectedError(url=url, concrete_problem=error_msg)
        
        links = {
            el.get_attribute("href").strip()
            for el in elements
            if el.get_attribute("href")
        }
        
        if not links:
            error_msg = "Anchor elements found, but none contained valid href attributes"
            logger.error(error_msg)
            raise WebsiteNotAsExpectedError(url=url, concrete_problem=error_msg)
        
        matching_links = []
        non_matching_links = []
        for link in links:
            if PATTERN_GUIDELINE_DETAIL_PAGE.search(link):
                logger.debug(f"Found guideline detail URL: {link}")
                matching_links.append(link)
            elif PATTERN_GUIDELINE_REGISTRATION_PAGE.search(link):
                logger.debug(f"Found guideline registration URL: {link}")
                non_matching_links.append(link)
            else:
                logger.debug(f"Found non-matching URL: {link}")
                non_matching_links.append(link)
        
        logger.info(
            f"Link extraction complete - Found {len(matching_links)} matching and {len(non_matching_links)} non-matching URLs",
        )
        return matching_links, non_matching_links
    
    @handle_website_not_as_excepted_error(logger=logger)
    def extract_guideline_metadata_from_detail_page(self, url: str) -> AWMFExtractedGuidelineMetadata:
        logger.info(f"Starting metadata extraction from {url}")
        driver = self._setup_driver()
        try:
            logger.debug(f"Navigating to detail page URL: {url}")
            driver.get(url)
            
            basic_details = self._get_basic_details(url, driver)
            actuality_details = self._get_actuality_details(url, driver)
            download_url = self._get_pdf_download_url(url, driver)
            leading_orgs, other_contributing_orgs = self._get_contributing_organizations(url, driver)
            keywords, goal_definition = self._get_content_details(url, driver)
            target_patient_group, care_area = self._get_patient_description(url, driver)
            
            logger.debug("Creating AWMFExtractedGuidelineMetadata object...")
            extracted_metadata = AWMFExtractedGuidelineMetadata(
                guideline_details_website=HttpUrl(url),
                awmf_register_number=basic_details[0],
                title=basic_details[1],
                awmf_class=basic_details[2],
                download_url=download_url,
                version=actuality_details[0],
                date_of_guideline_creation=actuality_details[1],
                date_until_valid=actuality_details[2],
                leading_publishing_organizations=leading_orgs,
                further_organizations=other_contributing_orgs,
                keywords=keywords,
                goal=goal_definition,
                target_patients=target_patient_group,
                care_area=care_area,
            )
            
            logger.info(f"Successfully extracted metadata for guideline {basic_details[0]}")
            return extracted_metadata
        finally:
            self._close_driver(driver)
    
    @handle_website_not_as_excepted_error(logger=logger)
    def _get_basic_details(self, url: str, driver) -> Tuple[str, str, str]:
        """
        Returns AWMF register number (ddd-ddd), guideline title, and guideline class (S1, S2k, ...).
        """
        logger.debug("Extracting basic guideline details...")
        expected_text = WebDriverWait(driver, 10).until(
            lambda d: (t := d.find_element(By.XPATH, "//*[contains(text(), 'Registernummer ')]")).text.strip() or None,
        )
        match = re.search(r"(\d{3})\s?-\s?(\d{3})", expected_text)
        if match:
            register_number = f"{match.group(1)}-{match.group(2)}"
            logger.debug(f"Extracted guideline register number: {register_number}")
        else:
            error_msg = f"Could not extract register number from 'Registernummer' text, which is {expected_text}"
            logger.error(error_msg)
            raise WebsiteNotAsExpectedError(url=url, concrete_problem=error_msg)
        
        try:
            title_element = WebDriverWait(driver, 10).until(
                expected_conditions.presence_of_element_located((By.CSS_SELECTOR, "div.guideline-details > h1")),
            )
            logger.debug("Title element found, extracting content...")
            print(title_element.get_attribute('innerHTML'))
            title_text = title_element.accessible_name.strip()
        except TimeoutException:
            error_msg = "The element 'div.guideline-details > h1' was not found within the timeout period."
            logger.error(error_msg)
            raise WebsiteNotAsExpectedError(url=url, concrete_problem=error_msg)
        
        if not title_text:
            error_msg = "Extracted guideline title is empty or not present."
            logger.error(error_msg)
            raise WebsiteNotAsExpectedError(url=url, concrete_problem=error_msg)
        
        match = re.search(r"^(S.*)-Leitlinie (.*)$", title_text)
        if match:
            guideline_class = match.group(1)
            title = match.group(2)
            logger.debug(f"Extracted guideline class: {guideline_class}")
            logger.debug(f"Extracted guideline title: {title}")
        else:
            error_msg = f"Could not extract guideline class and title from text: {title_element}"
            logger.error(error_msg)
            raise WebsiteNotAsExpectedError(url=url, concrete_problem=error_msg)
        
        return register_number, title, guideline_class
    
    @handle_website_not_as_excepted_error(logger=logger)
    def _get_pdf_download_url(self, url: str, driver) -> HttpUrl:
        logger.debug("Extracting PDF download URL...")
        wait = WebDriverWait(driver, 10)
        
        download_element = wait.until(
            expected_conditions.presence_of_element_located((By.XPATH, "//*[contains(text(), 'Download')]")),
        )
        pdf_link = download_element.get_attribute('href')
        
        if not pdf_link:
            error_msg = "Download element found but contains no valid href attribute"
            logger.error(error_msg)
            raise WebsiteNotAsExpectedError(url=url, concrete_problem=error_msg)
        
        logger.debug(f"Extracted PDF download link: {pdf_link}")
        return HttpUrl(pdf_link)
    
    @handle_website_not_as_excepted_error(logger=logger)
    def _get_actuality_details(self, url: str, driver) -> Tuple[str, date, date]:
        logger.debug("Extracting actuality details...")
        wait = WebDriverWait(driver, 10)
        
        @handle_website_not_as_excepted_error(logger=logger)
        def find_contained_string(col_label_text):
            logger.debug(f"Searching for content with label: {col_label_text}")
            row_element = wait.until(
                expected_conditions.presence_of_element_located(
                    (
                        By.XPATH,
                        f"//ion-row[ion-col[1][contains(text(), '{col_label_text}')]]",
                    ),
                ),
            )
            contained_information_col = row_element.find_elements(By.XPATH, "./ion-col")[1]
            return contained_information_col.text.strip()
        
        expected_text = find_contained_string("Version:")
        match = re.search(r".*", expected_text)
        if match:
            version = match.group()
            logger.debug(f"Extracted guideline version: {version}")
        else:
            error_msg = "Could not parse version value (from column with 'Version')"
            logger.error(error_msg)
            raise WebsiteNotAsExpectedError(url=url, concrete_problem=error_msg)
        
        expected_text = find_contained_string("Stand:")
        match = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", expected_text)
        if match:
            day, month, year = match.groups()
            date_publication = date(int(year), int(month), int(day))
            logger.debug(f"Extracted publication date: {date_publication.isoformat()} from {expected_text}")
        else:
            error_msg = "Could not parse publication date (from column with 'Stand')"
            logger.error(error_msg)
            raise WebsiteNotAsExpectedError(url=url, concrete_problem=error_msg)
        
        expected_text = find_contained_string("Gültig bis:")
        match = re.search(r"(\d{2})\.(\d{2})\.(\d{4}).*", expected_text)
        if match:
            day, month, year = match.groups()
            date_validity = date(int(year), int(month), int(day))
            logger.debug(f"Extracted validity date: {date_validity.isoformat()} from {expected_text}")
        else:
            error_msg = "Could not parse validity date (from column with 'Gültig bis')"
            logger.error(error_msg)
            raise WebsiteNotAsExpectedError(url=url, concrete_problem=error_msg)
        
        return version, date_publication, date_validity
    
    @handle_website_not_as_excepted_error(logger=logger)
    def _get_contributing_organizations(self, url: str, driver) -> Tuple[List[str], List[str]]:
        logger.debug("Extracting contributing organizations...")
        wait = WebDriverWait(driver, 10)
        
        def find_contained_organization_labels(col_label_text):
            logger.debug(f"Searching for organizations with label: {col_label_text}")
            row_element = wait.until(
                expected_conditions.presence_of_element_located(
                    (By.XPATH, f"//ion-row[ion-col[1][contains(text(), '{col_label_text}')]]"),
                ),
            )
            org_col = row_element.find_elements(By.XPATH, "./ion-col")[1]
            organisation_labels = org_col.find_elements(By.XPATH, ".//ion-label")
            organizations = []
            for label in organisation_labels:
                try:
                    wait.until(
                        lambda d: d.execute_script("return arguments[0].textContent.trim().length > 0;", label),
                    )
                    text = label.get_attribute("textContent").strip()
                    if text:
                        organizations.append(text)
                        logger.debug(f"Found organization: {text}")
                except Exception as e:
                    logger.warning(f"Label unreadable for '{col_label_text}': {e}")
            
            return organizations
        
        leading_organizations, other_contributing_organizations = [], []
        try:
            leading_organizations += find_contained_organization_labels("Federführende Fachgesellschaft")
            logger.debug(f"Found {len(leading_organizations)} leading organizations")
        except Exception as e:
            logger.warning(f"Could not extract leading organizations: {e}")
        try:
            other_contributing_organizations += find_contained_organization_labels("AWMF-Fachgesellschaft")
            logger.debug(f"Found {len(other_contributing_organizations)} AWMF organizations")
        except Exception as e:
            logger.warning(f"Could not extract other contributing AWMF organizations: {e}")
        try:
            external_orgs = find_contained_organization_labels("weiterer Fachgesellschaften")
            other_contributing_organizations += external_orgs
            logger.debug(f"Found {len(external_orgs)} external organizations")
        except Exception as e:
            logger.warning(f"Could not extract other contributing external organizations: {e}")
        return leading_organizations, other_contributing_organizations
    
    @handle_website_not_as_excepted_error(logger=logger)
    def _get_content_details(self, url, driver) -> Tuple[List[str], str]:
        logger.debug("Extracting content details...")
        wait = WebDriverWait(driver, 10)
        
        try:
            logger.debug("Searching for keywords...")
            row_element = wait.until(
                expected_conditions.presence_of_element_located(
                    (By.XPATH, f"//ion-row[ion-col[1][contains(text(), 'Schlüsselwörter')]]"),
                ),
            )
            content_col = row_element.find_elements(By.XPATH, "./ion-col")[1]
            wait.until(
                lambda d: d.execute_script("return arguments[0].textContent.trim().length > 0;", content_col),
            )
            full_text = content_col.get_attribute("textContent").strip()
            
            keywords = [kw.strip() for kw in re.split(r'[,;]', full_text) if kw.strip()]
            logger.debug(f"Found {len(keywords)} keywords")
        except Exception as e:
            logger.warning(f"Could not extract keywords from guideline: {str(e)}")
            keywords = []
        
        try:
            logger.debug("Searching for goal definition...")
            row_element = wait.until(
                expected_conditions.presence_of_element_located(
                    (By.XPATH, f"//ion-row[ion-col[1][contains(text(), 'Zielorientierung der Leitlinie')]]"),
                ),
            )
            content_col = row_element.find_elements(By.XPATH, "./ion-col")[1]
            wait.until(
                lambda d: d.execute_script("return arguments[0].textContent.trim().length > 0;", content_col),
            )
            goal = content_col.get_attribute("textContent").strip()
            logger.debug("Goal definition found")
        except Exception as e:
            logger.warning(f"Could not extract goal definition from guideline: {str(e)}")
            goal = ""
        
        return keywords, goal
    
    @handle_website_not_as_excepted_error(logger=logger)
    def _get_patient_description(self, url, driver) -> Tuple[str, str]:
        logger.debug("Extracting patient description...")
        wait = WebDriverWait(driver, 10)
        
        try:
            logger.debug("Searching for target patient group...")
            row_element = wait.until(
                expected_conditions.presence_of_element_located(
                    (By.XPATH, f"//ion-row[ion-col[1][contains(text(), 'Patientenzielgruppe')]]"),
                ),
            )
            content_col = row_element.find_elements(By.XPATH, "./ion-col")[1]
            wait.until(
                lambda d: d.execute_script("return arguments[0].textContent.trim().length > 0;", content_col),
            )
            target_patient_group = content_col.get_attribute("textContent").strip()
            logger.debug("Target patient group found")
        except Exception as e:
            logger.warning(f"Could not extract target patient group from guideline: {str(e)}")
            target_patient_group = ""
        
        try:
            logger.debug("Searching for care area...")
            row_element = wait.until(
                expected_conditions.presence_of_element_located(
                    (By.XPATH, f"//ion-row[ion-col[1][contains(text(), 'Versorgungsbereich')]]"),
                ),
            )
            content_col = row_element.find_elements(By.XPATH, "./ion-col")[1]
            wait.until(
                lambda d: d.execute_script("return arguments[0].textContent.trim().length > 0;", content_col),
            )
            care_area = content_col.get_attribute("textContent").strip()
            logger.debug("Care area found")
        except Exception as e:
            logger.warning(f"Could not extract care area from guideline: {str(e)}")
            care_area = ""
        
        return target_patient_group, care_area
    
    def transform_extracted_metadata_to_guideline_entry(
            self, extracted_info: AWMFExtractedGuidelineMetadata,
    ) -> GuidelineEntry:
        try:
            logger.info(f"Starting metadata transformation for {extracted_info.awmf_register_number}")
            
            file_name = extracted_info.download_url.path.split('/')[-1].removesuffix('.pdf')
            pattern = r"(\d{3}-\d{3}[^_]*)_(?:(S[^_]+)[_-])?(.*)_(\d{4}\-\d+)(.*)"
            # pattern: full register number; class; title; date; maybe information about invalid or extended validity 
            match = re.search(pattern, file_name)
            if not match:
                logger.error(f"Invalid filename pattern for {file_name}")
                raise ValueError(f"Invalid filename {file_name} (expect pattern: register_class_title_date)")
            
            try:
                logger.debug("Extracting register number and additional information...")
                awmf_register_number_full = match.group(1)
                additional = match.group(5) if match.group(5) else ""
                logger.debug(f"Extracted full register number: {awmf_register_number_full}")
            except IndexError as e:
                logger.error(f"Failed to extract register number from {file_name}")
                raise ValueError(f"Failed to extract data from filename {file_name}: {str(e)}") from e
            
            still_valid = 'abgelaufen' not in additional.lower()
            extended_validity = 'verlaengert' in additional.lower()
            logger.debug(f"Validity status - still valid: {still_valid}, extended: {extended_validity}")
            
            try:
                logger.debug("Creating validity information...")
                validity_range = extracted_info.date_until_valid.year - extracted_info.date_of_guideline_creation.year
                validity_information = GuidelineValidityInformation(
                    version=extracted_info.version or str(extracted_info.date_of_guideline_creation),
                    guideline_creation_date=extracted_info.date_of_guideline_creation,
                    valid=still_valid,
                    extended_validity=extended_validity,
                    validity_range=validity_range,
                )
                logger.debug(f"Created validity information with range: {validity_range} years")
            except Exception as e:
                logger.error("Failed to calculate validity information")
                raise ValueError(f"Failed to calculate validity information: {str(e)}") from e
            
            try:
                logger.debug("Processing organization information...")
                publishing_orgas = [
                    OrganizationEntry(name=orga, is_leading=True)
                    for orga in extracted_info.leading_publishing_organizations
                ]
                publishing_orgas += [
                    OrganizationEntry(name=orga, is_leading=False)
                    for orga in extracted_info.further_organizations
                ]
                logger.debug(f"Processed {len(publishing_orgas)} organizations")
            except Exception as e:
                logger.error("Failed to process organization information")
                raise ValueError(f"Failed to process organization information: {str(e)}") from e
            
            logger.debug("Creating download information...")
            download_information = GuidelineDownloadInformation(
                url=str(extracted_info.download_url),
            )
            
            try:
                logger.debug("Creating final guideline entry...")
                guideline_entry = GuidelineEntry(
                    awmf_register_number=extracted_info.awmf_register_number,
                    awmf_register_number_full=awmf_register_number_full,
                    title=extracted_info.title,
                    awmf_class=extracted_info.awmf_class,
                    keywords=extracted_info.keywords,
                    care_area=extracted_info.care_area,
                    goal=extracted_info.goal,
                    target_patients=extracted_info.target_patients,
                    validity_information=validity_information,
                    publishing_organizations=publishing_orgas,
                    download_information=download_information,
                )
                logger.info(f"Successfully created guideline entry for {extracted_info.awmf_register_number}")
                return guideline_entry
            except Exception as e:
                logger.error(f"Failed to create GuidelineEntry object")
                raise ValueError(f"Failed to create GuidelineEntry: {str(e)}") from e
        
        except Exception as e:
            logger.error(f"Failed to transform extracted metadata to guideline entry: {str(e)}")
            raise e
