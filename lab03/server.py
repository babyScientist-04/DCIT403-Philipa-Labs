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


# (Step 4: the record_sale tool goes HERE)


if __name__ == "__main__":
    mcp.run()