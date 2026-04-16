import os
import requests
from jinja2 import Template
from datetime import datetime, timedelta

# 1. Configuration
sb_url = os.getenv('SUPABASE_URL')
sb_key = os.getenv('SUPABASE_KEY')
headers = {"apikey": sb_key, "Authorization": f"Bearer {sb_key}"}

def fetch_data(endpoint, params=None):
    url = f"{sb_url}/rest/v1/{endpoint}"
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error fetching {endpoint}: {e}")
        return []

# TAB 1: Live Inventory
# Note: Manual string to avoid library encoding issues with the comma
live_url = (
    f"{sb_url}/rest/v1/products"
    f"?store=eq.mattel"
    f"&is_active=eq.true"
    f"&current_qty=gt.0"
    f"&current_qty=lt.625"
    f"&select=id,title,image,url,current_qty,price,updated_at,limit"
    f"&order=current_qty.asc"
)

live_products = []
try:
    res = requests.get(live_url, headers=headers)
    res.raise_for_status()
    live_products = res.json()
except Exception as e:
    print(f"Live products error: {e}")

# TAB 2: Coming Soon
soon_params = {
    "store": "eq.mattel",
    "availability": "eq.Coming Soon",
    "select": "id,title,image,url,current_qty,price,updated_at,limit",
    "order": "updated_at.desc"
}
coming_products = fetch_data("products", soon_params)

# TAB 3: Sold Out (Unique & Latest 7)
def fmt_duration(td: timedelta) -> str:
    total = int(td.total_seconds())
    if total < 60:
        return "<1 хв"
    minutes = total // 60
    hours = minutes // 60
    days = hours // 24
    parts = []
    if days:
        parts.append(f"{days}д")
    if hours % 24:
        parts.append(f"{hours % 24}г")
    if minutes % 60:
        parts.append(f"{minutes % 60}хв")
    return " ".join(parts)


def compute_last_cycle_stats(product_id: str) -> dict | None:
    """
    Для одного product_id:
    - тягнемо всю history по ньому
    - знаходимо останній закритий цикл: restock → soldout
    - рахуємо:
        - sold_amount = сума всіх зменшень qty між restock і soldout
        - duration = soldout_at - restock_at
    Повертає dict або None, якщо циклу немає.
    """
    rows = fetch_data(
        "product_qty_history",
        {
            "product_id": f"eq.{product_id}",
            "select": "old_qty,new_qty,changed_at",
            "order": "changed_at.asc",
        },
    )
    if not rows:
        return None

    pending_start = None
    sold_amount = 0
    last_cycle = None

    for ev in rows:
        old_q = ev.get("old_qty")
        new_q = ev.get("new_qty")
        changed_at = ev.get("changed_at")
        if changed_at is None:
            continue
        changed_dt = datetime.fromisoformat(changed_at.replace("Z", "+00:00"))

        is_restock = old_q == 0 and new_q is not None and new_q > 0
        is_soldout = new_q == 0 and old_q is not None and old_q > 0

        if is_restock:
            # починаємо новий цикл
            pending_start = changed_dt
            sold_amount = 0
        elif pending_start is not None:
            # всередині циклу: рахуємо всі зменшення
            if old_q is not None and new_q is not None and new_q < old_q:
                sold_amount += (old_q - new_q)

            if is_soldout:
                duration = changed_dt - pending_start
                if duration.total_seconds() > 0 and sold_amount > 0:
                    last_cycle = {
                        "restock_at": pending_start,
                        "soldout_at": changed_dt,
                        "sold_amount": sold_amount,
                        "duration": duration,
                    }
                pending_start = None
                sold_amount = 0

    return last_cycle


# TAB 3: Sold Out (Unique & Latest 10)
history_params = {
    "new_qty": "eq.0",
    "select": "product_id,changed_at",
    "order": "changed_at.desc",
    "limit": "40"  # трохи з запасом, щоб набрати 10 унікальних
}
history_records = fetch_data("product_qty_history", history_params)

sold_products = []
if history_records:
    unique_sold_map = {}
    for rec in history_records:
        p_id = rec['product_id']
        if p_id not in unique_sold_map:
            unique_sold_map[p_id] = rec['changed_at']
        if len(unique_sold_map) >= 10:
            break

    p_ids = ",".join([f"\"{pid}\"" for pid in unique_sold_map.keys()])
    details = fetch_data(
        "products",
        {
            "id": f"in.({p_ids})",
            "select": "id,title,image,url,price,limit"
        }
    )

    # збагачуємо кожен товар даними останнього циклу
    for item in details:
        pid = item["id"]
        item['sold_at'] = unique_sold_map.get(pid)

        cycle = compute_last_cycle_stats(pid)
        if cycle:
            item["sold_amount"] = cycle["sold_amount"]
            item["sold_duration"] = fmt_duration(cycle["duration"])
        else:
            item["sold_amount"] = None
            item["sold_duration"] = None

        sold_products.append(item)

    sold_products.sort(key=lambda x: x.get('sold_at', ''), reverse=True)

# 2. Render Template
with open('template.html', 'r') as f:
    template = Template(f.read())

html_output = template.render(
    live_products=live_products,
    coming_products=coming_products,
    sold_products=sold_products,
    last_updated=datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
)

with open('index.html', 'w') as f:
    f.write(html_output)
