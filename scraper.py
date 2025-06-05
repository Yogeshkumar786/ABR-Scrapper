!pip install playwright
!playwright install --with-deps

import asyncio
import json
import requests
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

USERNAME = "NRM.101"
PASSWORD = "Safe@123"
N8N_WEBHOOK_URL = "https://yogeshkumar0787.app.n8n.cloud/webhook/scraper"
structured_data = []  # global

MAX_RETRIES = 3
MIN_ROWS_REQUIRED = 100 # Change this as per your expectation

async def scrape_data():
    print("Launching browser in headless mode...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        data = []

        try:
            await page.goto("https://fmssmart.dsmsoft.com/FMSSmartApp/#/login", timeout=120000)
            await page.fill('input[formcontrolname="userName"]', USERNAME)
            await page.fill('input[formcontrolname="password"]', PASSWORD)
            await page.click('#mysubmit')
            await page.wait_for_selector('text=Dashboard', timeout=15000)
            await page.hover('xpath=/html/body/app-root/div/app-layout/div/main/div/app-dashboard/div[1]/div[1]/div[1]')
            await page.click('xpath=/html/body/app-root/div/app-layout/div/main/div/app-dashboard/div[1]/div[1]/div[1]/div/div[2]/div/button')
            await page.wait_for_selector('.dx-datagrid-rowsview', timeout=250000)
            await page.wait_for_timeout(30000)

            grid_container = await page.query_selector('.dx-scrollable-scroll-content')
            if grid_container:
                await page.evaluate('(el) => { el.scrollLeft = el.scrollWidth; }', grid_container)
                await page.wait_for_timeout(2000)

            header_cells = await page.query_selector_all('.dx-header-row .dx-datagrid-text-content')
            headers = [await cell.inner_text() for cell in header_cells]

            rows_view = await page.query_selector('.dx-datagrid-rowsview .dx-scrollable-container')
            all_rows_text = set()
            unchanged_attempts = 0
            scroll_attempt = 0

            while unchanged_attempts < 5:
                data_rows = await page.query_selector_all('.dx-data-row')
                new_data_found = False

                for row in data_rows:
                    cells = await row.query_selector_all('td')
                    row_data = {}
                    row_text = ''
                    for i, cell in enumerate(cells):
                        text = (await cell.inner_text()).strip()
                        header = headers[i] if i < len(headers) else f"Column {i+1}"
                        row_data[header] = text
                        row_text += text + '|'

                    if row_text not in all_rows_text:
                        all_rows_text.add(row_text)
                        data.append(row_data)
                        new_data_found = True

                if not new_data_found:
                    unchanged_attempts += 1
                else:
                    unchanged_attempts = 0

                await page.evaluate('(el) => el.scrollTop += el.clientHeight', rows_view)
                await page.wait_for_timeout(800)
                scroll_attempt += 1

            print(f"✅ Scraping finished. Rows collected: {len(data)}")
            return data

        except PlaywrightTimeoutError:
            print("❌ Timeout occurred.")
            return []
        except Exception as e:
            print(f"❌ Error during scraping: {e}")
            return []

# Retry loop
for attempt in range(1, MAX_RETRIES + 1):
    print(f"\n🔁 Attempt {attempt} of {MAX_RETRIES}...\n")
    structured_data = asyncio.run(scrape_data())

    if len(structured_data) >= MIN_ROWS_REQUIRED:
        print(f"✅ Got {len(structured_data)} rows. Sending to n8n...")
        try:
            res = requests.post(N8N_WEBHOOK_URL, json={"body": structured_data}, timeout=30)
            print(f"✅ Data sent successfully! Status code: {res.status_code}")
        except Exception as e:
            print(f"❌ Failed to send data to webhook: {e}")
        break
    else:
        print(f"⚠️ Not enough data ({len(structured_data)} rows). Retrying...")

else:
    print(f"❌ All {MAX_RETRIES} attempts failed to get sufficient data.")
