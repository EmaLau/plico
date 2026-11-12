"""Prova dell'interfaccia in un browser headless: ogni strumento dalla pagina, fino al file pronto.

Usa Chromium di Playwright (playwright install chromium). Per usare Chrome gia' installato: PW_CHANNEL=chrome.
"""
import os
import re

import pytest

from conftest import make_pdf, make_png

playwright = pytest.importorskip("playwright.sync_api")


@pytest.fixture(scope="module")
def files(tmp_path_factory):
    d = tmp_path_factory.mktemp("ui")
    (d / "a.pdf").write_bytes(make_pdf(4))
    (d / "b.pdf").write_bytes(make_pdf(2))
    (d / "x.png").write_bytes(make_png())
    (d / "y.png").write_bytes(make_png(300, 400))
    from test_features import form_pdf
    (d / "modulo.pdf").write_bytes(form_pdf())
    return d


@pytest.fixture(scope="module")
def browser():
    with playwright.sync_playwright() as p:
        b = p.chromium.launch(channel=os.environ.get("PW_CHANNEL") or None)
        yield b
        b.close()


@pytest.fixture
def page(browser, live_server):
    ctx = browser.new_context(locale="it-IT")
    pg = ctx.new_page()
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.on("console", lambda m: m.type == "error" and errors.append(m.text))
    pg.goto(live_server + "/")
    yield pg
    ctx.close()
    assert not errors, f"errori JavaScript: {errors}"


def run_tool(page, tool, names, files, prepare=None):
    page.goto(page.url.split("#")[0] + "#" + tool)
    with page.expect_file_chooser() as fc:
        page.click("#dz")
    fc.value.set_files([str(files / n) for n in names])
    if prepare:
        prepare(page)
    page.wait_for_selector("#run:not([disabled])", timeout=15000)
    page.click("#run")
    page.wait_for_selector("#done:not(.hidden)", timeout=60000)
    assert page.locator("#err").text_content() == ""
    return page.locator("#doneTxt").text_content()


def first_thumb(page):
    page.wait_for_selector(".pg")
    page.click(".pg >> nth=0")


TOOLS = [
    ("unisci", ["a.pdf", "b.pdf", "x.png"], None, r"\.pdf"),
    ("dividi", ["a.pdf"], lambda p: p.fill("#ranges", "1-2, 3-"), r"\.zip"),
    ("estrai", ["a.pdf"], first_thumb, r"\.pdf"),
    ("riordina", ["a.pdf"], lambda p: (p.wait_for_selector(".pg"), p.click("[data-b=revert]")), r"\.pdf"),
    ("ruota", ["a.pdf"], lambda p: (p.wait_for_selector(".pg"), p.click("[data-b=all-r]")), r"\.pdf"),
    ("elimina", ["a.pdf"], first_thumb, r"\.pdf"),
    ("comprimi", ["a.pdf"], None, r"KB|B|leggero|ottimizzato"),
    ("img2pdf", ["x.png", "y.png"], None, r"\.pdf"),
    ("pdf2img", ["a.pdf"], lambda p: p.wait_for_selector("#editor >> text=pagine"), r"\.zip"),
    ("proteggi", ["a.pdf"], lambda p: (p.fill("#pw", "segreta"), p.fill("#pw2", "segreta")), r"protetto\.pdf"),
    ("timbra", ["a.pdf"], lambda p: p.fill("#wm", "BOZZA"), r"timbrato\.pdf"),
]


@pytest.mark.parametrize("tool,names,prepare,expect", TOOLS, ids=[t[0] for t in TOOLS])
def test_tool(page, files, tool, names, prepare, expect):
    assert re.search(expect, run_tool(page, tool, names, files, prepare))


def test_home_lists_all_tools(page):
    assert page.locator("a.tool").count() >= 23  # 27 strumenti, meno quelli facoltativi non attivi


@pytest.mark.parametrize("locale,title,button", [("en-US", "All the PDF tools, at home", "Merge PDF"),
                                                 ("it-IT", "Tutti gli strumenti PDF, in casa", "Unisci PDF")])
def test_language_from_browser(browser, live_server, locale, title, button):
    ctx = browser.new_context(locale=locale)
    pg = ctx.new_page()
    errors = []
    pg.on("console", lambda m: m.type == "error" and errors.append(m.text))
    pg.goto(live_server + "/")
    assert pg.locator("h1").first.text_content() == title
    pg.goto(live_server + "/#unisci")
    pg.wait_for_selector("#tTitle")
    assert pg.locator("#run").text_content() == button
    ctx.close()
    assert not errors


