# PokeXGames — Community API & Scraper Documentation

The game talks to a JSON web API for account and community data, on the same host the client uses. As of **10/11/2026** it serves 7 highscore categories across 14 worlds, plus a Pokémon snapshot per world. `pxgscraper.py` collects all of it into one file.

## 1. The Scraper

`pxgscraper.py` is a single file of 144 lines and imports nothing outside the standard library. No config module, no database, no install step. It logs in once, walks every category and world, and writes one JSON file.

```
set PXG_EMAIL=you@example.com
set PXG_PASSWORD=yourpassword
python pxgscraper.py
```

| Flag | Effect |
|------|--------|
| `--out PATH` | Output file (default `pxg-<timestamp>.json`) |
| `--worlds wind,ocean` | Subset of worlds; `Global` also accepted |
| `--skip-pokemons` | Rankings only (98 requests instead of 112) |

`PXG_API_URL` and `PXG_API_KEY` can be overridden from the environment.

Requests are spaced 0.8–1.6 s apart at random, which puts a full run near four minutes. Firing them back to back gets the account rate-limited, and the retries then cost more time than the delay would have. Only 429, 5xx, timeouts and connection errors are retried. Every other 4xx fails on the first attempt, so a wrong password costs one request rather than three.

## 2. The APIs

| Method | Path | Returns |
|--------|------|---------|
| `POST` | `/api/login` | Sets the session cookie. Body: `{"username", "password"}` |
| `GET` | `/api/loggedin` | Confirms the cookie took. A 200 on login alone does not |
| `GET` | `/api/community/highscores/{category}/{world}` | Exactly **100** entries |
| `GET` | `/api/community/pokemons/{world}` | 907–1,049 entries |

Two hosts serve the same data with the same credentials:

```
WEBSITE_URL           = https://access-main.loginto.me
INTERNAL_WEBSITE_URL  = https://access-secondary.loginto.me
```

**Categories (7):** `level`, `achievementpoints`, `pokelogpoints`, `fishing`, `officialwins`, `likes`, `catches`

**Worlds (14):** Global, `wind`, `aurora`, `ocean`, `emerald`, `gold`, `cosmic`, `steel`, `omega`, `lunar`, `rainbow`, `magma`, `obsidian`, `snow`

Global is not a world name — it is the empty one. Its URL therefore ends in a trailing slash: `/api/community/highscores/level/`. Both `global` and `Global` return 404. The scraper rewrites `--worlds global` to the empty string.

## 3. The X Key

```
f87d8265e02127171cc1d0a6e333275c595e0c55
```

Sent as `X-Requested-With`. It does not change between sessions or between the two hosts, which is what makes it safe to keep in a secrets store. It is not in `pxgme.exe` at all — the C++ layer receives it as an argument and the string comes from Lua, in `assets/modules/gamelib/gameweb.klua`.

Static extraction is where this goes wrong. The constant pool holds no standalone 40-character hex string. The value only appears fused into `"onSelectIp-f87d8265e02127171cc1d0a6e333275c595e0c55"`. LuaJIT folds `"onSelectIp-" .. KEY` at compile time, so a scan for hex constants sees an event name and skips past it. It has to be read at runtime.

The key changes with the build, and the server compares it exactly rather than checking its shape. 40 zeroes, 40 `a`s, a 10-character prefix, and the correct key with one extra character all return **400**. Leaving the header off also returns 400. Credentials are checked separately, so the two failures stay distinguishable:

| Status | Meaning |
|-------:|---------|
| `400` | `X-Requested-With` wrong, malformed, or missing |
| `401` | Key accepted, credentials wrong |
| `200` | Both good |

## 4. The User Agent

```
Luna (PokeXGames 200; Windows x86_64)
```

Assembled from the format string `Luna (%s %s; %s %s)` at `0x140fd09b6`:

| Slot | Value | Source |
|------|-------|--------|
| App | `PokeXGames` | app struct `+0x18` |
| Build | `200` | app struct `+0x58`; also `-> Build: 200` in the client log |
| OS | `Windows` | hardcoded in `FUN_14045b770` (falls back to `Android`) |
| Arch | `x86_64` | hardcoded in `FUN_14045ae60` |

There is one cross-reference, in `FUN_1403f2470`. The formatter at `RVA 0xB8E050` is shared with the console banner `%s - %s (%s %s)`, so a hook has to filter on the `Luna (` literal or it will report both.

## 5. The Client

`pxgme.exe` builds its web headers in Lua rather than C++. `gameweb.klua` calls `setRequestHeaderField` on a session from `g_gameWeb:newSession`. Header names are literals in the bytecode; the values are variables resolved at call time.

Captured from a running client:

| Header | Value |
|--------|-------|
| `Origin` / `Referer` / `User` | `base_url` — all three echo the API host |
| `User-Agent` | `Luna (PokeXGames 200; Windows x86_64)` |
| `X-Requested-With` | the build key from section 3 |
| `Content-Type` | `application/json;charset=utf-8` |
| `Accept` | `application/json, text/plain, */*` |
| `Connection` | `keep-alive` |

The three headers that repeat the host have to change together if the client is pointed at the secondary server. All of it came from three hooks in `pxgme.exe` under Frida:

```
0xB8E050   shared sprintf-style formatter   -> User-Agent
0x3F2470   HTTP header setup (C++)          -> header block
0xAEB410   setRequestHeaderField (Lua)      -> key/value pairs
```

Both arguments to `0xAEB410` are `std::string` objects, not `char*`. Under libstdc++ the data pointer sits at `+0` and the length at `+8`; reading them as C strings returns nothing usable.

Hooking `ws2_32!send` does not help — the API is HTTPS, so what reaches the socket is already ciphertext.

## 6. What It Returns

One JSON file:

```
{
  "timestamp": "2026-11-10 10:49:51",
  "rankings": [{"category": "level", "world": "Global", "data": [...]}],
  "pokemons": [{"world": "Global", "data": [...]}]
}
```

A full run on 10/11/2026 wrote 3.7 MB:

| Block | Entries | Records | Notes |
|-------|--------:|--------:|-------|
| `rankings` | 98 | 9,800 | 7 categories × 14 worlds, 100 rows each |
| `pokemons` | 14 | 14,371 | one per world, 907–1,049 rows |
| **Total** | **112** | **24,171** | |

Highscores are capped at 100 rows by the server, for every category and every world, so 9,800 is the most that block can ever hold. Two sample rows:

```
{"id": 7361377, "avatar": "quest35", "value": 621, "world": "obsidian", "clan": "raibolt", "name": "I Monstro I"}

{"id": 1, "name": "bulbasaur", "value": 71101, "shiny": 0}
```

Summing the 13 individual worlds reproduces the `Global` Pokémon snapshot exactly, with no mismatches across 1,049 entries. A run that reaches the end has not dropped anything.
