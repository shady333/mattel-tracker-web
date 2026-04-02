import os
import requests
from jinja2 import Template
from datetime import datetime

# 1. Запит до Supabase
url = f"{os.getenv('SUPABASE_URL')}/rest/v1/products"
headers = {
    "apikey": os.getenv('SUPABASE_KEY'),
    "Authorization": f"Bearer {os.getenv('SUPABASE_KEY')}",
    "Prefer": "return=representation"
}
params = {
    "store": "eq.mattel",
    "is_active": "eq.true",
    "current_qty": "lt.625",
    "select": "title,image,url,current_qty",
    "order": "current_qty.asc"
}

response = requests.get(url, headers=headers, params=params)
products = response.json()

# 2. Рендеринг шаблону
with open('template.html', 'r') as f:
    template = Template(f.read())

html_output = template.render(
    products=products, 
    last_updated=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
)

# 3. Запис результату
with open('index.html', 'w') as f:
    f.write(html_output)
