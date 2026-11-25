import csv
import json
import os

from dotenv import load_dotenv
from litellm import completion

load_dotenv()
MODEL = os.getenv("LLM_MODEL", "groq/openai/gpt-oss-20b")
DATA = "data/pharmacy_stock.csv"


# A normal Python function. The model never runs this; our code does.
def check_stock(item: str, strength: str = "") -> list[dict]:
    with open(DATA, newline="") as f:
        rows = list(csv.DictReader(f))
    rows = [r for r in rows if item.lower() in r["item"].lower()]
    if strength:
        rows = [r for r in rows if strength.lower() in r["strength"].lower()]
    return rows


TOOLS = {"check_stock": check_stock}

# The same function described to the model as a JSON schema.
tool_schemas = [{
    "type": "function",
    "function": {
        "name": "check_stock",
        "description": "Look up stock of a medicine. Returns matching rows with quantity, "
                       "unit_price_ghs and expiry_date. Empty list = not stocked.",
        "parameters": {
            "type": "object",
            "properties": {
                "item": {"type": "string", "description": "Medicine name only, e.g. 'amoxicillin'"},
                "strength": {"type": "string", "description": "Optional, e.g. '500mg'"},
            },
            "required": ["item"],
        },
    },
}]

messages = [
    {"role": "system", "content": "You are a pharmacy stock assistant. Use the tools; never guess."},
    {"role": "user", "content": "Do we have amoxicillin 500mg?"},
]

resp = completion(model=MODEL, messages=messages, tools=tool_schemas)

for _ in range(5):                      # max_steps, so it can never loop forever
    msg = resp.choices[0].message
    if not msg.tool_calls:              # no tool requested -> this is the final answer
        break
    messages.append(msg.model_dump())   # the model's decision (an ACTION)
    for tc in msg.tool_calls:
        args = json.loads(tc.function.arguments)
        print("Model asked for:", tc.function.name, args)
        result = TOOLS[tc.function.name](**args)          # OUR code runs it
        print("Tool result (percept):", result)
        messages.append({"role": "tool", "tool_call_id": tc.id,
                         "content": json.dumps(result)})  # send the PERCEPT back
    resp = completion(model=MODEL, messages=messages, tools=tool_schemas)

print("\nFinal answer:", resp.choices[0].message.content)