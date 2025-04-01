import argparse
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import csv
import re
from datetime import datetime
from difflib import SequenceMatcher

#
# 1. Minimal HTMLPatternCleaner class (no external references):
#
class HTMLPatternCleaner:
    def __init__(self, max_patterns=5):
        """
        This class tracks and removes large repeated text patterns
        (like headers/footers) across multiple pages.
        """
        self.common_patterns = []  # Will store tuples of (-length, pattern)
        self.max_patterns = max_patterns

    def find_longest_common_substring(self, str1, str2):
        """
        Returns the longest common substring between str1 and str2.
        """
        seqMatch = SequenceMatcher(None, str1, str2)
        match = seqMatch.find_longest_match(0, len(str1), 0, len(str2))
        return str1[match.a : match.a + match.size]

    def clean_content(self, content):
        """
        Repeatedly removes the largest repeated substring (>= 250 chars) 
        that matches previously encountered patterns, up to 5 iterations.
        """
        # If we haven't stored any patterns yet, store the entire content
        if not self.common_patterns:
            self.common_patterns.append((-len(content), content))
            return content

        cleaned_content = content
        iterations = 0

        while iterations < 5:
            longest_common = ""
            # Find the longest common substring with any known pattern
            for _, pattern in self.common_patterns:
                common = self.find_longest_common_substring(pattern, cleaned_content)
                if len(common) > len(longest_common):
                    longest_common = common

            # If no sufficiently large pattern found, break
            if len(longest_common) < 250:
                break

            # Remove the longest common pattern from the content
            cleaned_content = cleaned_content.replace(longest_common, "")

            # Also store this newly found pattern, if we have capacity
            if len(self.common_patterns) < self.max_patterns:
                self.common_patterns.append((-len(longest_common), longest_common))

            iterations += 1

        return cleaned_content.strip()

#
# 2. Instantiate the cleaner once (so patterns accumulate across pages):
#
cleaner = HTMLPatternCleaner(max_patterns=5)

#
# 3. Crawl function:
#
def crawl_website(base_url, exclusion_list=None):
    """
    Crawls a website starting from the base_url, ignoring any URL that contains
    a substring from exclusion_list.
    Returns a list of dictionaries with "url", "title", "content".
    """
    if exclusion_list is None:
        exclusion_list = []

    visited = set()             # To keep track of visited URLs
    urls_to_crawl = [base_url]  # Starting point
    results = []                # Store the crawled URLs, titles, and cleaned HTML

    while urls_to_crawl:
        current_url = urls_to_crawl.pop(0)
        # Skip if already visited or contains '#'
        if current_url in visited or "#" in current_url:
            continue

        visited.add(current_url)

        try:
            response = requests.get(current_url, timeout=5)
            response.raise_for_status()  # Raise exception for bad responses
            soup = BeautifulSoup(response.content, 'html.parser')

            # Get the page title
            title = soup.title.string.strip() if soup.title else "No Title"

            # Get raw text from the page, then reduce multiple whitespaces to single spaces
            html_content = soup.get_text()
            html_content = re.sub(r'\s+', ' ', html_content)

            # Clean the extracted text with the HTMLPatternCleaner
            cleaned_html = cleaner.clean_content(html_content)

            print(f"Crawling {current_url}")
            # Append the result (URL, title, cleaned HTML)
            results.append({
                "url": current_url,
                "title": title,
                "content": cleaned_html
            })

            # Enqueue new links
            for link in soup.find_all('a', href=True):
                new_url = urljoin(base_url, link['href'])  # Handle relative URLs

                # Skip new_url if:
                # 1. not starting with base_url
                # 2. already visited
                # 3. '#' in the URL
                # 4. matches any substring in exclusion_list
                if (not new_url.startswith(base_url)
                    or new_url in visited
                    or "#" in new_url
                    or any(exclusion in new_url for exclusion in exclusion_list)
                ):
                    continue

                urls_to_crawl.append(new_url)

        except requests.RequestException as e:
            print(f"Error crawling {current_url}: {e}")
            continue

    return results

#
# 4. Main program to run the crawl and save results to CSV:
#
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Web Crawler")
    parser.add_argument("--base_url", required=True, help="Base URL to start crawling")
    parser.add_argument(
        "--exclusion_list", 
        required=False, 
        help="Comma-separated exclusion substrings", 
        default=".pdf,.jpg,.docx"
    )
    args = parser.parse_args()

    base_url = args.base_url
    exclusion_list = [s.strip() for s in args.exclusion_list.split(",") if s.strip()]

    # Create a timestamp for the filename
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_file = f"crawled_full_html_{timestamp}.csv"

    print(f"Starting crawl for {base_url}")
    results = crawl_website(base_url, exclusion_list=exclusion_list)

    # Write results to a CSV file
    with open(output_file, mode='w', newline='', encoding='utf-8') as file:
        fieldnames = ["url", "title", "content"]
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    print(f"Crawling completed. Results saved to {output_file}")
