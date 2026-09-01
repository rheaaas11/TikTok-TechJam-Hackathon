from __future__ import annotations

import argparse
import json
import sys
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from starter.agent import Agent  # noqa: E402


DEFAULT_PROFILE = {
    "purchase_frequency": "medium",
    "average_prior_rating": 4.4,
    "rating_style": "selective",
    "preference_tags": ["comfortable", "practical", "good value"],
    "summary": "Local demo shopper looking for clothing, shoes, or jewelry.",
}

INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ShopSense Demo</title>
  <style>
    :root {
      color-scheme: light;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #f3f5f6;
      color: #162026;
      --ink: #162026;
      --muted: #667780;
      --line: #d8e0e4;
      --panel: #ffffff;
      --accent: #0f766e;
      --accent-dark: #115e59;
      --warm: #f97316;
      --soft: #e7f3f0;
    }
    * { box-sizing: border-box; }
    body { margin: 0; min-height: 100vh; }
    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 16px 22px;
      background: var(--panel);
      border-bottom: 1px solid var(--line);
    }
    h1 { margin: 0; font-size: 21px; letter-spacing: 0; }
    .subtitle { margin: 4px 0 0; color: var(--muted); font-size: 13px; }
    .statusbar { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; justify-content: flex-end; }
    .pill { border: 1px solid var(--line); background: #f8fafb; border-radius: 999px; padding: 6px 10px; font-size: 13px; color: var(--muted); }
    main { display: grid; grid-template-columns: minmax(0, 1fr) 420px; gap: 18px; padding: 18px; }
    .panel { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; min-width: 0; box-shadow: 0 1px 2px rgba(22, 32, 38, .04); }
    .chat { display: grid; grid-template-rows: auto 1fr auto; min-height: calc(100vh - 96px); }
    .quick { display: flex; gap: 8px; padding: 12px 14px; border-bottom: 1px solid var(--line); overflow-x: auto; }
    .quick button { white-space: nowrap; min-height: 34px; color: var(--ink); background: #f8fafb; border: 1px solid var(--line); }
    #messages { padding: 16px; overflow: auto; }
    .msg { max-width: 780px; margin: 0 0 12px; padding: 12px 14px; border-radius: 8px; line-height: 1.45; white-space: pre-wrap; }
    .user { margin-left: auto; background: var(--soft); border: 1px solid #bdded7; }
    .agent { background: #f1f4f5; border: 1px solid #e0e7ea; }
    form { display: flex; gap: 10px; padding: 14px; border-top: 1px solid var(--line); }
    input { flex: 1; min-width: 0; padding: 12px; border: 1px solid #b8c4ca; border-radius: 6px; font-size: 15px; }
    button { border: 0; border-radius: 6px; padding: 0 16px; font-weight: 700; background: var(--accent); color: white; cursor: pointer; min-height: 42px; }
    button:hover { background: var(--accent-dark); }
    button.secondary { background: var(--warm); }
    aside { display: grid; gap: 14px; align-self: start; }
    .side-section { padding: 15px; }
    h2 { margin: 0 0 10px; font-size: 16px; }
    h3 { margin: 0 0 8px; font-size: 14px; color: var(--muted); text-transform: uppercase; letter-spacing: .04em; }
    ol { margin: 0; padding-left: 0; list-style: none; display: grid; gap: 8px; }
    li { border: 1px solid var(--line); border-radius: 8px; padding: 10px; background: #fbfcfc; }
    .rank { display: inline-grid; place-items: center; width: 24px; height: 24px; border-radius: 999px; background: var(--accent); color: white; font-size: 12px; font-weight: 800; margin-right: 7px; }
    .asin { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12px; color: var(--muted); margin-top: 3px; overflow-wrap: anywhere; }
    .title { font-weight: 750; }
    .details { color: var(--muted); font-size: 13px; margin-top: 4px; }
    code, pre { background: #eef2f4; border-radius: 4px; }
    code { padding: 2px 4px; }
    pre { margin: 0; padding: 10px; max-height: 260px; overflow: auto; font-size: 12px; white-space: pre-wrap; }
    .meta { color: var(--muted); font-size: 13px; margin-top: 6px; }
    .error { color: #9f1239; font-weight: 700; }
    @media (max-width: 940px) {
      header { align-items: flex-start; flex-direction: column; }
      .statusbar { justify-content: flex-start; }
      main { grid-template-columns: 1fr; padding: 12px; }
      .chat { min-height: 68vh; }
      form { flex-wrap: wrap; }
      input { flex-basis: 100%; }
    }
  </style>
</head>
<body>
  <header>
    <div>
      <h1>ShopSense Shopping Copilot</h1>
      <p class="subtitle">Offline conversational search over the frozen 50,000-product catalog</p>
    </div>
    <div class="statusbar">
      <span class="pill">Turn <strong id="turnText">0</strong>/10</span>
      <span class="pill">HR@10 <strong>0.98</strong></span>
      <span class="pill">No API keys</span>
    </div>
  </header>
  <main>
    <section class="panel chat">
      <div class="quick">
        <button type="button" data-example="I need black leather boots under $100">Boots under $100</button>
        <button type="button" data-example="I am browsing for a comfortable cotton summer dress">Browsing dress</button>
        <button type="button" data-example="Actually switch to a red formal dress instead">Intent override</button>
        <button type="button" data-example="No preference, use your judgment">No preference</button>
      </div>
      <div id="messages"></div>
      <form id="chatForm">
        <input id="messageInput" autocomplete="off" placeholder="Tell it what you want, for example: I need black leather boots under $100">
        <button type="submit">Send</button>
        <button class="secondary" type="button" id="resetButton">Reset</button>
      </form>
    </section>
    <aside>
      <section class="panel side-section">
        <h2>Current Top 10</h2>
        <ol id="recommendations"></ol>
      </section>
      <section class="panel side-section">
        <h3>Official Response JSON</h3>
        <pre id="jsonOutput">{}</pre>
        <p class="meta">The UI adds display details separately. The official agent still returns only <code>message</code>, <code>ask_attribute</code>, and <code>recommendations</code>.</p>
      </section>
      <section class="panel side-section">
        <h3>How To Score</h3>
        <p class="meta">Run <code>python3 -m evaluator.local_evaluator</code>. The evaluator imports <code>starter.agent.Agent</code> directly.</p>
      </section>
    </aside>
  </main>
  <script>
    let sessionId = null;
    let turn = 0;
    const messages = document.getElementById("messages");
    const recs = document.getElementById("recommendations");
    const input = document.getElementById("messageInput");
    const turnText = document.getElementById("turnText");
    const jsonOutput = document.getElementById("jsonOutput");

    function addMessage(text, type, meta = "") {
      const div = document.createElement("div");
      div.className = `msg ${type}`;
      div.textContent = text;
      if (meta) {
        const small = document.createElement("div");
        small.className = "meta";
        small.textContent = meta;
        div.appendChild(small);
      }
      messages.appendChild(div);
      messages.scrollTop = messages.scrollHeight;
    }

    function setRecommendations(items) {
      recs.innerHTML = "";
      for (const item of items || []) {
        const li = document.createElement("li");
        const rank = document.createElement("span");
        rank.className = "rank";
        rank.textContent = item.rank;
        const title = document.createElement("div");
        title.className = "title";
        title.appendChild(rank);
        title.append(item.title || "Catalog product");
        const details = document.createElement("div");
        details.className = "details";
        details.textContent = [item.price, item.store, item.categories].filter(Boolean).join(" | ");
        const asin = document.createElement("div");
        asin.className = "asin";
        asin.textContent = item.parent_asin;
        li.append(title, details, asin);
        recs.appendChild(li);
      }
    }

    function setOfficialJson(data) {
      const official = {
        message: data.message,
        ask_attribute: data.ask_attribute,
        recommendations: data.recommendations || []
      };
      jsonOutput.textContent = JSON.stringify(official, null, 2);
    }

    async function postJson(url, body) {
      const response = await fetch(url, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(body || {})
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Request failed");
      return data;
    }

    async function reset() {
      const data = await postJson("/api/reset", {});
      sessionId = data.session_id;
      turn = 0;
      turnText.textContent = "0";
      messages.innerHTML = "";
      setRecommendations([]);
      jsonOutput.textContent = "{}";
      addMessage("New shopping session started. What are you looking for?", "agent", "demo profile loaded");
      input.focus();
    }

    document.getElementById("resetButton").addEventListener("click", reset);
    for (const button of document.querySelectorAll("[data-example]")) {
      button.addEventListener("click", () => {
        input.value = button.dataset.example;
        input.focus();
      });
    }
    document.getElementById("chatForm").addEventListener("submit", async (event) => {
      event.preventDefault();
      const text = input.value.trim();
      if (!text || turn >= 10) return;
      input.value = "";
      addMessage(text, "user");
      try {
        turn += 1;
        const data = await postJson("/api/message", {session_id: sessionId, user_message: text, turn});
        turnText.textContent = String(turn);
        addMessage(data.message, "agent", data.ask_attribute ? `asks for: ${data.ask_attribute}` : "");
        setRecommendations(data.recommendation_details || data.recommendations);
        setOfficialJson(data);
      } catch (error) {
        addMessage(error.message, "agent error");
      }
    });

    reset();
  </script>
</body>
</html>
"""


class DemoApp:
    def __init__(self, catalog_path: Path) -> None:
        self.agent = Agent(catalog_path)
        self.products = self._load_products(catalog_path)
        self.lock = threading.RLock()

    def _load_products(self, catalog_path: Path) -> dict[str, dict[str, object]]:
        products: dict[str, dict[str, object]] = {}
        with catalog_path.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                item = json.loads(line)
                parent_asin = str(item.get("parent_asin") or "")
                if parent_asin:
                    products[parent_asin] = item
        return products

    def _details(self, recommendations: list[dict[str, str]]) -> list[dict[str, object]]:
        output: list[dict[str, object]] = []
        for index, rec in enumerate(recommendations, start=1):
            parent_asin = rec.get("parent_asin", "")
            product = self.products.get(parent_asin, {})
            categories = product.get("categories")
            if isinstance(categories, list):
                categories = " / ".join(str(value) for value in categories[-3:])
            price = product.get("price")
            if isinstance(price, (int, float)):
                price_text = f"${price:.2f}"
            elif price:
                price_text = str(price)
            else:
                price_text = ""
            output.append(
                {
                    "rank": index,
                    "parent_asin": parent_asin,
                    "title": str(product.get("title") or ""),
                    "store": str(product.get("store") or ""),
                    "price": price_text,
                    "categories": str(categories or ""),
                }
            )
        return output

    def reset(self) -> dict[str, str]:
        session_id = str(uuid.uuid4())
        with self.lock:
            self.agent.reset(session_id, DEFAULT_PROFILE)
        return {"session_id": session_id}

    def message(self, payload: dict) -> dict:
        session_id = str(payload.get("session_id") or "")
        user_message = str(payload.get("user_message") or "")
        turn = payload.get("turn")
        if type(turn) is not int:
            raise ValueError("turn must be an integer")
        with self.lock:
            response = self.agent.respond(session_id, user_message, turn, 10)
        response["recommendation_details"] = self._details(response.get("recommendations", []))
        return response


def make_handler(app: DemoApp) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return

        def _send_json(self, status: int, data: dict) -> None:
            body = json.dumps(data).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            if urlparse(self.path).path != "/":
                self.send_error(404)
                return
            body = INDEX_HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:
            try:
                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(length) if length else b"{}"
                payload = json.loads(raw.decode("utf-8") or "{}")
                path = urlparse(self.path).path
                if path == "/api/reset":
                    self._send_json(200, app.reset())
                elif path == "/api/message":
                    self._send_json(200, app.message(payload))
                else:
                    self.send_error(404)
            except Exception as exc:
                self._send_json(400, {"error": str(exc)})

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the optional ShopSense local demo UI.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--catalog", default=str(ROOT / "data" / "catalog.jsonl"))
    args = parser.parse_args()

    catalog_path = Path(args.catalog)
    if not catalog_path.exists():
        raise SystemExit(f"Missing catalog file: {catalog_path}")

    server = ThreadingHTTPServer((args.host, args.port), make_handler(DemoApp(catalog_path)))
    print(f"ShopSense demo UI: http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
