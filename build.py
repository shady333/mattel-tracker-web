import os
import requests
from jinja2 import Template
from datetime import datetime

# 1. Запит до Supabase
url = f"{os.getenv('SUPABASE_URL')}/rest/v1/products"
headers = {
    "apikey": os.getenv('SUPABASE_KEY'),
    "Authorization": f"Bearer {os.getenv('SUPABASE_KEY')}",
}

# ВИПРАВЛЕНО: об'єднуємо умови в один рядок через кому (це означає AND)
params = {
    "store": "eq.mattel",
    "is_active": "eq.true",
    "current_qty": "gt.0,lt.625",  # ТУТ МАГІЯ: більше 0 ТА менше 625
    "select": "title,image,url,current_qty,price,updated_at",
    "order": "updated_at.desc"
}

try:
    response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()
    products = response.json()
except Exception as e:
    print(f"Error fetching data: {e}")
    products = []

# 2. Рендеринг шаблону
with open('template.html', 'r') as f:
    template = Template(f.read())

html_output = template.render(
    products=products, 
    last_updated=datetime.now().strftime("%d.%m.%Y %H:%M")
)

with open('index.html', 'w') as f:
    f.write(html_output)
