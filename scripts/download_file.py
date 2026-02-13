#!/usr/bin/env python3
"""Download files from URLs. Handles PDFs, images, documents, and any binary content.

Usage:
    python3 download_file.py <url> [--output DIR] [--filename NAME]

Flags:
    --output DIR     Directory to save to (default: /tmp/downloads)
    --filename NAME  Override filename (auto-detected from URL/headers if omitted)

Outputs JSON {status, path, filename, size_bytes, content_type}.
Detects file type from Content-Type header and URL. For PDFs, also extracts
text if possible (requires pdfplumber or falls back to basic extraction).
"""

import argparse
import json
import os
import re
import sys
import urllib.parse

import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}

# File types we handle specially
TEXT_EXTRACTABLE = {
    "application/pdf": "pdf",
}


def guess_filename(url: str, resp: requests.Response) -> str:
    """Determine filename from Content-Disposition, URL, or Content-Type."""
    # Check Content-Disposition header
    cd = resp.headers.get("Content-Disposition", "")
    if "filename=" in cd:
        match = re.search(r'filename[*]?=["\']?([^"\';]+)', cd)
        if match:
            return match.group(1).strip()

    # Extract from URL path
    parsed = urllib.parse.urlparse(url)
    path_name = os.path.basename(parsed.path)
    if path_name and "." in path_name:
        return urllib.parse.unquote(path_name)

    # Fall back to content type
    ct = resp.headers.get("Content-Type", "")
    ext_map = {
        "application/pdf": "download.pdf",
        "image/png": "download.png",
        "image/jpeg": "download.jpg",
        "image/gif": "download.gif",
        "image/webp": "download.webp",
        "application/zip": "download.zip",
        "text/html": "download.html",
        "text/plain": "download.txt",
        "application/json": "download.json",
    }
    for mime, name in ext_map.items():
        if mime in ct:
            return name

    return "download.bin"


def extract_pdf_text(filepath: str) -> str:
    """Try to extract text from a PDF. Returns empty string on failure."""
    # Try pdfplumber first
    try:
        import pdfplumber
        text_parts = []
        with pdfplumber.open(filepath) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    text_parts.append(t)
        return "\n\n".join(text_parts)
    except ImportError:
        pass

    # Try PyPDF2
    try:
        from PyPDF2 import PdfReader
        reader = PdfReader(filepath)
        text_parts = []
        for page in reader.pages:
            t = page.extract_text()
            if t:
                text_parts.append(t)
        return "\n\n".join(text_parts)
    except ImportError:
        pass

    return ""


def download(url: str, output_dir: str = "/tmp/downloads", filename: str = None) -> dict:
    os.makedirs(output_dir, exist_ok=True)

    resp = requests.get(url, headers=HEADERS, timeout=30, stream=True, allow_redirects=True)
    resp.raise_for_status()

    if not filename:
        filename = guess_filename(url, resp)

    filepath = os.path.join(output_dir, filename)

    # Avoid overwriting — add suffix if exists
    base, ext = os.path.splitext(filepath)
    counter = 1
    while os.path.exists(filepath):
        filepath = f"{base}_{counter}{ext}"
        counter += 1

    # Stream to disk
    total = 0
    with open(filepath, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)
            total += len(chunk)

    content_type = resp.headers.get("Content-Type", "unknown")
    result = {
        "status": "downloaded",
        "path": filepath,
        "filename": os.path.basename(filepath),
        "size_bytes": total,
        "content_type": content_type,
        "url": url,
    }

    # Extract text from PDFs
    if "pdf" in content_type.lower() or filepath.lower().endswith(".pdf"):
        text = extract_pdf_text(filepath)
        if text:
            result["extracted_text"] = text
            result["extracted_chars"] = len(text)
        else:
            result["extracted_text"] = ""
            result["note"] = "PDF text extraction failed. Install pdfplumber or PyPDF2 for text extraction."

    return result


def main():
    parser = argparse.ArgumentParser(description="Download files from URLs")
    parser.add_argument("url", help="URL to download")
    parser.add_argument("--output", default="/tmp/downloads", help="Output directory (default: /tmp/downloads)")
    parser.add_argument("--filename", default=None, help="Override filename")
    args = parser.parse_args()

    result = download(args.url, args.output, args.filename)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
