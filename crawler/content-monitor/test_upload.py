import time
from playwright.sync_api import sync_playwright

def test_upload():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, channel="chrome")
        page = browser.new_page()

        # Test 1: /xhs with no token (no image_data)
        page.goto("http://localhost:5050/xhs")
        page.wait_for_load_state("domcontentloaded")
        time.sleep(1)

        # Check if xhs-image element exists
        img_exists = page.query_selector("#xhs-image") is not None
        print(f"#xhs-image exists: {img_exists}")

        # Check img src
        if img_exists:
            src = page.evaluate("document.getElementById('xhs-image').src")
            print(f"img src: {src[:80] if src else 'empty'}")
            hidden = page.evaluate("document.getElementById('xhs-image').classList.contains('hidden')")
            print(f"img has 'hidden' class: {hidden}")

        # Check placeholder
        placeholder = page.query_selector("#xhs-image-placeholder")
        print(f"#xhs-image-placeholder exists: {placeholder is not None}")

        # Try uploading a file
        upload_input = page.query_selector("#image-upload")
        print(f"#image-upload exists: {upload_input is not None}")

        if upload_input:
            # Upload test image
            upload_input.set_input_files("C:/Users/demiliang/test_upload.png")
            time.sleep(1)

            # Check result
            new_src = page.evaluate("document.getElementById('xhs-image').src")
            print(f"After upload - img src starts with: {new_src[:40] if new_src else 'empty'}")
            still_hidden = page.evaluate("document.getElementById('xhs-image').classList.contains('hidden')")
            print(f"After upload - img still hidden: {still_hidden}")

            # Check for JS errors
            console_errors = []
            page.on("console", lambda msg: console_errors.append(f"{msg.type}: {msg.text}") if msg.type == "error" else None)

        # Also check the page HTML for any issues
        html_snippet = page.evaluate("""
            (() => {
                const img = document.getElementById('xhs-image');
                const label = document.querySelector('label');
                const input = document.getElementById('image-upload');
                return JSON.stringify({
                    imgExists: !!img,
                    imgDisplay: img ? window.getComputedStyle(img).display : 'N/A',
                    imgSrc: img ? img.src.slice(0,50) : 'N/A',
                    inputExists: !!input,
                    inputDisplay: input ? window.getComputedStyle(input).display : 'N/A',
                    labelText: label ? label.textContent.trim().slice(0,30) : 'N/A'
                });
            })()
        """)
        print(f"DOM state: {html_snippet}")

        time.sleep(2)
        browser.close()

test_upload()
