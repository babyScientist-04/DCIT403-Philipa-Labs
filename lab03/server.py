import csv
import datetime as dt

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("pharmacy-stock")
DATA = "data/pharmacy_stock.csv"
FIELDS = ["item", "strength", "form", "quantity", "unit_price_ghs", "expiry_date"]


def load():
    with open(DATA, newline="") as f:
        return list(csv.DictReader(f))


def match(rows, item, strength=""):
    rows = [r for r in rows if item.lower().strip() in r["item"].lower()]
    if strength:
        rows = [r for r in rows if strength.lower().replace(" ", "")
                in r["strength"].lower().replace(" ", "")]
    return rows


# ---------------- READ TOOLS (percepts) ----------------

@mcp.tool()
def check_stock(item: str, strength: str = "") -> list[dict]:
    """Check stock of ONE specific medicine. Use when the user names a medicine,
    e.g. "Do we have amoxicillin 500mg?" -> item="amoxicillin", strength="500mg".
    item: medicine name only, WITHOUT the strength.
    strength: optional, e.g. "500mg"; leave empty to see all strengths.
    Returns rows with quantity (packs), unit_price_ghs and expiry_date.
    An empty list means the pharmacy does not stock it."""
    return match(load(), item, strength)


@mcp.tool()
def search_items(query: str) -> list[dict]:
    """Free-text search over item name, strength and form. Use when the user is
    browsing or unsure of the name, e.g. "what syrups do we have?" -> query="syrup".
    Returns all matching rows (empty list if none)."""
    q = query.lower().strip()
    return [r for r in load() if q in f'{r["item"]} {r["strength"]} {r["form"]}'.lower()]


@mcp.tool()
def list_expiring(days: int = 60) -> list[dict]:
    """List items expiring within the next `days` days (default 60), soonest first.
    Already-expired items are included with status "EXPIRED".
    Use for "Which items expire within 60 days?"."""
    today = dt.date.today()
    out = []
    for r in load():
        left = (dt.date.fromisoformat(r["expiry_date"]) - today).days
        if left <= days:
            out.append({**r, "days_left": left,
                        "status": "EXPIRED" if left < 0 else "expiring"})
    return sorted(out, key=lambda r: r["days_left"])


# ---------------- WRITE TOOL (action / actuator) ----------------

def save(rows):
    with open(DATA, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)


@mcp.tool()
def record_sale(item: str, strength: str, qty: int) -> dict:
    """ACTION - CHANGES STOCK. Record that qty packs of ONE medicine were sold and
    reduce its stock. Only call this when the user clearly says to sell or record
    a sale. For price questions use check_stock instead. strength is required, e.g. "500mg".
    The sale is REFUSED (stock unchanged) if qty is not a positive whole number,
    no product or more than one product matches, the product has expired, or there
    is not enough stock. Always pass the returned message on to the user."""
    if qty <= 0:
        return {"ok": False, "message": f"Refused: quantity must be positive (got {qty})."}

    rows = load()
    found = match(rows, item, strength)
    if not found:
        return {"ok": False, "message": f"Refused: no product matches '{item} {strength}'."}
    if len(found) > 1:
        return {"ok": False, "message": "Refused: more than one product matches; give the exact strength."}

    row = found[0]
    if dt.date.fromisoformat(row["expiry_date"]) < dt.date.today():
        return {"ok": False, "message": f'Refused: {row["item"]} expired on {row["expiry_date"]}.'}

    have = int(row["quantity"])
    if qty > have:
        return {"ok": False, "message": f'Refused: only {have} packs of {row["item"]} '
                                        f'{row["strength"]} in stock, cannot sell {qty}.'}

    row["quantity"] = str(have - qty)   # row is inside rows, so rows is updated too
    save(rows)
    total = qty * float(row["unit_price_ghs"])
    return {"ok": True, "message": f'Sold {qty} x {row["item"]} {row["strength"]} for '
                                   f'GHS {total:.2f}. {row["quantity"]} packs left.'}


if __name__ == "__main__":
    mcp.run()