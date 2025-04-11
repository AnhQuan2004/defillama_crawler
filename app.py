from flask import Flask, jsonify, request
import time
from datetime import datetime
import pandas as pd
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
import logging
import sys
import threading
from threading import Thread

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Global variable to store the crawled data
crawled_data = []

def get_text_safely(element):
    try:
        return element.inner_text().strip()
    except Exception:
        return ""

def get_chain_images(element):
    try:
        images = element.query_selector_all("img")
        return [img.get_attribute("src") for img in images] if images else []
    except Exception:
        return []

def scrape_defillama_data():
    """Function to scrape data from DeFi Llama website and return as a list of dictionaries"""
    url = "https://defillama.com/raises/investors"
    all_data = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--disable-software-rasterizer',
                '--disable-setuid-sandbox'
            ]
        )
        context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        page = context.new_page()
        
        try:
            logger.info("Starting DeFi Llama data scraping...")
            page.goto(url)
            logger.info("Website loaded successfully!")
            time.sleep(5)
            
            # Data to collect
            investors = []
            scroll_step = 300
            current_position = 0
            duplicate_count = 0
            last_data_length = 0
            
            while True:
                try:
                    page.mouse.wheel(0, scroll_step)
                    current_position += scroll_step
                    time.sleep(1.5)
                    
                    # Get element groups
                    elements_200px = page.query_selector_all("div[style*='min-width: 200px']")
                    elements_120px = page.query_selector_all("div[style*='min-width: 120px']")
                    elements_140px = page.query_selector_all("div[style*='min-width: 140px']")
                    elements_160px = page.query_selector_all("div[style*='min-width: 160px']")
                    elements_240px = page.query_selector_all("div[style*='min-width: 240px']")
                    chain_elements = page.query_selector_all("div.flex.items-center.justify-end")
                    
                    logger.info(f"Scroll position: {current_position}px, Found {len(elements_200px)} investors")
                    
                    current_data = {
                        'Investor': [get_text_safely(e) for e in elements_200px],
                        'Deals': [],
                        'Round_Type': [],
                        'Project_Category': [get_text_safely(e) for e in elements_160px],
                        'Project_Name': [get_text_safely(e) for e in elements_240px],
                        'Chains': [get_chain_images(e) for e in chain_elements],
                        'Median_Amount': [get_text_safely(e) for e in elements_140px]
                    }
                    
                    for e in elements_120px:
                        txt = get_text_safely(e)
                        if txt.replace('+', '').isdigit():
                            current_data['Deals'].append(txt)
                        else:
                            current_data['Round_Type'].append(txt)
                    
                    new_investors = 0
                    for i in range(len(current_data['Investor'])):
                        investor = current_data['Investor'][i]
                        deal = current_data['Deals'][i] if i < len(current_data['Deals']) else "N/A"
                        median_amount = current_data['Median_Amount'][i] if i < len(current_data['Median_Amount']) else "N/A"
                        round_type = current_data['Round_Type'][i] if i < len(current_data['Round_Type']) else "N/A"
                        category = current_data['Project_Category'][i] if i < len(current_data['Project_Category']) else "N/A"
                        project_name = current_data['Project_Name'][i] if i < len(current_data['Project_Name']) else "N/A"
                        chains = current_data['Chains'][i] if i < len(current_data['Chains']) else []
                        
                        if investor and investor not in investors:
                            investors.append(investor)
                            new_investors += 1
                            
                            all_data.append({
                                'Investor': investor,
                                'Deals': deal,
                                'Median_Amount': median_amount,
                                'Round_Type': round_type,
                                'Project_Category': category,
                                'Project_Name': project_name,
                                'Chains': ', '.join(chains) if chains else "N/A",
                                'Scrape_Date': datetime.now().strftime('%Y-%m-%d')
                            })
                    
                    logger.info(f"Found {new_investors} new investors in this scroll. Total: {len(investors)}")
                    
                    # Check if we're still getting new data
                    if len(investors) == last_data_length:
                        duplicate_count += 1
                        logger.info(f"No new data found. Duplicate count: {duplicate_count}/5")
                    else:
                        duplicate_count = 0
                        last_data_length = len(investors)
                    
                    # Break if no new data for several scrolls or scrolled too far
                    if duplicate_count >= 5 or current_position > 30000:
                        logger.info(f"Scraping complete. Collected {len(investors)} investors.")
                        break
                        
                except PlaywrightTimeout:
                    logger.warning("Timeout occurred. Trying again...")
                    continue
                except Exception as e:
                    logger.error(f"Unexpected error during scraping: {str(e)}")
                    break
                    
        except Exception as e:
            logger.error(f"An error occurred: {str(e)}")
        finally:
            browser.close()
            
    return all_data

def background_crawler():
    """Function to run the crawler in background"""
    global crawled_data
    while True:
        try:
            logger.info("Starting background crawl...")
            crawled_data = scrape_defillama_data()
            logger.info(f"Background crawl completed. Found {len(crawled_data)} investors.")
            # Wait for 1 hour before next crawl
            time.sleep(3600)
        except Exception as e:
            logger.error(f"Error in background crawler: {str(e)}")
            time.sleep(60)  # Wait 1 minute before retrying

@app.route('/', methods=['GET'])
def home():
    # Set CORS headers
    headers = {
        'Access-Control-Allow-Origin': '*'
    }
    return jsonify({
        "status": "success", 
        "total_investors": len(crawled_data),
        "data": crawled_data
    }), 200, headers

@app.route('/scrape', methods=['GET', 'OPTIONS'])
def scrape():
    # Set CORS headers for the preflight request
    if request.method == 'OPTIONS':
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET',
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Max-Age': '3600'
        }
        return ('', 204, headers)

    # Set CORS headers for the main request
    headers = {
        'Access-Control-Allow-Origin': '*'
    }
    
    try:
        # Return the current data
        return jsonify({"status": "success", "data": crawled_data}), 200, headers
    except Exception as e:
        logger.error(f"Error in /scrape endpoint: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500, headers

if __name__ == '__main__':
    # Start the crawler in a background thread
    crawler_thread = Thread(target=background_crawler, daemon=True)
    crawler_thread.start()
    
    # Start the Flask app
    app.run(debug=True, host='0.0.0.0', port=8080, use_reloader=False)