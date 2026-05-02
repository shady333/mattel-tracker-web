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

# Helpers
def fmt_duration(td: timedelta) -> str:
    total = int(td.total_seconds())
    if total < 60:
        return "<1 min"
    minutes = total // 60
    hours = minutes // 60
    days = hours // 24
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours % 24:
        parts.append(f"{hours % 24}h")
    if minutes % 60:
        parts.append(f"{minutes % 60}m")
    return " ".join(parts)


MIN_VALID_YEAR = 2024
MAX_SHOPIFY_QTY = 625


def compute_last_cycle_stats(product_id: str) -> dict | None:
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

    # Парсимо і фільтруємо невалідні дати
    norm_rows = []
    for ev in rows:
        changed_at = ev.get("changed_at")
        if not changed_at:
            continue
        dt = datetime.fromisoformat(changed_at.replace("Z", "+00:00"))
        if dt.year < MIN_VALID_YEAR:
            continue
        norm_rows.append({
            "old_qty": ev.get("old_qty"),
            "new_qty": ev.get("new_qty"),
            "changed_at": dt,
        })

    if not norm_rows:
        return None

    def is_restock(ev: dict) -> bool:
        old_q, new_q = ev["old_qty"], ev["new_qty"]
        if new_q is None or new_q <= 0:
            return False
        if old_q is None or old_q == 0:
            return True
        if new_q >= MAX_SHOPIFY_QTY and new_q > old_q:
            return True
        return False

    def is_soldout(ev: dict) -> bool:
        old_q, new_q = ev["old_qty"], ev["new_qty"]
        return (old_q is not None and old_q > 0
                and new_q is not None and new_q == 0)

    # Рахуємо всі restocks
    restock_events = [ev for ev in norm_rows if is_restock(ev)]
    total_restocks = len(restock_events)

    # Знаходимо останній soldout
    last_soldout = None
    for ev in reversed(norm_rows):
        if is_soldout(ev):
            last_soldout = ev
            break

    if last_soldout is None:
        return None

    # Знаходимо останній restock ДО цього soldout
    last_restock = None
    for ev in reversed(restock_events):
        if ev["changed_at"] < last_soldout["changed_at"]:
            last_restock = ev
            break

    # Fallback: якщо restock не знайдено — беремо перший запис в БД
    if last_restock is None:
        first_ev = norm_rows[0]
        if first_ev["changed_at"] < last_soldout["changed_at"]:
            last_restock = first_ev
        else:
            return None

    duration = last_soldout["changed_at"] - last_restock["changed_at"]

    if duration.total_seconds() <= 0:
        return None

    return {
        "restock_at": last_restock["changed_at"],
        "soldout_at": last_soldout["changed_at"],
        "total_restocks": total_restocks,
        "duration": duration,
    }


# TAB 3: Sold Out (Unique & Latest 10)
history_params = {
    "new_qty": "eq.0",
    "select": "product_id,changed_at",
    "order": "changed_at.desc",
    "limit": "40",
}
history_records = fetch_data("product_qty_history", history_params)

sold_products = []
if history_records:
    unique_sold_map: dict[str, str] = {}
    for rec in history_records:
        p_id = rec["product_id"]
        if p_id not in unique_sold_map:
            unique_sold_map[p_id] = rec["changed_at"]
        if len(unique_sold_map) >= 10:
            break

    if unique_sold_map:
        p_ids = ",".join([f"\"{pid}\"" for pid in unique_sold_map.keys()])
        details = fetch_data(
            "products",
            {
                "id": f"in.({p_ids})",
                "select": "id,title,image,url,price,limit",
            },
        )

        for item in details:
            pid = item["id"]
            item["sold_at"] = unique_sold_map.get(pid)

            cycle = compute_last_cycle_stats(pid)
            if cycle:
                item["total_restocks"] = cycle["total_restocks"]
                item["sold_duration"] = fmt_duration(cycle["duration"])
            else:
                item["total_restocks"] = None
                item["sold_duration"] = None

            sold_products.append(item)

        sold_products.sort(key=lambda x: x.get("sold_at", ""), reverse=True)

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
