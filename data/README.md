# Competition Data

## `public_set.jsonl`

Contains 200 labeled development sessions: 80 Buying, 80 Browsing, 30 Intent Override, and 10 Boundary sessions.

Each session contains a safe aggregate `user_profile` and public labels for local development. Direct user identifiers, timestamps, free-text reviews, raw purchase history, hidden intent cards, and simulator-policy internals are not shipped in this participant file.

## `catalog.jsonl`

Download `catalog.jsonl.gz` from:

```text
https://github.com/TechJam2026/techjam-conversational-search/releases/download/participant-kit/catalog.jsonl.gz
```

Place the decompressed file at `data/catalog.jsonl`. Expected row count: 50,000.

Compressed SHA256: `07FD142631FD6B03E2B4D09988C3EB7D53720E9D57010C79DB48EEAADA50A8F8`

Decompressed SHA256: `DA979B05A68AF864CB0DCF9EE6A81C010C7E66A57978AD286C7A2E005FC69A67`

Never place API keys, private evaluation data, or participant outputs in this directory.
