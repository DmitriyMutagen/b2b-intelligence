"""
Web Crawler — extract contact info (emails, phones, socials) from company websites.
Uses requests + BeautifulSoup. Follows links up to depth 3.
"""
import re
import time
import requests
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from dataclasses import dataclass, field


@dataclass
class CrawlResult:
    """Structured result from crawling a single website."""
    url: str
    emails: list = field(default_factory=list)
    phones: list = field(default_factory=list)
    social_links: dict = field(default_factory=dict)  # {vk: url, tg: url, ig: url}
    inn: str = None
    address: str = None
    description: str = None
    contacts_page_text: str = None

    def to_dict(self):
        return {
            "url": self.url,
            "emails": list(set(self.emails)),
            "phones": list(set(self.phones)),
            "social_links": self.social_links,
            "inn": self.inn,
            "address": self.address,
            "description": self.description,
        }


# Regex patterns
EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
PHONE_RE = re.compile(r'(?:\+7|8)[\s\-\(]?\d{3}[\s\-\)]?\s?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}')
INN_RE = re.compile(r'\bИНН\s*:?\s*(\d{10,12})\b')

SOCIAL_PATTERNS = {
    'vk': re.compile(r'https?://vk\.com/[a-zA-Z0-9_.-]+'),
    'telegram': re.compile(r'https?://t\.me/[a-zA-Z0-9_]+'),
    'instagram': re.compile(r'https?://(?:www\.)?instagram\.com/[a-zA-Z0-9_.]+'),
    'youtube': re.compile(r'https?://(?:www\.)?youtube\.com/(?:@|channel/|c/)[a-zA-Z0-9_-]+'),
    'whatsapp': re.compile(r'https?://(?:wa\.me|api\.whatsapp\.com)/\+?\d+'),
}

# Pages to prioritize for contacts
CONTACT_KEYWORDS = ['контакт', 'contact', 'о нас', 'about', 'связ', 'обратная']

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36'
}


def crawl_website(url: str, max_depth: int = 2, max_pages: int = 15) -> CrawlResult:
    """Crawl a website and extract contact information."""
    if not url.startswith('http'):
        url = f'https://{url}'

    result = CrawlResult(url=url)
    visited = set()
    domain = urlparse(url).netloc
    to_visit = [(url, 0)]  # (url, depth)

    while to_visit and len(visited) < max_pages:
        current_url, depth = to_visit.pop(0)

        if current_url in visited:
            continue
        visited.add(current_url)

        try:
            resp = requests.get(current_url, headers=HEADERS, timeout=10, allow_redirects=True)
            if resp.status_code != 200:
                continue
            if 'text/html' not in resp.headers.get('content-type', ''):
                continue

            html = resp.text
            soup = BeautifulSoup(html, 'html.parser')

            # Extract text
            text = soup.get_text(separator=' ', strip=True)

            # Emails
            result.emails.extend(EMAIL_RE.findall(text))
            # Also check mailto: links
            for a in soup.find_all('a', href=True):
                href = a['href']
                if href.startswith('mailto:'):
                    email = href.replace('mailto:', '').split('?')[0]
                    result.emails.append(email)

            # Phones
            result.phones.extend(PHONE_RE.findall(text))
            # Also check tel: links
            for a in soup.find_all('a', href=True):
                href = a['href']
                if href.startswith('tel:'):
                    phone = href.replace('tel:', '').strip()
                    result.phones.append(phone)

            # Social links
            for platform, pattern in SOCIAL_PATTERNS.items():
                matches = pattern.findall(html)
                if matches:
                    result.social_links[platform] = matches[0]

            # INN
            inn_match = INN_RE.search(text)
            if inn_match and not result.inn:
                result.inn = inn_match.group(1)

            # Description (meta description)
            meta_desc = soup.find('meta', attrs={'name': 'description'})
            if meta_desc and not result.description:
                result.description = meta_desc.get('content', '')

            # Save contacts page text
            page_lower = current_url.lower()
            if any(kw in page_lower for kw in CONTACT_KEYWORDS):
                result.contacts_page_text = text[:2000]

            # Find more links to crawl (only same domain)
            if depth < max_depth:
                for a in soup.find_all('a', href=True):
                    link = urljoin(current_url, a['href'])
                    link_parsed = urlparse(link)

                    # Same domain only
                    if link_parsed.netloc != domain:
                        continue
                    # Skip files and anchors
                    if any(link.endswith(ext) for ext in ['.pdf', '.jpg', '.png', '.zip', '.doc']):
                        continue

                    clean_link = f"{link_parsed.scheme}://{link_parsed.netloc}{link_parsed.path}"

                    # Prioritize contact pages
                    priority = any(kw in clean_link.lower() for kw in CONTACT_KEYWORDS)
                    if priority:
                        to_visit.insert(0, (clean_link, depth + 1))
                    else:
                        to_visit.append((clean_link, depth + 1))

            time.sleep(0.3)  # Polite crawling

        except Exception as e:
            print(f"  Crawl error {current_url}: {e}")
            continue

    # Deduplicate
    result.emails = list(set(e.lower() for e in result.emails if not e.endswith('.png') and not e.endswith('.jpg')))
    result.phones = list(set(result.phones))

    return result


# ─── Quick test ───
if __name__ == "__main__":
    import json
    test_url = "https://bio-innovations-stm.ru/"
    print(f"Crawling: {test_url}")
    res = crawl_website(test_url, max_depth=2, max_pages=10)
    print(json.dumps(res.to_dict(), indent=2, ensure_ascii=False))
