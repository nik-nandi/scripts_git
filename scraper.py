from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from rich.console import Console
from rich.table import Table
from rich.live import Live
import keyboard

import time
import json
import datetime
import os
from bs4 import BeautifulSoup
import requests

scripts = {
    'hover_script': """
        window._lastSelectedInfo = null;
        window._previousElement = null;
        
        document.addEventListener('mousedown', function(e) {
            if (window._previousElement) {
                window._previousElement.style.outline = '';
            }
            let element = e.target;
            window._previousElement = element;
            window._lastSelectedInfo = {
                'tag': element.tagName.toLowerCase(),
                'class': element.className,
                'id': element.id,
                'attributes': Object.entries(element.attributes)
                    .map(attr => `${attr[1].name}="${attr[1].value}"`).join(' '),
                'text': element.textContent.trim().substring(0, 100),
                'html': element.innerHTML.substring(0, 100),
                'dimensions': {
                    'width': window.getComputedStyle(element).width,
                    'height': window.getComputedStyle(element).height,
                    'position': window.getComputedStyle(element).position
                },
                'children': element.children.length,
                'parent': element.parentElement ? element.parentElement.tagName.toLowerCase() : 'none'
            };
            element.style.outline = '2px solid red';
            e.preventDefault();
        });
    """,
    'clear_script': """
        if (window._previousElement) {
            window._previousElement.style.outline = '';
            window._previousElement = null;
            window._lastSelectedInfo = null;
        }
    """,
    'scrape_script': """
        def scrape_element(url):
            import requests
            from bs4 import BeautifulSoup
            
            headers = {{'User-Agent': 'Mozilla/5.0'}}
            response = requests.get(url, headers=headers)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            element = soup.select_one("{selector}")
            if not element:
                return None
                
            return {{
                'tag': element.name,
                'text': element.text.strip(),
                'html': str(element),
                'attributes': element.attrs
            }}
    """
}

class ElementInspector:
    def __init__(self):
        self.service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=self.service)
        self.console = Console()
        self.history = {}  # Using dict for unique tracking
        self.max_history = 5
        
    def inspect_page(self, url):
        self.driver.get(url)
        
        hover_script = scripts['hover_script']
        
        self.driver.execute_script(hover_script)
        
        with Live(self.generate_display(), refresh_per_second=4) as live:
            while True:
                if keyboard.is_pressed('q'):
                    break
                elif keyboard.is_pressed('c'):
                    self.clear_selection()
                elif keyboard.is_pressed('s'):
                    element_info = self.driver.execute_script("return window._lastSelectedInfo;")
                    self.save_to_json(element_info)
                    time.sleep(0.5)  # Prevent multiple saves
                elif keyboard.is_pressed('g'):
                    element_info = self.driver.execute_script("return window._lastSelectedInfo;")
                    self.get_element_scraper(element_info)
                    time.sleep(0.5)
                
                element_info = self.driver.execute_script("return window._lastSelectedInfo;")
                if element_info:
                    self.add_to_history(element_info)
                    live.update(self.generate_display(element_info))
                time.sleep(0.25)
    
    def generate_display(self, element_info=None):
        table = Table(title="Element Inspector")
        table.add_column("Controls", style="cyan", width=20)
        table.add_column("Element Info", style="green", width=40)
        table.add_column("History", style="yellow", width=30)
        
        # First row
        table.add_row(
            "Click: Select element",
            "Current Selection:",
            "Recent Elements:"
        )
        
        # Prepare rows
        control_rows = [
            "q: Quit",
            "c: Clear selection",
            "s: Save to JSON",
            "g: Generate scraper"
        ]
        
        info_rows = []
        if element_info:
            for key, value in element_info.items():
                if isinstance(value, dict):
                    info_rows.append(key)
                    for subkey, subvalue in value.items():
                        info_rows.append(f"  {subkey}: {subvalue}")
                else:
                    info_rows.append(f"{key}: {value}")
        
        history_rows = []
        for entry in self.history.values():
            history_text = f"{entry['time']} - <{entry['tag']}> {entry['id']} {entry['class']}\n\n"  # Add double newline for spacing
            history_rows.append(history_text)
        
        # Fill table with rows
        max_rows = max(len(control_rows), len(info_rows), len(history_rows))
        for i in range(max_rows):
            table.add_row(
                control_rows[i] if i < len(control_rows) else "",
                info_rows[i] if i < len(info_rows) else "",
                history_rows[i] if i < len(history_rows) else ""
            )
        
        return table

    def add_to_history(self, element_info):
        if not element_info:
            return
        
        # Create unique key
        unique_key = f"{element_info['tag']}_{element_info['id']}_{element_info['class']}"
        
        # Create history entry with padding
        entry = {
            'time': datetime.datetime.now().strftime("%H:%M:%S"),
            'tag': element_info['tag'],
            'id': element_info['id'] if element_info['id'] else '-',
            'class': element_info['class'] if element_info['class'] else '-'
        }
        
        self.history[unique_key] = entry
        
        # Maintain max size
        if len(self.history) > self.max_history:
            oldest_key = next(iter(self.history))
            self.history.pop(oldest_key)
    
    def clear_selection(self):
        self.driver.execute_script(scripts['clear_script'])
    
    def save_to_json(self, element_info):
        if not element_info:
            return
            
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"element_{timestamp}.json"
        
        # Create 'scraped_elements' directory if it doesn't exist
        os.makedirs('scraped_elements', exist_ok=True)
        filepath = os.path.join('scraped_elements', filename)
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(element_info, f, indent=4)
            self.console.print(f"[green]Element saved to {filepath}[/green]")
        except Exception as e:
            self.console.print(f"[red]Error saving element: {str(e)}[/red]")
    
    def cleanup(self):
        self.driver.quit()

    def get_element_scraper(self, element_info):
        if not element_info:
            return None
        
        selectors = []
        if element_info['id']:
            selectors.append(f"#{element_info['id']}")
        if element_info['class']:
            selectors.append(f".{'.'.join(element_info['class'].split())}")
        if not selectors:
            selectors.append(element_info['tag'])
        
        scraper_code = scripts['scrape_script']

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"scraper_{timestamp}.py"
        
        os.makedirs('scrapers', exist_ok=True)
        filepath = os.path.join('scrapers', filename)
        
        with open(filepath, 'w') as f:
            f.write(scraper_code)
            
        self.console.print(f"[green]Scraper saved to {filepath}[/green]")
        return scraper_code

if __name__ == "__main__":
    SITE_URL = "https://www.nasdaq.com"
    inspector = ElementInspector()
    inspector.inspect_page(SITE_URL or "https://www.google.com")