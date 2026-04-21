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

    norm_rows = []
    for ev in rows:
        changed_at = ev.get("changed_at")
        if not changed_at:
            continue
        dt = datetime.fromisoformat(changed_at.replace("Z", "+00:00"))
        norm_rows.append({
            "old_qty": ev.get("old_qty"),
            "new_qty": ev.get("new_qty"),
            "changed_at": dt,
        })
    if not norm_rows:
        return None

    # Шукаємо останній soldout (old>0 → new=0)
    soldout_idx = None
    for i in range(len(norm_rows) - 1, -1, -1):
        ev = norm_rows[i]
        old_q, new_q = ev["old_qty"], ev["new_qty"]
        if old_q is not None and new_q is not None and old_q > 0 and new_q == 0:
            soldout_idx = i
            break

    if soldout_idx is None:
        return None

    soldout_ev = norm_rows[soldout_idx]

    # Шукаємо початок циклу
    start_idx = 0
    for j in range(soldout_idx - 1, -1, -1):
        ev = norm_rows[j]
        old_q, new_q = ev["old_qty"], ev["new_qty"]
        # Справжній restock з нуля
        if old_q == 0 and new_q is not None and new_q > 0:
            start_idx = j
            break
        # Попередній soldout — межа циклу
        if old_q is not None and new_q is not None and new_q == 0:
            start_idx = j + 1
            break
        # Додавання товару (old>0 → new>old) — теж початок нового мікро-циклу
        if old_q is not None and new_q is not None and new_q > old_q:
            start_idx = j
            break

    start_ev = norm_rows[start_idx]

    # Визначаємо початкову кількість циклу
    # Якщо старт — restock (0→X), беремо new_qty
    # Якщо старт — перший запис в БД, беремо old_qty (бо не знаємо скільки було до нього)
    start_new_q = start_ev["new_qty"]
    start_old_q = start_ev["old_qty"]

    if start_old_q == 0:
        # restock: початкова кількість = new_qty рестоку
        cycle_start_qty = start_new_q
    else:
        # перший запис в БД: old_qty — це перше відоме значення
        cycle_start_qty = start_old_q

    # Рахуємо sold_amount: тільки зменшення qty
    sold_amount = 0
    for k in range(start_idx, soldout_idx + 1):
        ev = norm_rows[k]
        old_q, new_q = ev["old_qty"], ev["new_qty"]
        if old_q is not None and new_q is not None and new_q < old_q:
            sold_amount += (old_q - new_q)

    duration = soldout_ev["changed_at"] - start_ev["changed_at"]
    if duration.total_seconds() <= 0 or sold_amount <= 0:
        return None

    # Якщо початкова кількість була 625 — реальна кількість невідома
    is_exact = (cycle_start_qty < MAX_SHOPIFY_QTY) if cycle_start_qty is not None else False

    return {
        "restock_at": start_ev["changed_at"],
        "soldout_at": soldout_ev["changed_at"],
        "sold_amount": sold_amount,
        "sold_amount_exact": is_exact,  # False = показувати "500+"
        "duration": duration,
    }


# TAB 3: Sold Out (Unique & Latest 10)
history_params = {
    "new_qty": "eq.0",
    "select": "product_id,changed_at",
    "order": "changed_at.desc",
    "limit": "40",  # з запасом, щоб набрати 10 унікальних
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
                sold_amount = cycle["sold_amount"]
                is_exact = cycle["sold_amount_exact"]
                item["sold_amount"] = sold_amount if is_exact else None
                item["sold_amount_min"] = None if is_exact else sold_amount  # нижня межа для "500+"
                item["sold_amount_exact"] = is_exact
                item["sold_duration"] = fmt_duration(cycle["duration"])
            else:
                item["sold_amount"] = None
                item["sold_amount_min"] = None
                item["sold_amount_exact"] = None
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
