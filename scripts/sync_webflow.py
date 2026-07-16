# Place this file at: scripts/sync_webflow.py
#
# Reads the HTML_FILE named in its environment, extracts the case study's
# title, and creates (or updates, if a Webflow item for the same page
# already exists) a live Webflow CMS Collection Item with just the name
# and html-url. Invoked once per newly-added .html file by
# .github/workflows/webflow-sync.yml.
import os
import json
import re
import requests
from bs4 import BeautifulSoup

WEBFLOW_TOKEN = os.environ.get("WEBFLOW_TOKEN")
COLLECTION_ID = os.environ.get("COLLECTION_ID")
GITHUB_PAGES = os.environ.get("GITHUB_PAGES")
HTML_FILE = os.environ.get("HTML_FILE")

if not HTML_FILE:
    print("⚠️ No HTML_FILE environment variable detected. Skipping sync.")
    exit(0)

HEADERS = {
    "Authorization": f"Bearer {WEBFLOW_TOKEN}",
    "Content-Type": "application/json"
}

# Read HTML
with open(HTML_FILE, "r", encoding="utf-8") as f:
    html = f.read()

soup = BeautifulSoup(html, "lxml")

# Some pages (the "bundler" export format) don't hold their real markup as
# live DOM — it's stashed as a JSON-encoded string inside a
# <script type="__bundler/template"> tag and injected client-side. If that
# tag is present, parse the decoded template instead so id lookups below
# can actually find the h1 element.
bundler_template = soup.find("script", attrs={"type": "__bundler/template"})
if bundler_template and bundler_template.string:
    soup = BeautifulSoup(json.loads(bundler_template.string), "lxml")

page_url = f"{GITHUB_PAGES}/{os.path.basename(HTML_FILE)}"

# Filename-derived slug — used only as a local fallback title source below.
# Not sent to Webflow: slug is left for Webflow to assign/manage itself.
slug = os.path.splitext(os.path.basename(HTML_FILE))[0]


def element_text(el):
    # separator=" " keeps text on either side of nested tags (e.g. <span>,
    # <br>, <em>) from getting jammed together; collapse the resulting
    # run of whitespace down to single spaces, then drop the space the
    # separator introduces before trailing punctuation like "growth ."
    text = " ".join(el.get_text(separator=" ", strip=True).split())
    return re.sub(r"\s+([.,!?;:])", r"\1", text)


# Title — the case study's <h1 id="case-study-name">, falling back to any
# <h1>, then <title>, then the filename-derived slug
title = ""
name_el = soup.find(id="case-study-name")
if name_el:
    title = element_text(name_el)
if not title:
    h1 = soup.find("h1")
    if h1:
        title = element_text(h1)
if not title and soup.title:
    title = soup.title.text.strip()
if not title:
    title = slug.replace("-", " ").title()

print("Parsed metadata:")
print(f"  Title: {title}")
print(f"  URL:   {page_url}")

# Fetch Webflow Items to check for an existing item for this case study.
# Matched by "html-url" (a stable id for the case study derived from the
# filename), not by "slug" — we don't push slug to Webflow — and not by
# "name"/title either, since titles can be edited later and shouldn't
# cause a duplicate item to be created.
url = f"https://api.webflow.com/v2/collections/{COLLECTION_ID}/items"
response = requests.get(url, headers=HEADERS)
response.raise_for_status()
items = response.json().get("items", [])

existing = None
for item in items:
    field_data = item.get("fieldData", {})
    if field_data.get("html-url") == page_url:
        existing = item
        break

# Payload Structure — slug is intentionally omitted; Webflow will assign
# one itself (derived from "name") when the item is created.
payload = {
    "isArchived": False,
    "isDraft": False,
    "fieldData": {
        "name": title,
        "html-url": page_url
    }
}

# Update or Create
try:
    if existing:
        item_id = existing["id"]
        print(f"\n🔄 Updating existing item: {item_id}")
        url = f"https://api.webflow.com/v2/collections/{COLLECTION_ID}/items/{item_id}/live"
        response = requests.patch(
            url,
            headers=HEADERS,
            data=json.dumps(payload)
        )
    else:
        print("\n✨ Creating new CMS item")
        url = f"https://api.webflow.com/v2/collections/{COLLECTION_ID}/items/live"
        response = requests.post(
            url,
            headers=HEADERS,
            data=json.dumps(payload)
        )
    response.raise_for_status()
    print("=" * 60)
    print("✅ Webflow Sync Successful")
    print("=" * 60)
except requests.exceptions.HTTPError as err:
    print("=" * 60)
    print("❌ Webflow API Error Detailed Output:")
    print("=" * 60)
    print(f"Status Code: {response.status_code}")
    try:
        print(json.dumps(response.json(), indent=2))
    except Exception:
        print(response.text)
    raise err
