import os
import requests
from jinja2 import Template
from datetime import datetime

# 1. Configuration
sb_url = os.getenv('SUPABASE_URL')
sb_key = os.getenv('SUPABASE_KEY')
headers = {"apikey": sb_key, "Authorization": f"Bearer {sb_key}"}

def fetch_data(endpoint, params):
    url = f"{sb_url}/rest/v1/{endpoint}"
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error fetching {endpoint}: {e}")
        return []

# TAB 1: Live Inventory
# Active, Qty > 0, Qty < 625
live_params = {
    "store": "eq.mattel",
    "is_active": "eq.true",
    "current_qty": "gt.0,lt.625",
    "select": "title,image,url,current_qty,price,updated_at,limit",
    "order": "current_qty.asc"
}
live_products = fetch_data("products", live_params)

# TAB 2: Coming Soon
# Active, availability == 'Coming Soon'
soon_params = {
    "store": "eq.mattel",
    "is_active": "eq.true",
    "availability": "eq.Coming Soon",
    "select": "title,image,url,current_qty,price,updated_at,limit",
    "order": "updated_at.desc"
}
coming_products = fetch_data("products", soon_params)

# TAB 3: Sold Out (via product_qty_history)
# 1. Get 7 latest records where new_qty is 0
history_params = {
    "new_qty": "eq.0",
    "select": "product_id,changed_at",
    "order": "changed_at.desc",
    "limit": "7"
}
history_records = fetch_data("product_qty_history", history_params)

sold_products = []
if history_records:
    # 2. Extract IDs and fetch product details
    product_ids = ",".join([f"\"{r['product_id']}\"" for r in history_records])
    sold_details_params = {
        "id": f"in.({product_ids})",
        "select": "id,title,image,url,price,limit"
    }
    details = fetch_data("products", sold_details_params)
    
    # Map changed_at time from history to the product objects
    time_map = {r['product_id']: r['changed_at'] for r in history_records}
    for item in details:
        item['sold_at'] = time_map.get(item['id'])
        sold_products.append(item)
    
    # Sort sold_products by the history timestamp
    sold_products.sort(key=lambda x: x['sold_at'], reverse=True)

# 2. Render Template
with open('template.html', 'r') as f:
    template = Template(f.read())

html_output = template.render(
    live_products=live_products,
    coming_products=coming_products,
    sold_products=sold_products,
    last_updated=datetime.now().strftime("%b %d, %H:%M")
)

with open('index.html', 'w') as f:
    f.write(html_output)
