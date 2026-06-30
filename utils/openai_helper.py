import json
import requests
from openai import OpenAI
from utils.config import get_secret

openai_client = OpenAI(api_key=get_secret("OPENAI_API_KEY"))

def get_website_text(url):
    try:
        if not url.startswith("http"):
            url = "https://" + url
        resp = requests.get(url, timeout=8)
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()
        text = soup.get_text(separator=" ", strip=True)
        return text[:4000]
    except:
        return ""

def generate_embedding(text):
    response = openai_client.embeddings.create(
        model="text-embedding-3-small",
        input=text
    )
    return response.data[0].embedding

def build_contact_text(contact):
    parts = [
        contact.get("name", ""),
        contact.get("designation", ""),
        contact.get("company", ""),
        contact.get("email", ""),
        contact.get("contact_type", ""),
        contact.get("category", ""),
        contact.get("subcategory", ""),
        contact.get("company_summary", ""),
        " ".join(contact.get("ai_tags") or []),
        " ".join(contact.get("keywords") or []),
    ]
    return " ".join([p for p in parts if p])

def research_company(website, company_name):
    website_text = get_website_text(website)
    if website_text:
        prompt = f"""You are a business intelligence analyst.
Based on the following website content from {company_name}, generate:
1. A company summary (2-5 paragraphs) covering nature of business, products, services, industries served.
2. A list of AI tags (e.g. HP Partner, Dell Partner, Cisco Partner, Cybersecurity, Cloud Services, Networking, Servers, Data Center)
3. Keywords for search

Website content:
{website_text}

Return ONLY a JSON with keys:
- "company_summary": string
- "ai_tags": list of strings
- "keywords": list of strings
No extra text."""
    else:
        prompt = f"""You are a business intelligence analyst.
Based on the company name "{company_name}" and website "{website}", generate your best guess:
1. A company summary (2-3 paragraphs)
2. Likely AI tags
3. Keywords

Return ONLY a JSON with keys:
- "company_summary": string
- "ai_tags": list of strings
- "keywords": list of strings
No extra text."""

    response = openai_client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}]
    )
    text = response.choices[0].message.content
    text = text.replace("```json", "").replace("```", "").strip()
    return json.loads(text)
