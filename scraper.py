import asyncio
import json
import os
import requests
import time

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

USERNAME = os.getenv("FMSS_USERNAME")
PASSWORD = os.getenv("FMSS_PASSWORD")
N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL")

MAX_RETRIES = 10
RETRY_DELAY = 10  # seconds
CHECKPOINT_FILE = "checkpoint.json"


def load_checkpoint():
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE, "r") as f:
            return json.load(f)
    return {
        "logged_in": False,
        "dashboard_loaded": False,
        "hovered": False,
        "button_clicked": False,
        "table_loaded": False,
        "data_extracted": False
    }


def save_checkpoint(progress):
    with open(CHECKPOINT_FILE, "w") as f:
        json.dump(progress, f)


async def extract_data():
    progress = load_checkpoint()
    print("Launching browser...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        try:
            print("Navigating to login page...")
            await page.goto("http://52.186.104.146:8085/FMSSmartApp/#/login", timeout=60000)

            if not progress["logged_in"]:
                print("Filling login form...")
                await page.fill('input[formcontrolname="userName"]', USERNAME)
                await page.fill('input[formcontrolname="password"]', PASSWORD)
                await page.click('#mysubmit')
                progress["logged_in"] = True
                save_checkpoint(progress)

            if not progress["dashboard_loaded"]:
                print("Waiting for dashboard...")
                await page.wait_for_selector('text=Dashboard', timeout=150000)
                progress["dashboard_loaded"] = True
                save_checkpoint(progress)

            if not progress["hovered"]:
                print("Hovering...")
                hover_xpath = '/html/body/app-root/div/app-layout/div/main/div/app-dashboard/div[1]/div[1]/div[1]'
                await page.hover(f'xpath={hover_xpath}')
                progress["hovered"] = True
                save_checkpoint(progress)

            if not progress["button_clicked"]:
                print("Clicking button...")
                button_xpath = '/html/body/app-root/div/app-layout/div/main/div/app-dashboard/div[1]/div[1]/div[1]/div/div[2]/div/button'
                await page.click(f'xpath={button_xpath}')
                progress["button_clicked"] = True
                save_checkpoint(progress)

            if not progress["table_loaded"]:
                print("Waiting for table/grid to load...")
                await page.wait_for_selector('.dx-datagrid-rowsview', timeout=150000)
                await page.wait_for_timeout(3000)
                progress["table_loaded"] = True
                save_checkpoint(progress)

            print("Scrolling horizontally to reveal all columns...")
            grid_container = await page.query_selector('.dx-scrollable-scroll-content')
            if grid_container:
                await page.evaluate('(el) => { el.scrollLeft = el.scrollWidth; }', grid_container)
                await page.wait_for_timeout(5000)

            print("Scrolling vertically to reveal all rows...")
            rows_view = await page.query_selector('.dx-datagrid-rowsview .dx-scrollable-container')
            if rows_view:
                scroll_height = await page.evaluate('(el) => el.scrollHeight', rows_view)
                visible_height = await page.evaluate('(el) => el.clientHeight', rows_view)
                scroll_pos = 0
                while scroll_pos < scroll_height:
                    await page.evaluate(
                        '(args) => { args.el.scrollTop = args.pos; }',
                        {'el': rows_view, 'pos': scroll_pos}
                    )
                    await page.wait_for_timeout(1000)
                    scroll_pos += visible_height

            print("Extracting headers...")
            header_cells = await page.query_selector_all('.dx-header-row .dx-datagrid-text-content')
            headers = [await cell.inner_text() for cell in header_cells]

            print("Extracting row data...")
            data_rows = await page.query_selector_all('.dx-data-row')
            structured_data = []

            for row in data_rows:
                cells = await row.query_selector_all('td')
                row_data = {}
                for i, cell in enumerate(cells):
                    text = await cell.inner_text()
                    header = headers[i] if i < len(headers) else f"Column {i+1}"
                    row_data[header] = text.strip()
                structured_data.append(row_data)

            progress["data_extracted"] = True
            save_checkpoint(progress)

            await browser.close()
            return structured_data

        except PlaywrightTimeoutError:
            print("❌ Timeout: Element not found.")
        except Exception as e:
            print(f"❌ Error: {e}")
        finally:
            await browser.close()

    return []


async def run_until_success():
    retries = 0
    while retries < MAX_RETRIES:
        print(f"\n🔁 Attempt {retries + 1} of {MAX_RETRIES}...")
        data = await extract_data()

        if data:
            print(f"✅ Successfully extracted {len(data)} rows.")
            if N8N_WEBHOOK_URL:
                try:
                    response = requests.post(N8N_WEBHOOK_URL, json=data)
                    print(f"✅ Data sent to n8n. Status code: {response.status_code}")
                except Exception as e:
                    print(f"❌ Failed to send data to n8n: {e}")
            else:
                print("❌ N8N_WEBHOOK_URL is not set.")
            return  # Exit after success

        retries += 1
        print(f"⚠️ No data extracted. Retrying in {RETRY_DELAY} seconds...")
        time.sleep(RETRY_DELAY)

    print("❌ Max retries reached. Exiting without success.")


if __name__ == "__main__":
    asyncio.run(run_until_success())
