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

# ==========================================
# TAB 1: Live Inventory (Low Stock & New Arrivals)
# ==========================================

try:
    # 1. Топ-5 останніх новинок (сортування за датою появи від нових до старих)
    new_arrivals_params = {
        "store": "eq.mattel",
        "is_active": "eq.true",
        "current_qty": "gte.50",
        "title": "ilike.Hot Wheels*",
        "select": "id,title,image,url,current_qty,price,updated_at,detected_at,limit",
        "order": "detected_at.desc",
        "limit": "5"  # Показуємо рівно останні нові 5 одиниць
    }
    new_arrivals_list = fetch_data("products", new_arrivals_params)
    for p in new_arrivals_list:
        p["is_new_arrival"] = True  # маркер для шаблону

    # Зберігаємо ID новинок, щоб вони не дублювалися в блоці знизу, якщо раптом перетинаються
    seen_ids = {p["id"] for p in new_arrivals_list}

    # 2. Товари, кількість яких менше 625 (від найбільшої кількості до меншої)
    low_stock_url = (
        f"{sb_url}/rest/v1/products"
        f"?store=eq.mattel"
        f"&is_active=eq.true"
        f"&current_qty=gt.0"
        f"&current_qty=lt.625"  # Фільтр: менше 625 одиниць
        f"&select=id,title,image,url,current_qty,price,updated_at,limit"
        f"&order=current_qty.desc"  # Сортування від найбільшої кількості до меншої
    )
    res_low = requests.get(low_stock_url, headers=headers)
    res_low.raise_for_status()
    raw_low_stock = res_low.json()

    low_stock_list = []
    for p in raw_low_stock:
        if p["id"] not in seen_ids:
            p["is_new_arrival"] = False  # маркер, що це Low Stock товар
            low_stock_list.append(p)

except Exception as e:
    print(f"Live products error: {e}")
    new_arrivals_list = []
    low_stock_list = []

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
MAX_SHOPIFY_QTY = 50

def compute_last_cycle_stats(product_id: str) -> dict | None:
    rows = fetch_data(
        "product_qty_history",
        {
            "product_id": f"eq.{product_id}",
            "select": "old_qty,new_qty,changed_at",
            "order": "changed_at.desc",
        },
    )
    if not rows:
        return None

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

    last_soldout = None
    soldout_idx = -1
    for i, ev in enumerate(norm_rows):
        old_q, new_q = ev["old_qty"], ev["new_qty"]
        if old_q is not None and old_q > 0 and new_q is not None and new_q == 0:
            last_soldout = ev
            soldout_idx = i
            break

    if last_soldout is None:
        return None

    last_restock = None
    for i in range(soldout_idx + 1, len(norm_rows)):
        ev = norm_rows[i]
        old_q, new_q = ev["old_qty"], ev["new_qty"]
        if (old_q is None or old_q == 0) and (new_q is not None and new_q > 0):
            last_restock = ev
            break
        if (new_q is not None and old_q is not None) and (new_q >= MAX_SHOPIFY_QTY and new_q > old_q):
            last_restock = ev
            break

    if last_restock is None:
        last_restock = norm_rows[-1] 

    duration = last_soldout["changed_at"] - last_restock["changed_at"]
    if duration.total_seconds() <= 0:
        return None

    total_restocks = 0
    for i in range(len(norm_rows) - 1):
        curr = norm_rows[i]
        prev = norm_rows[i + 1]
        if curr["new_qty"] is not None and prev["new_qty"] is not None:
            if curr["new_qty"] > prev["new_qty"] and curr["new_qty"] >= 50:
                total_restocks += 1
            elif prev["new_qty"] == 0 and curr["new_qty"] > 0:
                total_restocks += 1

    return {
        "restock_at": last_restock["changed_at"],
        "soldout_at": last_soldout["changed_at"],
        "total_restocks": max(1, total_restocks),
        "duration": duration,
    }

# TAB 3: Sold Out
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
                "title": "ilike.Hot Wheels*",
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
    new_arrivals=new_arrivals_list,
    low_stock_products=low_stock_list,
    coming_products=coming_products,
    sold_products=sold_products,
    last_updated=datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
)

with open('index.html', 'w') as f:
    f.write(html_output)
