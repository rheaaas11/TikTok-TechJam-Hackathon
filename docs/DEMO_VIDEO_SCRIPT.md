# Demo Video Script

Target length: 2 to 3 minutes.

## Before Recording

From the repo root, run:

```bash
python3 demo/server.py
```

Open:

```text
http://127.0.0.1:8000
```

Keep a terminal ready with:

```bash
python3 -m evaluator.local_evaluator
```

## Recording Flow

1. Show the GitHub repo page.
   - Say: "This is our public repository for ShopSense, our TikTok TechJam conversational shopping copilot."

2. Show the README.
   - Say: "The official entry point is `starter.agent.Agent`. The project includes setup instructions, reproducible evaluator commands, final results, team contributions, and limitations."

3. Show the local demo UI.
   - Say: "This UI is optional. The official scorer still uses the Python agent directly, but the UI demonstrates the same agent end-to-end."

4. Type a query:

```text
I need black leather boots under $100
```

5. Point out:
   - the follow-up question;
   - the `ask_attribute`;
   - the Top 10 recommendation list;
   - the official response JSON.

6. Type an intent change:

```text
Actually switch to a red formal dress instead
```

7. Say: "The agent updates the conversation state and reranks recommendations for the new intent."

8. Show the evaluator command and result:

```bash
python3 -m evaluator.local_evaluator
```

9. Say: "On the public 200-session evaluator, our result is Hit Rate@10 0.98 and TechnicalScore 0.857921. The agent is offline and uses zero API tokens."

## Do Not Show

- API keys
- private data
- personal browser tabs
- TikTok logos or copyrighted media
- the large local `data/catalog.jsonl` file contents

## YouTube Note

Upload the video to YouTube as public or unlisted if Devpost accepts unlisted. Put the YouTube link into the Devpost project description.
