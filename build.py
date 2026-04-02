import os
import requests
from jinja2 import Template
from datetime import datetime

# 1. Налаштування
sb_url = os.getenv('SUPABASE_URL')
sb_key = os.getenv('SUPABASE_KEY')

# URL з фільтрами: активні, більше 0, менше 625. Сортування: Qty Low to High
url = f"{sb_url}/rest/v1/products?store=eq.mattel&is_active=eq.true&current_qty=gt.0&current_qty=lt.625&select=title,image,url,current_qty,price,updated_at&order=current_qty.asc"

headers = {
    "apikey": sb_key,
    "Authorization": f"Bearer {sb_key}",
}

products = []
try:
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    products = response.json()
    print(f"Успішно завантажено {len(products)} товарів")
except Exception as e:
    print(f"Помилка запиту: {e}")

# 2. Рендеринг шаблону
try:
    with open('template.html', 'r') as f:
        template = Template(f.read())

    html_output = template.render(
        products=products, 
        last_updated=datetime.now().strftime("%d.%m.%Y %H:%M")
    )

    with open('index.html', 'w') as f:
        f.write(html_output)
except Exception as e:
    print(f"Помилка шаблону: {e}")
