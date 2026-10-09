from playwright.sync_api import sync_playwright
out = "/home/claude/library/docs/img/"
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1280, "height": 860}, device_scale_factor=1.5)
    pg.goto("http://127.0.0.1:8080/login")
    pg.fill("input[name=login]", "demo"); pg.fill("input[name=password]", "demo")
    pg.click("button"); pg.wait_for_url("**/loans")
    pg.goto("http://127.0.0.1:8080/loans?status=overdue")
    pg.screenshot(path=out + "screen_loans.png", full_page=False)
    pg.goto("http://127.0.0.1:8080/summary")
    pg.screenshot(path=out + "screen_summary.png", full_page=True)
    pg.goto("http://127.0.0.1:8080/loans/50000")
    pg.screenshot(path=out + "screen_loan.png", full_page=True)
    pg.goto("http://127.0.0.1:8080/loans/new?reader_id=1&copy_id=1")
    pg.click("button:has-text('Выдать')")
    pg.screenshot(path=out + "screen_reject.png")
    b.close()
