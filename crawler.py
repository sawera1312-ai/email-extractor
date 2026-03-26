import requests
from bs4 import BeautifulSoup
import re
from urllib.parse import urljoin, urlparse, urlencode
import io
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import PyPDF2
import hashlib

# Patterns
EMAIL_PATTERN = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'

# Corresponding author indicators
CORRESPONDING_INDICATORS = [
    'corresponding author', 'correspondence', 'corresponding', 
    'correspondence author', 'corresponding email', 'corresponding address',
    'author for correspondence', 'author to whom correspondence'
]

# Author name patterns
AUTHOR_PATTERNS = [
    r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\s*(?:,|;|\(|\[|$)',
    r'(?:by|author|authors?):\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})',
    r'(?:Prof|Dr|Professor|Associate|Assistant)[\.\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})',
]

# Affiliation patterns
AFFILIATION_PATTERNS = [
    r'([A-Z][a-zA-Z\s&]+(?:University|Institute|College|School|Lab|Department|Center|Centre))',
    r'(?:Univ|Institute|College|School)[\s\.]+(?:of\s+)?([A-Z][a-zA-Z\s]+)',
    r'([A-Z][a-zA-Z\s]+(?:University|Institute))',
    r'\b([A-Z][a-zA-Z\s]+(?:Medical|Engineering|Science|Technology)\s+(?:College|School|University))\b',
]

visited_urls = set()
visited_pdfs = set()
all_authors = {}  # email -> {name, affiliation, source, is_corresponding}
downloaded_pdfs = set()

def download_pdf(pdf_url):
    """Download PDF and extract text"""
    if pdf_url in downloaded_pdfs:
        return None
    downloaded_pdfs.add(pdf_url)
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/pdf,text/html'
        }
        response = requests.get(pdf_url, timeout=15, headers=headers)
        if response.status_code == 200 and 'application/pdf' in response.headers.get('Content-Type', ''):
            pdf_file = io.BytesIO(response.content)
            pdf_reader = PyPDF2.PdfReader(pdf_file)
            
            text = ""
            for page in pdf_reader.pages[:20]:  # First 20 pages (enough for author info)
                try:
                    text += page.extract_text()
                except:
                    continue
            return text
    except Exception as e:
        pass
    return None

def extract_corresponding_author(text):
    """Find corresponding author email and info"""
    text_lower = text.lower()
    
    # Find where corresponding author is mentioned
    for indicator in CORRESPONDING_INDICATORS:
        if indicator in text_lower:
            # Get 500 chars around the indicator
            pos = text_lower.find(indicator)
            start = max(0, pos - 500)
            end = min(len(text), pos + 800)
            context = text[start:end]
            
            # Find email in that context
            emails = re.findall(EMAIL_PATTERN, context)
            if emails:
                return emails[0], context
    
    return None, None

def extract_author_details(text, email):
    """Extract author name and affiliation for a specific email"""
    name = "Unknown"
    affiliation = "Unknown"
    
    # Find email position
    email_pos = text.find(email)
    if email_pos == -1:
        return name, affiliation
    
    # Get 500 chars before and after
    start = max(0, email_pos - 500)
    end = min(len(text), email_pos + 500)
    context = text[start:end]
    
    # Extract name
    for pattern in AUTHOR_PATTERNS:
        matches = re.findall(pattern, context, re.IGNORECASE)
        for match in matches:
            if len(match) > 3 and not any(x in match.lower() for x in ['email', 'address', 'author']):
                name = match.strip()
                break
        if name != "Unknown":
            break
    
    # Clean name
    name = re.sub(r'[,\[\]().:;]', '', name).strip()
    
    # Extract affiliation
    for pattern in AFFILIATION_PATTERNS:
        matches = re.findall(pattern, context, re.IGNORECASE)
        if matches:
            affiliation = matches[0].strip()
            break
    
    # Try from email domain
    if "@" in email and affiliation == "Unknown":
        domain = email.split("@")[1]
        if ".edu" in domain:
            affiliation = domain.replace(".edu", "").replace(".", " ").title()
        elif "ac." in domain:
            parts = domain.split(".")
            if len(parts) > 1:
                affiliation = parts[0].title()
    
    return name, affiliation

def extract_emails_from_text(text, source_url):
    """Extract all emails with author details"""
    emails = set(re.findall(EMAIL_PATTERN, text))
    
    results = []
    for email in emails:
        email_lower = email.lower()
        
        # Skip garbage
        skip_words = ['info', 'admin', 'support', 'noreply', 'webmaster', 'help', 
                      'subscribe', 'unsubscribe', 'marketing', 'sales', 'editor',
                      'journal', 'office', 'system', 'mailer', 'do-not-reply']
        if any(word in email_lower for word in skip_words):
            continue
        
        # Get context
        email_pos = text.find(email)
        start = max(0, email_pos - 800)
        end = min(len(text), email_pos + 800)
        context = text[start:end]
        
        # Check if this is corresponding author
        is_corresponding = False
        context_lower = context.lower()
        for indicator in CORRESPONDING_INDICATORS:
            if indicator in context_lower:
                is_corresponding = True
                break
        
        name, affiliation = extract_author_details(text, email)
        
        # If still no name, try from surrounding text
        if name == "Unknown":
            name_match = re.search(r'([A-Z][a-z]+\s+[A-Z][a-z]+)', context[:200])
            if name_match:
                name = name_match.group(1)
        
        results.append({
            'email': email,
            'name': name,
            'affiliation': affiliation,
            'is_corresponding': is_corresponding,
            'source': source_url
        })
    
    return results

def find_all_links(soup, base_url):
    """Find all links on page"""
    links = set()
    for link in soup.find_all('a', href=True):
        full_url = urljoin(base_url, link['href'])
        links.add(full_url)
    return links

def find_pdf_links(soup, base_url):
    """Find all PDF links"""
    pdfs = set()
    for link in soup.find_all('a', href=True):
        href = link['href'].lower()
        if '.pdf' in href or 'download' in href:
            full_url = urljoin(base_url, link['href'])
            pdfs.add(full_url)
    return pdfs

def crawl_page(url, base_domain, depth, max_depth=3):
    """Deep crawl a single page"""
    if depth > max_depth or url in visited_urls:
        return
    
    visited_urls.add(url)
    
    try:
        print(f"🔍 Crawling: {url} (Depth: {depth})")
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        }
        response = requests.get(url, timeout=15, headers=headers)
        
        if response.status_code != 200:
            return
        
        content_type = response.headers.get('Content-Type', '')
        
        # Handle HTML pages
        if 'text/html' in content_type:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract emails from HTML
            html_emails = extract_emails_from_text(response.text, url)
            for item in html_emails:
                key = item['email']
                if key not in all_authors:
                    all_authors[key] = item
                    status = "✅ CORRESPONDING" if item['is_corresponding'] else "📧"
                    print(f"  {status} {item['email']} - {item['name']} ({item['affiliation']})")
                elif item['is_corresponding'] and not all_authors[key]['is_corresponding']:
                    all_authors[key]['is_corresponding'] = True
                    all_authors[key]['source'] = url
            
            # Find and process PDFs
            pdf_links = find_pdf_links(soup, url)
            for pdf_url in pdf_links:
                if pdf_url not in visited_pdfs:
                    visited_pdfs.add(pdf_url)
                    print(f"  📄 Processing PDF: {pdf_url[:80]}...")
                    pdf_text = download_pdf(pdf_url)
                    if pdf_text:
                        pdf_emails = extract_emails_from_text(pdf_text, pdf_url)
                        for item in pdf_emails:
                            key = item['email']
                            if key not in all_authors:
                                all_authors[key] = item
                                status = "✅ CORRESPONDING" if item['is_corresponding'] else "📧"
                                print(f"  {status} {item['email']} - {item['name']} ({item['affiliation']}) [PDF]")
                            elif item['is_corresponding'] and not all_authors[key]['is_corresponding']:
                                all_authors[key]['is_corresponding'] = True
            
            # Find all links to continue crawling
            if depth < max_depth:
                all_links = find_all_links(soup, url)
                for next_url in all_links:
                    next_domain = urlparse(next_url).netloc
                    # Stay within same domain
                    if next_domain == base_domain:
                        # Don't crawl too many pages - prioritize important ones
                        if len(visited_urls) < 100:  # Max 100 pages
                            crawl_page(next_url, base_domain, depth + 1, max_depth)
        
        # Handle direct PDF URLs
        elif 'application/pdf' in content_type:
            print(f"  📄 Direct PDF: {url[:80]}...")
            pdf_text = download_pdf(url)
            if pdf_text:
                pdf_emails = extract_emails_from_text(pdf_text, url)
                for item in pdf_emails:
                    key = item['email']
                    if key not in all_authors:
                        all_authors[key] = item
                        status = "✅ CORRESPONDING" if item['is_corresponding'] else "📧"
                        print(f"  {status} {item['email']} - {item['name']} ({item['affiliation']})")
        
        time.sleep(0.5)  # Be respectful to servers
        
    except Exception as e:
        print(f"  ❌ Error on {url}: {str(e)[:50]}")
        pass

def run_crawler(start_url, depth):
    """Start the powerful crawler"""
    global visited_urls, visited_pdfs, all_authors
    visited_urls = set()
    visited_pdfs = set()
    all_authors = {}
    
    domain = urlparse(start_url).netloc
    print(f"\n🚀 STARTING POWERFUL DEEP CRAWLER")
    print(f"📡 Target Domain: {domain}")
    print(f"🔧 Max Depth: {depth}")
    print(f"📄 Max Pages: 100\n")
    
    crawl_page(start_url, domain, 1, depth)
    
    print(f"\n✨ Crawling Complete!")
    print(f"📊 Total Pages Crawled: {len(visited_urls)}")
    print(f"📄 PDFs Processed: {len(visited_pdfs)}")
    print(f"📧 Unique Emails Found: {len(all_authors)}")
    
    # Prepare results
    results = []
    for email, data in all_authors.items():
        results.append((
            email,
            data['name'],
            data['affiliation'],
            "Corresponding Author" if data['is_corresponding'] else "Author/Researcher",
            data['source']
        ))
    
    return results