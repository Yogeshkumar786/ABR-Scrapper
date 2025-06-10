import asyncio
import json
import requests
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

USERNAME = "NRM.101"
PASSWORD = "Safe@123"
N8N_WEBHOOK_URL = "https://yogeshkumar0787.app.n8n.cloud/webhook/abcd"
structured_data = []

async def run_script():
    global structured_data
    print("Launching browser in headless mode...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        try:
            print("Navigating to login page...")
            await page.goto("https://fmssmart.dsmsoft.com/FMSSmartApp/#/login", timeout=120000)

            print("Filling login form...")
            await page.fill('input[formcontrolname="userName"]', USERNAME)
            await page.fill('input[formcontrolname="password"]', PASSWORD)
            await page.click('#mysubmit')

            print("Waiting for dashboard...")
            await page.wait_for_selector('text=Dashboard', timeout=15000)

            print("Hovering and clicking...")
            await page.hover('xpath=/html/body/app-root/div/app-layout/div/main/div/app-dashboard/div[1]/div[1]/div[1]')
            await page.click('xpath=/html/body/app-root/div/app-layout/div/main/div/app-dashboard/div[1]/div[1]/div[1]/div/div[2]/div/button')

            print("Waiting for table/grid to load...")
            await page.wait_for_selector('.dx-datagrid-rowsview', timeout=250000)
            await page.wait_for_timeout(30000)

            print("Scrolling horizontally...")
            grid_container = await page.query_selector('.dx-scrollable-scroll-content')
            if grid_container:
                await page.evaluate('(el) => { el.scrollLeft = el.scrollWidth; }', grid_container)
                await page.wait_for_timeout(2000)

            print("Extracting headers...")
            header_cells = await page.query_selector_all('.dx-header-row .dx-datagrid-text-content')
            headers = [await cell.inner_text() for cell in header_cells]

            print("Extracting data rows...")
            rows_view = await page.query_selector('.dx-datagrid-rowsview .dx-scrollable-container')
            all_rows_text = set()
            scroll_attempt = 0
            unchanged_attempts = 0

            while unchanged_attempts < 5:
                print(f"🔁 Scroll attempt #{scroll_attempt + 1}")
                new_rows_found = False

                data_rows = await page.query_selector_all('.dx-data-row')
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
                        structured_data.append(row_data)
                        new_rows_found = True

                if not new_rows_found:
                    unchanged_attempts += 1
                else:
                    unchanged_attempts = 0

                await page.evaluate('(el) => el.scrollTop += el.clientHeight', rows_view)
                await page.wait_for_timeout(800)
                scroll_attempt += 1

            print(f"✅ Finished. Total rows: {len(structured_data)}")

        except PlaywrightTimeoutError:
            print("❌ Timeout occurred.")
        except Exception as e:
            print(f"❌ Error: {e}")
        finally:
            await browser.close()


def send_with_retry(data, retries=3, delay=10):
    for attempt in range(retries):
        try:
            print(f"📤 Attempt {attempt + 1}: Sending {len(data)} rows...")
            response = requests.post(N8N_WEBHOOK_URL, json=data, timeout=90)
            print(f"✅ Sent! Status code: {response.status_code}")
            return
        except Exception as e:
            print(f"❌ Attempt {attempt + 1} failed: {e}")
            if attempt < retries - 1:
                time.sleep(delay)
    print("❌ All attempts failed. Data not sent.")



if __name__ == "__main__":
    asyncio.run(run_script())
    send_with_retry(structured_data)
