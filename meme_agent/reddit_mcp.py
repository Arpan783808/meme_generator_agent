import asyncio
import logging
import sys
import requests
from bs4 import BeautifulSoup
from ddgs import DDGS
from mcp.server.fastmcp import FastMCP

logging.basicConfig(
    level=logging.DEBUG,
    format='[%(levelname)s] reddit_mcp: %(message)s',
    stream=sys.stderr
)
logger = logging.getLogger(__name__)

mcp = FastMCP("RedditMiner")

def search_reddit(topic: str):
    """Searches for the top reddit thread for a topic."""
    query = f"{topic} reddit"
    logger.info(f"Searching DuckDuckGo with query: {query}")
    try:
        with DDGS(timeout=10) as ddgs:
            # Get results and filter for actual Reddit URLs
            results = list(ddgs.text(query, max_results=15, region="us-en"))
            logger.debug(f"DDGS returned {len(results)} results")
            for result in results:
                url = result.get('href', '')
                logger.debug(f"Checking URL: {url}")
                # Filter for actual Reddit thread URLs
                if 'reddit.com/r/' in url and '/comments/' in url:
                    logger.info(f"Found Reddit thread: {url}")
                    return url
            # Fallback: any reddit.com URL
            for result in results:
                url = result.get('href', '')
                if 'reddit.com' in url:
                    logger.info(f"Found Reddit URL (fallback): {url}")
                    return url
        logger.warning("No Reddit URLs found in DDGS results")
    except Exception as e:
        logger.error(f"DDGS search failed: {e}")
    return None

def scrape_thread(url: str):
    """Scrapes the content of a reddit thread using old.reddit.com."""
    # Force old reddit for easier scraping
    url = url.replace("www.reddit.com", "old.reddit.com")
    
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            return f"Error: Failed to fetch page (Status {response.status_code})"
            
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 1. Get the Main Post Title & Content
        title = soup.find('a', class_='title').text.strip() if soup.find('a', class_='title') else "No Title"
        post_content = soup.find('div', class_='usertext-body').text.strip() if soup.find('div', class_='usertext-body') else ""
        
        # 2. Get Top Comments (Consolidation)
        comments = []
        comment_area = soup.find('div', class_='commentarea')
        if comment_area:
            # Get top 5 comments only to save tokens
            entries = comment_area.find_all('div', class_='entry', limit=5)
            for entry in entries:
                text = entry.find('div', class_='usertext-body')
                if text:
                    comments.append(f"- {text.text.strip()}")
        
        # 3. Consolidate Data
        final_report = f"""
        SOURCE: {url}
        TITLE: {title}
        POST: {post_content}
        """
        return final_report

    except Exception as e:
        return f"Scraping failed: {str(e)}"

@mcp.tool()
def mine_reddit_context(topics: list[str]) -> str:
    """
    Takes a list of topics, finds the top Reddit thread for each, and returns consolidated discussions.
    
    Args:
        topics: A list of search topics to mine Reddit for.
    
    Returns:
        Consolidated data from all topics with thread content and comments.
    """
    logger.info(f"=== Mining Reddit for {len(topics)} topics: {topics} ===")
    results = []
    
    for i, topic in enumerate(topics, 1):
        logger.info(f"[{i}/{len(topics)}] Searching: {topic}")
        url = search_reddit(topic)
        
        if not url:
            logger.warning(f"No Reddit threads found for topic: {topic}")
            results.append(f"TOPIC: {topic}\nDATA COLLECTED: No Reddit threads found.\n")
            continue
        
        thread_data = scrape_thread(url)
        results.append(f"TOPIC: {topic}\nDATA COLLECTED:\n{thread_data}\n")
    
    return "\n---\n".join(results)

if __name__ == "__main__":
    # Runs the server on stdio
    logger.info("Launching MCP server...")
    mcp.run()