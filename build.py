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
    "current_qty": "lt.625",
    "current_qty": "gt.0",  # ВІДСІЮЄМО НУЛІ
    "select": "title,image,url,current_qty",
    "order": "current_qty.asc" # За замовчуванням від мін до макс
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
