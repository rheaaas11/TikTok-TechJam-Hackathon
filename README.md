# ShopSense

ShopSense is our TikTok TechJam 2026 Shopping Copilot project.

Our goal is to build a shopping assistant that understands a user's conversation, creates a Product DNA profile, searches the product catalog, and returns the best Top 10 recommendations for the official evaluator.

Team:
- Shayna: Product DNA, conversation state, constraints, useful questions
- Leon: catalog search, filtering, ranking, Top 10 recommendations
- Rhea: integration, official agent contract, evaluator, README, final submission










# Competition Data

## `public_set.jsonl`

Contains 200 labeled development sessions: 80 Buying, 80 Browsing, 30 Intent Override, and 10 Boundary sessions.

Each session contains a safe aggregate `user_profile` and public labels for local development. Direct user identifiers, timestamps, free-text reviews, raw purchase history, hidden intent cards, and simulator-policy internals are not shipped in this participant file.

## `catalog.jsonl`

Download `catalog.jsonl.gz` from the GitHub Release and decompress it as `catalog.jsonl` in this directory. Expected row count: 50,000.

Never place API keys, private evaluation data, or participant outputs in this directory.
