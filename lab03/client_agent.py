import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone

from dotenv import load_dotenv
from litellm import acompletion
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

load_dotenv()
MODEL = os.getenv("LLM_MODEL", "groq/openai/gpt-oss-20b")
LOG = "evidence/tool_calls.jsonl"
MAX_STEPS = 6

SYSTEM = ("You are the stock assistant for a community pharmacy in Ghana. "
          "Answer only from tool results; never guess stock, prices or dates. "
          "Prices are in GHS. Never oversell. Only record a sale when the user "
          "clearly asks for one. If a tool refuses, tell the user exactly why.")

SIX_QUESTIONS = [
    "Do we have amoxicillin 500mg?",
    "Which items expire within 60 days?",
    "What do 2 packs of paracetamol 500mg cost?",
    "What syrups do we have?",
    "Record a sale of 3 packs of amoxicillin 500mg.",            # a real sale
    "Sell 500 packs of ciprofloxacin 500mg to a walk-in customer.",  # oversale
]

# Start server.py as a subprocess and talk to it over stdin/stdout
params = StdioServerParameters(command="python", args=["server.py"])


def log_call(question, name, args, text, ms):
    """Step 5: one JSON line per tool call."""
    with open(LOG, "a") as f:
        f.write(json.dumps({
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "question": question,
            "tool": name,
            "arguments": args,
            "result_summary": text[:200].replace("\n", " "),
            "duration_ms": round(ms, 1),
        }) + "\n")


async def call_tool(session, question, name, args):
    start = time.perf_counter()
    try:
        result = await session.call_tool(name, args)
        text = "\n".join(c.text for c in result.content if c.type == "text") or "[]"
    except Exception as e:          # bad tool name or arguments: tell the model, don't crash
        text = f"TOOL ERROR: {e}"
    log_call(question, name, args, text, (time.perf_counter() - start) * 1000)
    return text


async def ask(session, schemas, question):
    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": question}]
    for _ in range(MAX_STEPS):
        resp = await acompletion(model=MODEL, messages=messages, tools=schemas)
        msg = resp.choices[0].message
        if not msg.tool_calls:
            return msg.content
        messages.append(msg.model_dump())
        for tc in msg.tool_calls:
            args = json.loads(tc.function.arguments or "{}")
            print(f"  -> {tc.function.name}({args})")
            text = await call_tool(session, question, tc.function.name, args)
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": text})
    return "Stopped: step limit reached."


async def main(questions):
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = (await session.list_tools()).tools       # DISCOVERY
            schemas = [{"type": "function", "function": {
                "name": t.name, "description": t.description,
                "parameters": t.inputSchema}} for t in tools]
            print("Discovered tools:", [t.name for t in tools], "\n")
            for q in questions:
                print("Q:", q)
                print("A:", await ask(session, schemas, q), "\n")
                await asyncio.sleep(2)   # gentle on free-tier rate limits


if __name__ == "__main__":
    if "--six" in sys.argv:
        asyncio.run(main(SIX_QUESTIONS))
    else:
        asyncio.run(main([" ".join(sys.argv[1:]) or "Do we have amoxicillin 500mg?"]))