def test_language_switch_and_english_tool(browser, live_server, files):
    ctx = browser.new_context(locale="it-IT")
    pg = ctx.new_page()
    errors = []
    pg.on("console", lambda m: m.type == "error" and errors.append(m.text))
    pg.goto(live_server + "/")
    pg.click("[data-lang-switch] [data-l=en]")
    pg.wait_for_selector("text=All the PDF tools, at home")
    # un errore del server arriva in inglese
    pg.goto(live_server + "/#dividi")
    with pg.expect_file_chooser() as fc:
        pg.click("#dz")
    fc.value.set_files(str(files / "a.pdf"))
    pg.fill("#ranges", "99")
    pg.click("#run")
    pg.wait_for_selector("#err:has-text('outside the document')")
    ctx.close()
    assert not [e for e in errors if "status of 400" not in e]  # il 400 e' quello voluto


def test_admin_page_login(page, live_server):
    from conftest import ADMIN_PASSWORD
    page.goto(live_server + "/admin")
    page.fill("#pw", ADMIN_PASSWORD)
    page.click("#loginForm button")
    page.wait_for_selector("#app:not(.hidden)")
    page.fill("#name", "prova ui")
    page.click("#allPerms")
    page.click("#createForm button[type=submit]")
    page.wait_for_selector("#created:not(.hidden)")
    assert page.locator("#newKey").text_content().startswith("plico_")
    assert page.locator("#keys .key", has_text="prova ui").count() == 1


def drag(page, sel, a, b, steps=8):
    box = page.locator(sel).bounding_box()
    page.mouse.move(box["x"] + box["width"] * a[0], box["y"] + box["height"] * a[1])
    page.mouse.down()
    page.mouse.move(box["x"] + box["width"] * b[0], box["y"] + box["height"] * b[1], steps=steps)
    page.mouse.up()


def draw_signature(p):
    p.wait_for_selector("#ov")
    drag(p, "#pad", (0.1, 0.6), (0.6, 0.3))
    drag(p, "#ov", (0.5, 0.7), (0.9, 0.8))


def annotate(p):
    p.wait_for_selector("#ov")
    drag(p, "#ov", (0.1, 0.1), (0.6, 0.15))
    p.click("[data-mode=arrow]")
    drag(p, "#ov", (0.2, 0.5), (0.7, 0.6))
    p.click("[data-mode=text]")
    p.fill("#atext", "Ciao")
    drag(p, "#ov", (0.2, 0.3), (0.6, 0.35))


def redact(p):
    p.wait_for_selector("#ov")
    drag(p, "#ov", (0.05, 0.05), (0.95, 0.2))
    p.fill("#terms", "Pagina 2")


NEW_TOOLS = [
    ("scanner", ["x.png", "y.png"], None, r"\.pdf"),
    ("firma", ["a.pdf"], draw_signature, r"\.pdf"),
    ("annota", ["a.pdf"], annotate, r"\.pdf"),
    ("oscura", ["a.pdf"], redact, r"\.pdf"),
    ("moduli", ["modulo.pdf"], lambda p: (p.wait_for_selector("[data-f]"), p.fill("input[type=text][data-f]", "Mario")), r"\.pdf"),
    ("metadati", ["a.pdf"], lambda p: (p.wait_for_selector("#mtitle"), p.fill("#mtitle", "Relazione")), r"\.pdf"),
    ("confronta", ["a.pdf", "b.pdf"], None, r"\.pdf"),
    ("pagine", ["a.pdf"], None, r"\.pdf"),
    ("nup", ["a.pdf"], None, r"\.pdf"),
    ("estraiimg", ["a.pdf"], lambda p: p.click("[data-seg=ekind] [data-v=text]"), r"\.txt"),
    ("ripara", ["a.pdf"], None, r"\.pdf"),
    ("catena", ["a.pdf", "b.pdf"], lambda p: p.check("#c_num"), r"\.zip"),
]


@pytest.mark.parametrize("tool,names,prepare,expect", NEW_TOOLS, ids=[t[0] for t in NEW_TOOLS])
def test_new_tool(page, files, tool, names, prepare, expect):
    assert re.search(expect, run_tool(page, tool, names, files, prepare))


def test_stamp_header_and_logo(page, files):
    def prep(p):
        p.fill("#hdr", "Relazione {date}")
        p.uncheck("#num")
        p.set_input_files("#logo", str(files / "x.png"))
    assert "timbrato" in run_tool(page, "timbra", ["a.pdf"], files, prep)


def test_admin_chains(page, live_server):
    from conftest import ADMIN_PASSWORD
    page.goto(live_server + "/admin")
    page.fill("#pw", ADMIN_PASSWORD)
    page.click("#loginForm button")
    page.wait_for_selector("#chains .key")
    n = page.locator("#chains .key").count()
    page.fill("#cname", "Prova UI")
    page.check("[data-op=compress]")
    page.check("[data-op=stamp]")
    page.click("#chainForm button[type=submit]")
    page.locator("#chains .key", has_text="Prova UI").wait_for()
    assert page.locator("#chains .key").count() == n + 1
    assert "Comprimi → Numeri di pagina" in page.locator("#chains").text_content()
