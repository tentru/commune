
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import os
import hashlib
from typing import Dict, List, Set
import logging
import commune as c
class Web:
    endpoints = ["search", "crawl"]
    def __init__(self, url: str='https://github.com/ai16z/eliza/fork', max_pages: int = 10):
        """
        Initialize the WebCrawler with a base URL and maximum pages to crawl
        """
        self.url = url
        self.max_pages = max_pages
        self.visited_urls: Set[str] = set()
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        self.setup_logging()

    def setup_logging(self):
        """Configure logging for the crawler"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)

    def is_valid_url(self, url: str) -> bool:
        """Check if URL is valid and belongs to the same domain"""
        try:
            parsed_base = urlparse(self.url)
            parsed_url = urlparse(url)
            return parsed_base.netloc == parsed_url.netloc
        except Exception:
            return False
        


    # def search(self, query:str='twitter', source:str='desktop') -> str:

    engine2url = { 
            'brave': 'https://search.brave.com/search?q={query}',
            'google': 'https://www.google.com/search?q={query}',
            'bing': 'https://www.bing.com/search?q={query}',
            'yahoo': 'https://search.yahoo.com/search?p={query}',
            'duckduckgo': 'https://duckduckgo.com/?q{query}'
        }
    
    engines = list(engine2url.keys())

    def search(self, query:str='twitter', engine="brave", source:str='desktop') -> str:
        '''
        Searches the query on the source
        '''

        if engine in self.engine2url:
            url = self.engine2url[engine].format(query=query)
        elif engine == 'all':
            results = {}
            future2engine = {}
            for engine in self.engine2url:
                url = self.engine2url[engine].format(query=query)
                future = c.submit(self.page_content, [url], timeout=10)
                future2engine[future] = engine

            for f in c.as_completed(future2engine):
                engine = future2engine[f]
                url = f.result()
                print(f'{engine} --> {url}')
                results[engine] = url
            return results
        else:
            raise ValueError(f'Engine {engine} not supported')
        
        return self.page_content(url)

    def page_content(self, url: str="https://search.brave.com/search?q=twitter") -> Dict:
        """
        Fetch and extract content from a webpage
        Returns a dictionary containing text content and image URLs
        """
        url = url or self.url
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract text content
            text_content = []
            for text in soup.stripped_strings:
                if len(text.strip()) > 0:
                    text_content.append(text.strip())

            # Extract images
            images = []
            for img in soup.find_all('img'):
                src = img.get('src')
                if src:
                    absolute_url = urljoin(url, src)
                    alt_text = img.get('alt', '')
                    images.append({
                        'url': absolute_url,
                        'alt_text': alt_text
                    })

            # Extract links for further crawling
            links = []
            for link in soup.find_all('a'):
                href = link.get('href')
                if href:
                    absolute_url = urljoin(url, href)
                    if self.is_valid_url(absolute_url):
                        links.append(absolute_url)

            return {
                'url': url,
                'text_content': text_content,
                'images': images,
                'links': links
            }

        except Exception as e:
            print(f"Error crawling {url}: {str(e)}")
            return None

    def save_content(self, content: Dict, output_dir: str = 'crawled_data'):
        """Save the crawled content to files"""
        if not content:
            return

        # Create hash of URL for unique filename
        url_hash = hashlib.md5(content['url'].encode()).hexdigest()[:10]
        
        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)
        
        # Save text content
        text_file = os.path.join(output_dir, f'{url_hash}_content.txt')
        with open(text_file, 'w', encoding='utf-8') as f:
            f.write(f"URL: {content['url']}\n\n")
            f.write("TEXT CONTENT:\n")
            for text in content['text_content']:
                f.write(f"{text}\n")
            
            f.write("\nIMAGES:\n")
            for img in content['images']:
                f.write(f"URL: {img['url']}\nAlt Text: {img['alt_text']}\n\n")

    def crawl(self, save_output: bool = True, output_dir: str = 'crawled_data'):
        """
        Main crawling method that processes pages up to max_pages
        """
        pages_to_visit = [self.url]
        crawled_content = []

        while pages_to_visit and len(self.visited_urls) < self.max_pages:
            current_url = pages_to_visit.pop(0)
            
            if current_url in self.visited_urls:
                continue

            self.logger.info(f"Crawling: {current_url}")
            content = self.page_content(current_url)
            
            if content:
                self.visited_urls.add(current_url)
                crawled_content.append(content)
                
                if save_output:
                    self.save_content(content, output_dir)
                
                # Add new links to visit
                pages_to_visit.extend([
                    url for url in content['links']
                    if url not in self.visited_urls and url not in pages_to_visit
                ])

        return crawled_content

# Example usage
if __name__ == "__main__":
    crawler = WebCrawler("https://example.com", max_pages=5)
    results = crawler.crawl(save_output=True)
    print(f"Crawled {len(results)} pages successfully!")
