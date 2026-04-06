# Cosplay — NVIDIA NIM Provider

The default seeded provider: NVIDIA NIM (`https://integrate.api.nvidia.com/v1`), OpenAI-compatible.

- Fixed id `37b74868-f817-45f6-9691-ae60885cd79b`; `api_key` is empty until the user adds one.
- Routing defaults point at Nemotron models ([[Cosplay-Setup-Flow]], [[Cosplay-Model-Routing]]).
- Without a key, every upstream request fails — a user-supplied key is required for the proxy to answer.

#cosplay #nim
