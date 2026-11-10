import argparse
import http.cookiejar
import json
import os
import random
import time
import urllib.error
import urllib.request
from datetime import datetime

BASE_URL = os.environ.get("PXG_API_URL", "https://access-main.loginto.me").rstrip("/")
API_KEY = os.environ.get("PXG_API_KEY", "f87d8265e02127171cc1d0a6e333275c595e0c55")

CATEGORIES = ["level", "achievementpoints", "pokelogpoints",
              "fishing", "officialwins", "likes", "catches"]

# "" is Global. The word itself returns 404.
WORLDS = ["", "wind", "aurora", "ocean", "emerald", "gold", "cosmic",
          "steel", "omega", "lunar", "rainbow", "magma", "obsidian", "snow"]

TIMEOUT = 30
RETRIES = 3


class Client:
    def __init__(self):
        self.headers = {
            "Origin": BASE_URL, "Referer": BASE_URL, "User": BASE_URL,
            "User-Agent": "Luna (PokeXGames 200; Windows x86_64)",
            "X-Requested-With": API_KEY,
            "Content-Type": "application/json;charset=utf-8",
            "Accept": "application/json, text/plain, */*",
            "Connection": "keep-alive",
        }
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def get(self, path, payload=None):
        body = json.dumps(payload).encode() if payload is not None else None
        method = "POST" if body is not None else "GET"
        for attempt in range(RETRIES):
            request = urllib.request.Request(
                BASE_URL + path, data=body, headers=self.headers, method=method)
            try:
                with self.opener.open(request, timeout=TIMEOUT) as response:
                    return json.loads(response.read().decode())
            except urllib.error.HTTPError as exc:
                # A 4xx other than 429 will fail identically next time.
                if exc.code != 429 and exc.code < 500:
                    raise RuntimeError(f"{path} -> HTTP {exc.code}") from exc
                error = exc
            except (urllib.error.URLError, OSError) as exc:
                error = exc
            if attempt < RETRIES - 1:
                time.sleep(2 ** (attempt + 1))
        reason = f"HTTP {error.code}" if isinstance(error, urllib.error.HTTPError) else error
        raise RuntimeError(f"{path} -> {reason}") from error


def parse_worlds(spec):
    if not spec:
        return WORLDS
    picked = ["" if w.strip().lower() == "global" else w.strip().lower()
              for w in spec.split(",") if w.strip()]
    unknown = [w for w in picked if w not in WORLDS]
    if unknown:
        valid = ", ".join(w or "Global" for w in WORLDS)
        raise SystemExit(f"unknown world(s): {', '.join(unknown)}\nvalid: {valid}")
    return picked or WORLDS


def scrape(client, worlds, with_pokemons):
    rankings = []
    for category in CATEGORIES:
        for world in worlds:
            print(f"  {category:<20} {world or 'Global'}")
            rankings.append({
                "category": category,
                "world": world or "Global",
                "data": client.get(f"/api/community/highscores/{category}/{world}"),
            })
            time.sleep(random.uniform(0.8, 1.6))

    pokemons = []
    if with_pokemons:
        for world in worlds:
            print(f"  {'pokemons':<20} {world or 'Global'}")
            pokemons.append({
                "world": world or "Global",
                "data": client.get(f"/api/community/pokemons/{world}"),
            })
            time.sleep(random.uniform(0.8, 1.6))
    return rankings, pokemons


def main():
    parser = argparse.ArgumentParser(description="PokeXGames community scraper")
    parser.add_argument("--out", help="output JSON path")
    parser.add_argument("--worlds", help="comma-separated subset, e.g. wind,ocean")
    parser.add_argument("--skip-pokemons", action="store_true", help="rankings only")
    args = parser.parse_args()

    email = os.environ.get("PXG_EMAIL")
    password = os.environ.get("PXG_PASSWORD")
    if not (email and password):
        raise SystemExit("set PXG_EMAIL and PXG_PASSWORD")

    worlds = parse_worlds(args.worlds)

    client = Client()
    print(f"logging in as {email} @ {BASE_URL}")
    try:
        client.get("/api/login", {"username": email, "password": password})
        client.get("/api/loggedin")   # 200 here means the cookie actually took
    except RuntimeError as exc:
        raise SystemExit(f"login failed: {exc}")

    rankings, pokemons = scrape(client, worlds, not args.skip_pokemons)

    out = args.out or datetime.now().strftime("pxg-%Y%m%d-%H%M%S.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump({"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                   "rankings": rankings, "pokemons": pokemons},
                  fh, ensure_ascii=False, indent=2)

    print(f"\n{out}: {len(rankings)} rankings, {len(pokemons)} pokemons")


if __name__ == "__main__":
    main()
