# Subbrain: OpenClaw Journalism Agent — Deployment Walkthrough

## Architecture

```
User (Discord DM / Server @subbrain)
    ↓
Subbrain PC (10.170.75.85)
├── OpenClaw Gateway (systemd)
├── Main Agent (SOUL.md + IDENTITY.md)
├── 37 Registered Specialist Agents
└── Obsidian Vault (/root/.openclaw/vault/)
    ↓ LLM API
L40S Server (171.226.10.121)
├── nginx-gateway :8000  (Docker, web-network)
│   └── /llm/ → gemma_4_moe:8000 (Docker DNS)
│   └── /     → elderly :8001 (host)
│   └── /voice/ → kids :8002 (host) 
│   └── /api/lkg/ → lkg :8003 (host)
└── gemma_4_moe (vLLM, web-network + gemma_default)
```

## 1. Gemma 4 26B NVFP4 (L40S Server)

| Parameter | Value |
|---|---|
| Image | `vllm-gemma4:latest` (custom, transformers 5.5.3) |
| Model | `/model` served as `gemma-4` |
| Quantization | **NVFP4** (`--quantization modelopt`) |
| Context Window | **32768** tokens |
| GPU Memory | 75% utilization |
| KV Cache | FP8 (`--kv-cache-dtype fp8`) |
| API Key | `gemma4-openclaw-2026` |
| Container | `gemma_4_moe` on `gemma_default` + `web-network` |
| Vision | ✅ (base64 images) |

## 2. Nginx Gateway (L40S Server)

**Location:** `/home/namnx/nginx/`  
**Container:** `nginx-gateway` on `web-network`, port 8000  
**Replaces:** CloudPTalk nginx (stopped)

Routes:
- `/llm/` → `gemma_4_moe:8000` (Docker DNS, flat routing)
- `/` → `host.docker.internal:8001` (Elderly)
- `/voice/` → `host.docker.internal:8002` (Kids)
- `/api/lkg/` → `host.docker.internal:8003` (Legal KG)

## 3. OpenClaw (Subbrain PC)

| Component | Detail |
|---|---|
| Base URL | `http://171.226.10.121:8000/llm/v1` |
| Model | `gemma-4` (32K context, 8K max tokens) |
| Gateway | `openclaw-gateway.service` (systemd, enabled) |
| Discord | `@subbrain` bot, DM works ✅ |
| Server mention | Needs `guilds` config with server ID |
| Agent actions | `auto-approve` |
| SOUL.md | 171 lines — vault structure, templates, routing |

## 4. Agent System

- **184 agent workspaces** converted from `agency-agents`
- **37 registered** with OpenClaw CLI
- Main agent routes via SOUL.md routing table
- Agent tiers: Core / Specialist / Utility / Parked

## 5. Obsidian Vault (`/root/.openclaw/vault/`)

Structure: `00 Inbox` → `07 Sessions` → `99 Archive`  
5 automation scripts on cron (sync registry, capture sessions, promote memory, refresh open loops, daily dashboard).

## Verification

```bash
# Test LLM via nginx
curl -s -X POST http://171.226.10.121:8000/llm/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer gemma4-openclaw-2026' \
  -d '{"model":"gemma-4","messages":[{"role":"user","content":"hello"}],"max_tokens":10}'

# OpenClaw status (on subbrain)
openclaw channels status --probe
openclaw agents list | head -10
```

## TODO
- [ ] Add Discord server guild ID to enable @mention in channels
- [ ] Change subbrain password from `1`
- [ ] Configure web search tool (Tavily/DuckDuckGo)
- [ ] Register remaining agents (37/184)
