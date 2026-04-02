import os
import requests
from jinja2 import Template # треба буде додати в requirements.txt

# 1. Отримуємо дані з Supabase
url = f"{os.getenv('SUPABASE_URL')}/rest/v1/products?store=eq.mattel&current_qty=lt.625&is_active=eq.true&select=*"
headers = {
    "apikey": os.getenv('SUPABASE_KEY'),
    "Authorization": f"Bearer {os.getenv('SUPABASE_KEY')}"
}
data = requests.get(url, headers=headers).json()

# 2. Завантажуємо твій HTML шаблон і рендеримо його
with open('template.html', 'r') as f:
    template = Template(f.read())

html_output = template.render(products=data)

# 3. Зберігаємо готовий файл
with open('index.html', 'w') as f:
    f.write(html_output)
