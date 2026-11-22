<div align="center">

# 🔮 Olivia

A tarot reader who lives on your computer. She is a woman of few words: she does not predict, and she does not decide for you.

Cards are drawn locally, memories stay on this machine, and only the reading step talks to a model.

[![CI](https://github.com/Him-Wang/tarot-counselor/actions/workflows/ci.yml/badge.svg)](https://github.com/Him-Wang/tarot-counselor/actions/workflows/ci.yml)
[![version](https://img.shields.io/badge/version-1.2.0-blue.svg)](CHANGELOG.md)
[![python](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![license](https://img.shields.io/badge/license-PolyForm%20NC%20%2B%20CC%20BY--NC--SA-green.svg)](LICENSE)

[Quick start](#quick-start) · [A full reading](#a-full-reading) · [Why trust her](#why-trust-her) · [Her hands](#her-hands) · [MCP](#mcp) · [Config](#config) · [Layout](#layout)

![Olivia demo: draw, ask, read](docs/media/demo.gif)

<sub>[Home](docs/media/home.png) · [Spreads](docs/media/spreads.png) · [Cards](docs/media/cards.png) · [Reading](docs/media/reading.png) · [Settings](docs/media/settings.png) · [Mobile](docs/media/mobile.png)</sub>

<sub>[中文版](README.md)</sub>

</div>

---

## What she is

- **A complete persona pack**: `prompts/` holds her personality, tone and an optional prophecy mode. Use it as a standing system prompt, a lazily loaded skill, or the person typing in the local web page.
- **An agent that acts**: nine tools (draw, look up a card, search knowledge, remember, take notes, crisis gate, reminders) are chosen by the model, not hard-coded into a flow.
- **A purely local consulting room**: 78 RWS card images, 39 spreads, meanings, memories and notes all live on your disk. Drawing a card does not even need an API key.

What she deliberately does not do: predict specific events, give medical / legal / financial advice, role-play a medium, or make life decisions for you. On acute crisis (self-harm, suicide, abuse) she steps out of the tarot role and gives helpline resources first — that gate lives on the server, before drawing, before the model, before writing memory.

---

## Quick start

### Windows: double-click install

Grab **`Olivia-setup.exe`** (about 11 MB) from the [latest Release](https://github.com/Him-Wang/tarot-counselor/releases/latest):

1. Choose an install folder (default `%LOCALAPPDATA%\Olivia`) and whether to start on boot
2. It creates a shortcut, starts the service in the background, opens <http://127.0.0.1:8765>
3. Open "Settings" and paste your key

Requires **Python 3 on PATH** (tick *Add Python to PATH* during install). If missing, the installer tells you and links the download. The server uses the standard library only — no pip install.

### From source: one line

```bash
cd agent && python server.py      # Python 3 standard library only
```

### Docker: one command

```bash
docker compose up -d              # open http://127.0.0.1:8765
```

The image is based on `python:3.12-slim` and still uses only the standard library. Data is mounted at `./agent/data`, so deleting the container does not erase her memory.

### Mobile: `Olivia-release.apk` from the same Release

A thin client that connects to the Olivia running on your computer (see [Mobile](#mobile)).

### Which model

| Backend | How to fill it in |
|---|---|
| **DeepSeek** (default) | Get a key at platform.deepseek.com; presets `deepseek-flash` (default, fast and cheap), `deepseek-v4-pro`, `deepseek-chat`; you can also type `deepseek-reasoner` |
| **Anthropic** | Native Messages API, `sk-ant-…`, model such as `claude-sonnet-4-5-20250929` |
| **Gemini** | Native GenerateContent API, model such as `gemini-2.5-flash` |
| **Ollama** | Run `ollama serve`, set `base_url` to `http://127.0.0.1:<port>/v1`, leave the key empty |
| Others | Pick protocol `auto` or `openai`; any OpenAI-compatible endpoint works |

All three protocols (OpenAI-compatible / Anthropic Messages / Gemini GenerateContent) run the same agentic loop and tool calls, and you can switch at any time in Settings. The key is only written to `agent/config.json`, which is gitignored and encrypted at rest.

---

## A full reading

**1. You say "draw".** She lists 39 spreads to tap: one card, three cards, Celtic Cross, Tree of Life, seven chakras, relationship, either/or, yes/no, four seasons… Each position shows what it asks about on hover. This step is fully local with zero API calls.

**2. She draws, but does not read yet.** 78 cards are drawn without replacement and laid out in the spread's traditional geometry, reversals rotated 180°. Then she asks one question: "What would you like to ask?" She does not speak before knowing what you want to know.

**3. You say what is actually on your mind.** Only then does she read this spread against this question. The order is **traditional meaning → position in the spread → your question → your situation**. When two or more cards are read together she also looks at element, numerical stage, majors vs minors, court cards and narrative arc (`knowledge/meanings/牌间关系.md`): perspectives, not formulas.

**4. You can interrupt her mid-reading.** Press "Stop" and she stops immediately. What was already said stays, ending with "generation stopped".

**5. Want another angle? Add one card.** Press "Add a card" and write why (e.g. "I want to see the part I am ignoring"). The added card is listed separately under "Added cards · a later perspective" without replacing the original, and the reason is logged to `agent/data/extras.jsonl`.

**6. Look, save, listen.** Double-tap any card for a large view (reversals are rotated upright so you can see them); press "Save this reading" to render the cards and her words into a 1080-wide PNG (browser download, or straight into `Pictures/Olivia` on mobile); press "Read aloud" to hear her (Web Speech in the browser, system TTS on Android).

**7. Every turn leaves a receipt.** Below each message: "tokens this turn: in x / out y". In Settings you can also set a daily budget: she warns as you approach it and falls back to offline composition when it is exceeded, so nothing is quietly burned. History is trimmed by message count and character budget, keeping long chats affordable.

**8. Not talking tomorrow is fine.** In the care panel, enable "Daily card": every day she draws one locally and writes it to the inbox — **no model call, works without a key**.

---

## Why trust her

**The cards are not made up on the spot.** The 78 card images are public-domain scans (`agent/cards/`, see `SOURCE.md`). Meanings stay within the Waite (RWS) system: core meaning and upright/reversed, plus visual symbolism and practical notes added per card, and court cards get both "a person" and "a side of yourself" perspectives. The writing is an original rewrite after looking at each card; the bibliography sits at the top of each file under `knowledge/meanings/`. **Cards are drawn without replacement**, and every draw gives a seed: the same seed and spread reproduce the same cards, so you can verify she is not cherry-picking.

**Time is real.** Every turn injects the current date and time into her context, so suggestions like "tonight before bed" or "tomorrow at seven" rest on actual time rather than years from training data.

**She does not fake it when words fail.** With no key or an unreachable model, `agent/offline.py` composes the cards **you already drew** into text using position, traditional meaning and the reproduction seed, clearly labelled **【offline composition】not an AI reading**. Drawing, viewing and reading positions never needed the network. She will not invent a reading just to look useful.

> Meta-rule: **the cards do not speak; the person does.** Offline, that voice is traditional meaning — not a pretend AI.

---

## Her hands

A real agentic loop: the model decides whom to call, and the UI shows each step with a ⚙ badge.

| Tool | What it does |
|---|---|
| `draw_cards` | Draw locally by spread (no replacement, seeded) |
| `search_knowledge` | Search reading method, card relations, empathic listening, ethics and referral |
| `lookup_card` | Look up one card's traditional RWS meaning (upright / reversed) instead of hoping search finds it |
| `save_memory` | Remember preferences, boundaries and explicit "please remember" |
| `recall_memory` | Recall profile / facts / draw history, or delete a wrong entry |
| `save_note` / `search_notes` | Archive and retrieve your notes |
| `crisis_check` | Crisis backstop (`safety.py` on the server is the authoritative gate) |
| `schedule_reminder` | One-off / daily / weekly / every-N-minutes reminders |

So she understands "remind me tomorrow at eight", "what did I ask last time", "what does Death mean" — not just card talk.

**Scheduling and watching** (`scheduler.py` / `watchers.py`, managed in the care panel): at the appointed time she writes a care note to the inbox and fires a Windows notification; quiet hours default to 22:00–08:00, the master switch is off by default, and everything runs locally. Watching supports web / RSS / JSON / weather sources with contains, regex, numeric threshold, changed and new-item rules. **The first run only establishes a baseline**, so it does not cry wolf; a dead source is logged, not shouted about.

**Vision** (optional): give it any OpenAI-compatible VLM key and she passes an objective Chinese description to the main model as text context. The main model stays text-only and does not pretend to see.

---

## Her memory

`agent/memory.py` keeps four layers: **stable profile**, **facts** (preferences and boundaries), **conversations**, **draw history**, injected by relevance each turn so you do not repeat yourself. She can also **actively recall** (`recall_memory`) and **actively forget** (delete one entry or clear recent ones).

Two more books: `agent/plugin_kb.py` is your **note library** (`kb.db`, archive, search, export Markdown), and the session book is **conversation history stored in the browser** (name it, revisit it, deep link `#/chat/<id>`; crisis conversations keep only a placeholder, never the transcript).

Moving house or machines? Settings can **export / import** the whole thing as JSON: profile, facts, draws, conversations, notes, scheduled tasks and watchers, **without the key**. Databases use WAL and carry a schema version, migrating automatically on upgrade, so changing versions does not strand old memories.

---

## Config

`agent/config.json` (copy from `config.example.json`):

```json
{
  "backend": "deepseek-flash",
  "base_url": "https://api.deepseek.com/v1",
  "api_key": "",
  "model": "deepseek-flash",
  "temperature": 0.8,
  "timeout": 120
}
```

Environment variables: `AGENT_PORT` (default `8765`), `AGENT_HOST` (default `127.0.0.1`).

**LAN access needs a pairing code.** Once `AGENT_HOST` is not a loopback address, startup prints an 8-character pairing code (also stored in `agent/data/access_token`; set `OLIVIA_TOKEN` to choose your own). Another device must enter it once, then an HttpOnly cookie remembers it; scripts may send an `X-Olivia-Token` header. Eight wrong codes from the same IP within ten minutes are temporarily blocked. On your own machine (the default `127.0.0.1`) there is no such step.

All data lives in `agent/data/`: `memory.db` (profile / facts / conversations / draws), `kb.db` (notes), `scheduler.db` (tasks and inbox), `watchers.db` (watchers and baselines), `extras.jsonl` (added-card log). Delete those files and she forgets; delete the folder and it is gone.

---

## Layout

```
.
├── prompts/                     # persona / tone / prophecy mode (Chinese + English)
├── skills/tarot-counselor/SKILL.md  # lazily loaded skill format
├── knowledge/                   # professional material, entry point INDEX.md
│   ├── meanings/                # majors + four suits + reading method + card relations
│   ├── readings/                # method: reading flow, single-card depth, reversals, court cards
│   ├── spreads/牌阵速查.md
│   ├── skills/共情式倾听.md
│   └── ethics/危机与转介.md
├── agent/
│   ├── server.py                # HTTP server, API, two-phase draw and reading orchestration
│   ├── index.html               # single-page UI: chat / cards / lightbox / share image / care
│   ├── provider.py  llm.py      # three-protocol streaming + usage normalisation
│   ├── tools.py                 # definitions and execution of 9 tools
│   ├── spreads.py               # single source of truth for 39 spreads
│   ├── safety.py  offline.py    # crisis gate / offline composition fallback
│   ├── memory.py  knowledge.py  # layered memory / knowledge retrieval
│   ├── scheduler.py  watchers.py # scheduled care (incl. daily card) / conditional watching
│   ├── plugin_kb.py  plugin_vision.py
│   ├── cards/                   # 78 RWS card images
│   ├── toast.ps1                # Windows desktop notification
│   └── data/                    # the .db and .jsonl files above (gitignored)
├── android/                     # mobile: WebView thin client
│   ├── build.ps1                # aapt2 + d8 + apksigner, one command to a signed APK
│   ├── src/com/olivia/tarot/    # WebView / TTS bridge / gallery download / change address
│   ├── res/                     # icons and strings
│   └── tools/merge_dex.py       # merge classes.dex into the base APK
├── installer/                   # Windows single-file installer
│   ├── build.py                 # python installer/build.py to rebuild
│   ├── Setup.cs  Launcher.cs    # compiled with csc.exe, no VS / dotnet SDK needed
│   └── dist/                    # artifacts (gitignored)
├── tests/                       # white-box + black-box self-checks
└── README.en.md
```

---

## Self-check

Standard library only, **never touches a real model API**, runs without a key:

```bash
python tests/test_whitebox.py     # 120 checks: source structure, pure functions, protocol conversion, spread integrity, pairing/crypto/migrations/MCP
python tests/test_blackbox.py     # 57 checks: starts a separate server and makes real HTTP requests (incl. LAN pairing)
```

The black box verifies: crisis requests do not draw, do not call tools, and give helpline resources first; draws use no replacement; without a key the reading turn is marked offline and says it is not an AI reading; crisis residue in history does not re-alert; deep links and the share button exist on the home page; card images are reachable and traversal is rejected; with `AGENT_HOST=0.0.0.0` unpaired requests get 401, wrong codes are throttled, and the cookie works after pairing. It starts its own server on `AGENT_PORT` and does not disturb your running instance.

---

## Mobile

`android/` is a **thin WebView client that reimplements no logic** — meanings, memory and schedules exist once, and the phone is just a window.

- **Which machine**: `http://<computer-IP>:8765`; if it cannot connect it shows an error page where you can edit the address (defaults to the emulator address `10.0.2.2:8765`)
- **What works on the phone**: draw / read / add a card / stop / double-tap to zoom / save a reading to the gallery / system TTS / care panel daily card
- **First real-device connection**: on the computer run `AGENT_HOST=0.0.0.0 python agent/server.py`; phone and computer on the same Wi-Fi (cleartext HTTP is already allowed for Android 9+ in the app)

Build it yourself, no Android Studio or Gradle:

```powershell
# requires JDK 17 + Android SDK (platform 34, build-tools 34.0.0)
powershell -NoProfile -ExecutionPolicy Bypass -File android\build.ps1
# artifact: android\build\Olivia-release.apk
```

Signing reads `android\keystore\olivia-release.jks` by default (alias `olivia`, sample password `olivia-tarot`; change it for your own use), or pass `-Keystore/-StorePass/-KeyAlias`. Details in [`android/README.md`](android/README.md).

---

## Use her elsewhere

- **As a prompt**: drop `prompts/persona.zh.md` (optionally `tone.zh.md`) into ChatGPT custom instructions / a Claude Project / your own agent's system prompt
- **As a skill**: put the whole `skills/tarot-counselor/` folder into your skills directory (Claude Code `~/.claude/skills/`, DSH `~/.dsh/skills/`). She is an ordinary assistant most of the time and loads only when you ask for a reading or want to talk

---

## MCP

`agent/mcp_server.py` is a zero-dependency MCP stdio server that exposes draw, lookup, search and list-spreads to other clients. It does not go online and does not touch your memory or key.

```json
{
  "mcpServers": {
    "olivia-tarot": {
      "command": "python",
      "args": ["C:/path/to/tarot-counselor/agent/mcp_server.py"]
    }
  }
}
```

| Tool | Returns |
|---|---|
| `draw_cards` | Local draw by spread: positions, orientation, traditional meanings, layout coordinates and seed |
| `lookup_card` | One card's RWS meaning (upright / reversed / both) |
| `search_knowledge` | Reading method, card relations, empathic listening, ethics and referral |
| `list_spreads` | Names and position notes of the 39 spreads |

Self-test: `python agent/mcp_server.py --selftest`.

---

## Privacy

Conversations, memories, notes and keys stay on this machine: nothing is uploaded, no middle server. The installer excludes `config.json`, `agent/data/*.db` and caches, then cleans up once more after install. To make her forget everything: delete `agent/data/`; to erase completely: delete the install folder.

---

## License

By default: **play with it however you like, just do not make money from it.** Two licenses:

| Content | License | In one line |
|---|---|---|
| `agent/` `android/` `installer/` `tests/` (program code) | [PolyForm Noncommercial 1.0.0](LICENSE) | Code: self-use and tinkering allowed, commercial use not |
| `prompts/` `skills/` `knowledge/` (persona, tone, meanings, spreads, method) | [CC BY-NC-SA 4.0](LICENSE-CONTENT) | Text and persona: attribution, non-commercial, share-alike |
| `agent/cards/` 78 card images | Public domain (1909 RWS) | No permission needed; see `agent/cards/SOURCE.md` |

Allowed: download, install on your own computer or phone, read the source, tinker, show friends, share non-commercially (with `LICENSE` and the `Required Notice` attribution line).

Not allowed: commercial use — selling it, including it in a paid product or service, using it as a production tool at work, or repackaging it under another name and publishing it as your own product.

**Need commercial use?** A separate commercial license is available; see [`COMMERCIAL.md`](COMMERCIAL.md). Individuals, study, research and non-profit use need no contact — just use it.

The "Olivia / 奥莉薇娅" name and persona belong to the author; offering her under another brand requires a separate contract.
