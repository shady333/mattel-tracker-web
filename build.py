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
params = {
    "store": "eq.mattel",
    "is_active": "eq.true",
    "current_qty": "gt.0",    # Більше 0
    "current_qty": "lt.625",  # Менше 625
    "select": "title,image,url,current_qty,price,updated_at",
    "order": "updated_at.desc" # Останні оновлення зверху
}

response = requests.get(url, headers=headers, params=params)
products = response.json()

# 2. Рендеринг шаблону
with open('template.html', 'r') as f:
    template = Template(f.read())

html_output = template.render(
    products=products, 
    last_updated=datetime.now().strftime("%d.%m.%Y %H:%M")
)

with open('index.html', 'w') as f:
    f.write(html_output)
