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
      background: #f5f7f8;
      color: #172026;
    }
    * { box-sizing: border-box; }
    body { margin: 0; min-height: 100vh; display: grid; grid-template-rows: auto 1fr; }
    header { padding: 18px 24px; background: #ffffff; border-bottom: 1px solid #d9e0e4; }
    h1 { margin: 0; font-size: 20px; letter-spacing: 0; }
    main { display: grid; grid-template-columns: minmax(0, 1fr) 360px; gap: 20px; padding: 20px; }
    .panel { background: #ffffff; border: 1px solid #d9e0e4; border-radius: 8px; min-width: 0; }
    .chat { display: grid; grid-template-rows: 1fr auto; min-height: calc(100vh - 100px); }
    #messages { padding: 16px; overflow: auto; }
    .msg { max-width: 760px; margin: 0 0 12px; padding: 12px 14px; border-radius: 8px; line-height: 1.45; }
    .user { margin-left: auto; background: #d7ece7; }
    .agent { background: #eef2f4; }
    form { display: flex; gap: 10px; padding: 14px; border-top: 1px solid #d9e0e4; }
    input { flex: 1; min-width: 0; padding: 12px; border: 1px solid #b8c4ca; border-radius: 6px; font-size: 15px; }
    button { border: 0; border-radius: 6px; padding: 0 16px; font-weight: 700; background: #111827; color: white; cursor: pointer; }
    button.secondary { background: #ec4e20; }
    aside { padding: 16px; align-self: start; }
    h2 { margin: 0 0 12px; font-size: 16px; }
    ol { margin: 0; padding-left: 22px; }
    li { margin-bottom: 10px; }
    code { background: #eef2f4; border-radius: 4px; padding: 2px 4px; }
    .meta { color: #60707a; font-size: 13px; margin-top: 6px; }
    .error { color: #9f1239; font-weight: 700; }
    @media (max-width: 860px) {
      main { grid-template-columns: 1fr; padding: 12px; }
      .chat { min-height: 70vh; }
    }
  </style>
</head>
<body>
  <header>
    <h1>ShopSense Shopping Copilot</h1>
  </header>
  <main>
    <section class="panel chat">
      <div id="messages"></div>
      <form id="chatForm">
        <input id="messageInput" autocomplete="off" placeholder="Tell it what you want, for example: I need black leather boots under $100">
        <button type="submit">Send</button>
        <button class="secondary" type="button" id="resetButton">Reset</button>
      </form>
    </section>
    <aside class="panel">
      <h2>Current Top 10</h2>
      <ol id="recommendations"></ol>
      <p class="meta">This demo calls <code>starter.agent.Agent</code>. Official scoring still uses <code>python3 -m evaluator.local_evaluator</code>.</p>
    </aside>
  </main>
  <script>
    let sessionId = null;
    let turn = 0;
    const messages = document.getElementById("messages");
    const recs = document.getElementById("recommendations");
    const input = document.getElementById("messageInput");

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
        li.textContent = item.parent_asin;
        recs.appendChild(li);
      }
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
      messages.innerHTML = "";
      setRecommendations([]);
      addMessage("New shopping session started. What are you looking for?", "agent");
      input.focus();
    }

    document.getElementById("resetButton").addEventListener("click", reset);
    document.getElementById("chatForm").addEventListener("submit", async (event) => {
      event.preventDefault();
      const text = input.value.trim();
      if (!text || turn >= 10) return;
      input.value = "";
      addMessage(text, "user");
      try {
        turn += 1;
        const data = await postJson("/api/message", {session_id: sessionId, user_message: text, turn});
        addMessage(data.message, "agent", data.ask_attribute ? `asks for: ${data.ask_attribute}` : "");
        setRecommendations(data.recommendations);
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
        self.lock = threading.RLock()

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
            return self.agent.respond(session_id, user_message, turn, 10)


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
