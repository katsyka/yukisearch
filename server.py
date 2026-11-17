#!/usr/bin/env python3
"""Yuki Search backend: Brave Search proxy + Gemini overview (SSE). Stdlib only."""
import json, os, re, time, html, threading, urllib.request, urllib.parse
import yukiindex
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

ROOT = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(ROOT, "static")


def load_env(path):
    try:
        for line in open(path):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"'))
    except FileNotFoundError:
        pass


load_env(os.path.join(ROOT, ".env"))
BRAVE_KEY = os.environ.get("BRAVE_API_KEY", "")
TAVILY_KEY = os.environ.get("TAVILY_API_KEY", "")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
MODELS = os.environ.get("GEMINI_MODELS", "gemini-3.5-flash-lite,gemini-3.5-flash,gemini-3.1-flash-lite").split(",")
PORT = int(os.environ.get("PORT", "6850"))
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"

# Cache on disk (survives restarts): each paid search is bought once and reused.
import sqlite3
DAY = 24 * 3600
TTL = {"web": 7 * DAY, "images": 7 * DAY, "videos": 7 * DAY, "news": 3 * 3600, "sug": DAY, "ov": 7 * DAY,
       "place": 30 * DAY, "ent": 30 * DAY, "music": 3600}
LOCK = threading.Lock()
DB = sqlite3.connect(os.path.join(ROOT, "cache.db"), check_same_thread=False, isolation_level=None)
DB.execute("PRAGMA journal_mode=WAL")
DB.execute("CREATE TABLE IF NOT EXISTS c (k TEXT PRIMARY KEY, exp REAL, v TEXT)")
_sets = 0


def _key(k):
    return json.dumps(k, ensure_ascii=False)


def cache_get(k):
    with LOCK:
        row = DB.execute("SELECT exp, v FROM c WHERE k=?", (_key(k),)).fetchone()
    if row and row[0] > time.time():
        return json.loads(row[1])


def cache_set(k, val, ttl=None):
    global _sets
    ttl = ttl or TTL.get(k[0], DAY)
    with LOCK:
        DB.execute("INSERT OR REPLACE INTO c VALUES (?,?,?)", (_key(k), time.time() + ttl, json.dumps(val, ensure_ascii=False)))
        _sets += 1
        if _sets % 500 == 0:
            DB.execute("DELETE FROM c WHERE exp < ?", (time.time(),))


def http_json(url, headers=None, data=None, timeout=12):
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            import gzip
            raw = gzip.decompress(raw)
        return json.loads(raw)


def strip_tags(s):
    return html.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()


# ---------- Brave ----------
BRAVE = "https://api.search.brave.com/res/v1/"


def brave(kind, q, extra):
    params = {"q": q, **extra}
    url = BRAVE + kind + "/search?" + urllib.parse.urlencode(params)
    return http_json(url, {"X-Subscription-Token": BRAVE_KEY, "Accept": "application/json",
                           "Accept-Encoding": "gzip"})


def norm_web(d):
    out = {"results": [], "news": [], "videos": [], "infobox": None}
    for r in (d.get("web") or {}).get("results", []):
        out["results"].append({
            "title": strip_tags(r.get("title")), "url": r.get("url"),
            "desc": strip_tags(r.get("description")),
            "extra": [strip_tags(x) for x in (r.get("extra_snippets") or [])][:3],
            "site": (r.get("profile") or {}).get("name") or urllib.parse.urlparse(r.get("url", "")).netloc,
            "icon": (r.get("meta_url") or {}).get("favicon"),
            "age": r.get("age"),
        })
    for r in (d.get("news") or {}).get("results", [])[:4]:
        out["news"].append({"title": strip_tags(r.get("title")), "url": r.get("url"),
                            "site": (r.get("meta_url") or {}).get("hostname"), "age": r.get("age"),
                            "thumb": (r.get("thumbnail") or {}).get("src")})
    for r in (d.get("videos") or {}).get("results", [])[:4]:
        out["videos"].append({"title": strip_tags(r.get("title")), "url": r.get("url"),
                              "site": (r.get("meta_url") or {}).get("hostname"), "age": r.get("age"),
                              "thumb": (r.get("thumbnail") or {}).get("src")})
    ib = ((d.get("infobox") or {}).get("results") or [None])[0]
    if ib:
        out["infobox"] = {"title": ib.get("title"), "desc": strip_tags(ib.get("long_desc") or ib.get("description")),
                          "url": ib.get("url"), "thumb": (ib.get("thumbnail") or {}).get("src")}
    return out


# ---------- Bing HTML fallback (no Brave key yet) ----------
def bing_url(h):
    m = re.search(r"[?&]u=a1([^&]+)", h)
    if m:
        import base64
        b = m.group(1)
        try:
            return base64.urlsafe_b64decode(b + "=" * (-len(b) % 4)).decode()
        except Exception:
            pass
    return h


def scrape(q, offset=0, lang=""):
    url = "https://www.bing.com/search?" + urllib.parse.urlencode(
        {"q": q, "first": offset * 10 + 1, "setlang": lang or "en"})
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": (lang or "en") + ",en;q=0.8"})
    page = urllib.request.urlopen(req, timeout=12).read().decode("utf-8", "replace")
    out = {"results": [], "news": [], "videos": [], "infobox": None}
    for b in page.split('class="b_algo"')[1:]:
        b = re.sub(r"<link[^>]+>|<style.*?</style>|<script.*?</script>", "", b, flags=re.S)
        m = re.search(r'<h2[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', b, re.S)
        if not m:
            continue
        href = bing_url(html.unescape(m.group(1)))
        if not href.startswith("http"):
            continue
        s = re.search(r'<p[^>]*>(.*?)</p>', b, re.S)
        desc = strip_tags(re.sub(r'<span class="news_dt">.*?</span>', "", s.group(1))) if s else ""
        desc = desc.lstrip("\u00b7 \u00a0")
        out["results"].append({"title": strip_tags(m.group(2)), "url": href, "desc": desc, "extra": [],
                               "site": urllib.parse.urlparse(href).netloc.replace("www.", ""),
                               "icon": None, "age": None})
    return out


# ---------- Tavily ----------
def tavily(q, **kw):
    body = json.dumps({"query": q, "search_depth": "basic", "include_favicon": True, **kw}).encode()
    return http_json("https://api.tavily.com/search",
                     {"Authorization": "Bearer " + TAVILY_KEY, "Content-Type": "application/json"},
                     data=body, timeout=20)


def clip(s, n):
    s = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", s or "")
    s = re.sub(r"(^|\s)#{1,6}\s+|[*_`]{1,3}(?=\S)|(?<=\S)[*_`]{1,3}|^\s*[-*]\s+", " ", s, flags=re.M)
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= n else s[:n].rsplit(" ", 1)[0] + " …"


def yt_thumb(u):
    m = re.search(r"(?:v=|youtu\.be/|shorts/)([\w-]{11})", u or "")
    return f"https://i.ytimg.com/vi/{m.group(1)}/hqdefault.jpg" if m else None


def site_of(u):
    return urllib.parse.urlparse(u or "").netloc.replace("www.", "")


BAD_IMG = re.compile(r"\.svg(\?|$)|[/_-](icon|logo|sprite|avatar|badge|emoji|pixel|spacer|button)s?[._/-]|/\d{1,2}px-|favicon|gravatar", re.I)


def best_img(imgs):
    """The page's own preview picture (og:image scores highest), never icons or logos."""
    best = None
    for i in imgs or []:
        u = i if isinstance(i, str) else i.get("url")
        s = 5 if isinstance(i, str) else (i.get("score") or 0)
        if u and u.startswith("http") and not BAD_IMG.search(u) and s >= 5 and (not best or s > best[0]):
            best = (s, u)
    return best[1] if best else None


def search_tavily(kind, q):
    if kind == "images":
        d = tavily(q, max_results=10, include_images=True, include_image_descriptions=True)
        imgs = [{"thumb": i["url"], "url": i["url"], "title": i.get("title") or i.get("description") or "",
                 "site": site_of(i["url"])} for i in d.get("images", []) if isinstance(i, dict)]
        for r in d.get("results", []):
            for i in (r.get("images") or []):
                u = i if isinstance(i, str) else i.get("url")
                if u:
                    imgs.append({"thumb": u, "url": r["url"], "title": r.get("title", ""), "site": site_of(r["url"])})
        seen, out = set(), []
        for i in imgs:
            if i["thumb"] not in seen:
                seen.add(i["thumb"]); out.append(i)
        return {"results": out}
    if kind == "videos":
        d = tavily(q, max_results=12, include_domains=["youtube.com", "vimeo.com", "rutube.ru", "vkvideo.ru"])
        return {"results": [{"title": r.get("title"), "url": r["url"], "site": site_of(r["url"]),
                             "thumb": yt_thumb(r["url"]), "desc": clip(r.get("content"), 200)}
                            for r in d.get("results", [])]}
    if kind == "news":
        d = tavily(q, max_results=12, topic="news", include_images=False)
        return {"results": [{"title": r.get("title"), "url": r["url"], "site": site_of(r["url"]),
                             "age": (r.get("published_date") or "")[:16], "desc": clip(r.get("content"), 260),
                             "thumb": None} for r in d.get("results", [])]}
    d = tavily(q, max_results=10, include_images=True, include_image_descriptions=True)
    out = {"results": [], "news": [], "videos": [], "infobox": None, "images": []}
    seen_img = set()
    for i in d.get("images", []):
        u = i if isinstance(i, str) else i.get("url")
        if u and not BAD_IMG.search(u) and u not in seen_img:
            seen_img.add(u)
            out["images"].append({"thumb": u, "url": u, "title": (i.get("description") if isinstance(i, dict) else "") or q,
                                  "site": site_of(u), "page": None})
    for r in d.get("results", []):
        u = r["url"]
        item = {"title": r.get("title"), "url": u, "desc": clip(r.get("content"), 300),
                "extra": [clip(r.get("content"), 1200)], "site": site_of(u), "icon": r.get("favicon"), "age": None,
                "thumb": best_img(r.get("images"))}
        if item["thumb"] and item["thumb"] not in seen_img and len(out["images"]) < 14:
            seen_img.add(item["thumb"])
            out["images"].append({"thumb": item["thumb"], "url": u, "title": r.get("title") or "", "site": site_of(u), "page": u})
        if yt_thumb(u):
            out["videos"].append({"title": item["title"], "url": u, "site": item["site"], "thumb": yt_thumb(u)})
        out["results"].append(item)
    if len(out["videos"]) < 2:
        out["videos"] = []
    return out


def search(kind, q, offset, lang):
    key = (kind, q.lower(), offset, lang)
    hit = cache_get(key)
    if hit:
        return hit
    if offset and not BRAVE_KEY:
        return {"results": [], "more": False}
    res = None
    if BRAVE_KEY:
        extra = {"count": 20 if kind == "web" else 30, "offset": offset, "safesearch": "moderate"}
        if lang:
            extra["search_lang"] = lang
        if kind == "web":
            extra["extra_snippets"] = "true"
            extra["count"] = 10
            res = norm_web(brave("web", q, extra))
        else:
            d = brave(kind, q, extra)
            res = {"results": [{
                "title": strip_tags(r.get("title")), "url": r.get("url"),
                "site": (r.get("meta_url") or {}).get("hostname") or r.get("source"),
                "age": r.get("age"), "desc": strip_tags(r.get("description")),
                "thumb": (r.get("thumbnail") or {}).get("src"),
                "full": (r.get("properties") or {}).get("url"),
            } for r in d.get("results", [])]}
        res["source"] = "brave"
    elif TAVILY_KEY:
        try:
            res = search_tavily(kind, q)
            res["source"] = "tavily"
            res["more"] = False
        except Exception as e:
            print("tavily failed:", e, flush=True)
    if res is None:
        if kind != "web":
            return {"results": [], "error": "This tab is unavailable right now."}
        res = scrape(q, offset, lang)
        res["source"] = "bing"
    if kind == "web" and not offset:
        res["results"] = yukiindex.merge(res["results"], q)
    cache_set(key, res, 3600 if res.get("source") == "bing" else None)
    return res


def suggest(q):
    hit = cache_get(("sug", q.lower()))
    if hit is not None:
        return hit
    try:
        d = http_json("https://api.bing.com/osjson.aspx?" + urllib.parse.urlencode({"query": q}), timeout=4)
        out = d[1][:8] if isinstance(d, list) and len(d) > 1 else []
    except Exception:
        out = []
    cache_set(("sug", q.lower()), out)
    return out


# ---------- Gemini overview ----------
SYSTEM = (
    "You are Kopro, the answer engine of Yuki Search. Write a short overview that answers the user's query "
    "using ONLY the numbered search results provided. Rules: answer directly in the first sentence; "
    "2-5 short paragraphs or a compact list, under 170 words; cite sources inline as [n] right after the fact "
    "they support; never invent facts, numbers or dates that are not in the results; if the results do not "
    "answer the query, reply with exactly NO_ANSWER and nothing else. Reply in the language of the query. Plain Markdown only "
    "(**bold**, lists). No headings, no preamble, no closing remarks."
)


def overview_stream(q, results, write):
    ctx = "\n\n".join(
        f"[{i+1}] {r['title']} ({r['site']})\n{r['desc']}" + ("\n" + "\n".join(r.get("extra") or []) if r.get("extra") else "")
        for i, r in enumerate(results[:8]))
    body = json.dumps({
        "systemInstruction": {"parts": [{"text": SYSTEM}]},
        "contents": [{"role": "user", "parts": [{"text": f"Today is {time.strftime('%Y-%m-%d')}.\nQuery: {q}\n\nResults:\n{ctx}"}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 600, "thinkingConfig": {"thinkingLevel": "minimal"}},
    }).encode()
    last = None
    for model in MODELS:
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/{model.strip()}:streamGenerateContent"
               f"?alt=sse&key={GEMINI_KEY}")
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                text = ""
                for line in r:
                    line = line.decode("utf-8", "replace").strip()
                    if not line.startswith("data:"):
                        continue
                    try:
                        chunk = json.loads(line[5:])
                        parts = chunk["candidates"][0]["content"]["parts"]
                    except (KeyError, IndexError, ValueError):
                        continue
                    t = "".join(p.get("text", "") for p in parts if not p.get("thought"))
                    if t:
                        text += t
                        write({"t": t})
                return text
        except urllib.error.HTTPError as e:
            last = f"{model}: HTTP {e.code}"
            if e.code in (401, 403):
                break
        except Exception as e:
            last = f"{model}: {e}"
    raise RuntimeError(last or "no model")


# ---------- places (for the Yuki Maps card) ----------
MAP_WORDS = re.compile(r"\b(map|maps|on the map|where is|location of|directions to|how to get to|карта|карты|на карте|где находится|где|как добраться до|как доехать до)\b", re.I)
ZOOM = {"country": 4, "adm1st": 6, "adm2nd": 8, "city": 11, "isle": 10, "waterbody": 8, "mountain": 12,
        "landmark": 15, "airport": 13, "railwaystation": 15, "edu": 15}


def place(q):
    key = ("place", q.lower())
    hit = cache_get(key)
    if hit is not None:
        return hit
    rest = MAP_WORDS.sub(" ", q).strip(" ?,.")
    intent = rest != q.strip(" ?,.")
    out = {}
    if rest and len(rest) <= 80:
        lang = "ru" if re.search("[а-яё]", rest, re.I) else "en"
        url = f"https://{lang}.wikipedia.org/w/api.php?" + urllib.parse.urlencode({
            "action": "query", "format": "json", "generator": "search", "gsrlimit": 1, "gsrsearch": rest,
            "prop": "coordinates|description", "coprop": "type|dim"})
        try:
            d = http_json(url, {"User-Agent": "YukiSearch/1.0 (+https://search.yukichat.lol/about)"}, timeout=6)
            pages = list((d.get("query") or {}).get("pages", {}).values())
            p = pages[0] if pages else None
            co = (p or {}).get("coordinates") or []
            if p and co:
                title = p["title"]
                nt = set(re.findall(r"\w+", title.lower().replace("ё", "е")))
                nq = [w for w in re.findall(r"\w+", rest.lower().replace("ё", "е"))]
                # Without map words the query must name the place itself ("paris", "red square").
                close = all(any(w == t or (len(w) > 4 and t.startswith(w[:-2])) for t in nt) for w in nq)
                org = re.search(r"company|conglomerate|corporation|organi[sz]ation|brand|компания|корпорация|организация", p.get("description") or "", re.I)
                if (close and not org) or intent:
                    c = co[0]
                    z = ZOOM.get(c.get("type"), 13)
                    try:
                        dim = float(c.get("dim") or 0)
                        if dim and not c.get("type"):
                            z = max(3, min(16, round(25 - __import__("math").log2(max(dim, 500)) )))
                    except ValueError:
                        pass
                    out = {"name": title, "desc": p.get("description") or "", "lat": c["lat"], "lon": c["lon"], "zoom": z,
                           "wiki": f"https://{lang}.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"))}
        except Exception as e:
            print("place failed:", e, flush=True)
        return out
    cache_set(key, out)
    return out


# ---------- music (Deezer) ----------
MUSIC_WORDS = re.compile(r"\b(songs?|music|lyrics|album|albums|listen|tracks?|discography|песн[яиюе]|музык[аиу]|слушать|альбомы?|текст|треки?)\b", re.I)


def _toks(s):
    return re.findall(r"\w+", (s or "").lower().replace("ё", "е"))


def music(q):
    key = ("music", q.lower(), int(time.time() // 3600))  # preview links expire
    hit = cache_get(key)
    if hit is not None:
        return hit
    rest = MUSIC_WORDS.sub(" ", q).strip(" -?,.")
    intent = rest.lower() != q.strip(" -?,.").lower()
    out = {}
    rt = set(_toks(rest)) - {"by", "feat", "ft", "от"}
    try:
        if rt:
            a = (http_json("https://api.deezer.com/search/artist?" + urllib.parse.urlencode({"q": rest, "limit": 1}), timeout=6).get("data") or [None])[0]
            if a and set(_toks(a["name"])) == rt and (a.get("nb_fan", 0) >= (2000 if intent else 50000)):
                top = http_json(f"https://api.deezer.com/artist/{a['id']}/top?limit=5", timeout=6).get("data") or []
                out = {"kind": "artist", "name": a["name"], "pic": a.get("picture_xl") or a.get("picture_big"), "fans": a.get("nb_fan"),
                       "albums": a.get("nb_album"), "tracks": [{"title": t["title"], "artist": t["artist"]["name"], "preview": t.get("preview"),
                       "cover": t["album"].get("cover_medium"), "dur": t.get("duration")} for t in top]}
            if not out and len(rt) >= 2:
                for t in (http_json("https://api.deezer.com/search?" + urllib.parse.urlencode({"q": rest, "limit": 3}), timeout=6).get("data") or []):
                    tt, at = set(_toks(t["title"])) - {"feat", "ft"}, set(_toks(t["artist"]["name"]))
                    # "song artist" / "artist - song": both named, nothing else in the query
                    if tt and at and tt <= rt and (at <= rt or intent) and rt <= tt | at and t.get("rank", 0) > 100000:
                        out = {"kind": "track", "title": t["title"], "artist": t["artist"]["name"], "album": t["album"]["title"],
                               "cover": t["album"].get("cover_xl") or t["album"].get("cover_big"), "preview": t.get("preview"), "dur": t.get("duration")}
                        break
    except Exception as e:
        print("music failed:", e, flush=True)
        return out
    cache_set(key, out)
    return out


# ---------- knowledge panel (Wikipedia + Wikidata) ----------
PERSON = {"Q5"}
ORG = {"Q4830453", "Q783794", "Q891723", "Q6881511", "Q43229", "Q167037", "Q18388277", "Q1058914", "Q210167", "Q2085381",
       "Q163740", "Q484652", "Q215380", "Q5341295", "Q1616075", "Q15265344", "Q13226383", "Q2401749", "Q778575"}
WUA = {"User-Agent": "YukiSearch/1.0 (+https://search.yukichat.lol/about)"}
MONTHS = {"en": "January February March April May June July August September October November December".split(),
          "ru": "января февраля марта апреля мая июня июля августа сентября октября ноября декабря".split()}


def _wd_date(c, lang):
    try:
        t = c["mainsnak"]["datavalue"]["value"]
        y, m, d = int(t["time"][1:5]), int(t["time"][6:8]), int(t["time"][9:11])
        prec = t.get("precision", 11)
        if prec >= 11 and m and d:
            return (f"{d} {MONTHS[lang][m-1]} {y}"), (y, m, d)
        if prec == 10 and m:
            return f"{MONTHS[lang][m-1].capitalize() if lang == 'en' else MONTHS[lang][m-1]} {y}", (y, m, 1)
        return str(y), (y, 1, 1)
    except (KeyError, ValueError, TypeError):
        return None, None


def entity(q):
    key = ("ent", q.lower())
    hit = cache_get(key)
    if hit is not None:
        return hit
    out = {}
    rest = MUSIC_WORDS.sub(" ", q).strip(" ?,.")
    lang = "ru" if re.search("[а-яё]", rest, re.I) else "en"
    try:
        d = http_json(f"https://{lang}.wikipedia.org/w/api.php?" + urllib.parse.urlencode({
            "action": "query", "format": "json", "generator": "search", "gsrlimit": 1, "gsrsearch": rest,
            "prop": "coordinates|pageprops|description", "ppprop": "wikibase_item|disambiguation"}), WUA, timeout=6)
        p = (list((d.get("query") or {}).get("pages", {}).values()) or [None])[0]
        if p and "disambiguation" not in (p.get("pageprops") or {}):
            title = p["title"]
            nt = set(_toks(re.sub(r"\(.*?\)", "", title)))
            nq = _toks(rest)
            close = nq and all(any(w == t or (len(w) > 4 and t.startswith(w[:-2])) for t in nt) for w in nq) and len(nt) <= len(nq) + 2
            if close:
                sm = http_json(f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/" + urllib.parse.quote(title.replace(" ", "_")), WUA, timeout=6)
                ex = sm.get("extract") or ""
                out = {"title": sm.get("title") or title, "desc": sm.get("description") or p.get("description") or "",
                       "extract": ex if len(ex) < 600 else ex[:600].rsplit(". ", 1)[0] + ".",
                       "img": (sm.get("thumbnail") or {}).get("source"), "url": (sm.get("content_urls") or {}).get("desktop", {}).get("page"),
                       "facts": [], "kind": "thing"}
                qid = (p.get("pageprops") or {}).get("wikibase_item")
                if qid:
                    out.update(wikidata_facts(qid, lang))
                # Places get the Yuki Maps card instead; people and companies keep their panel.
                if p.get("coordinates") and out["kind"] == "thing":
                    out = {}
    except Exception as e:
        print("entity failed:", e, flush=True)
        return out
    cache_set(key, out)
    return out


def wikidata_facts(qid, lang):
    e = http_json("https://www.wikidata.org/w/api.php?" + urllib.parse.urlencode({
        "action": "wbgetentities", "format": "json", "ids": qid, "props": "claims"}), WUA, timeout=8)["entities"][qid]["claims"]
    def current(p):
        """Claims for p, best first: preferred rank, then ones without an end date; deprecated dropped."""
        cs = [c for c in e.get(p, []) if c["mainsnak"].get("datavalue") and c.get("rank") != "deprecated"]
        pref = [c for c in cs if c.get("rank") == "preferred"]
        live = [c for c in cs if "P582" not in (c.get("qualifiers") or {})]
        return pref or live or cs

    ids = lambda p, n=3: [c["mainsnak"]["datavalue"]["value"]["id"] for c in current(p)[:n]
                          if isinstance(c["mainsnak"]["datavalue"].get("value"), dict) and "id" in c["mainsnak"]["datavalue"]["value"]]
    kinds = set(ids("P31", 20))
    kind = "person" if kinds & PERSON else "org" if kinds & ORG or ("P571" in e and ("P159" in e or "P452" in e)) else "thing"
    plan = []  # (label, [qids] | str)
    L = (lambda en, ru: ru if lang == "ru" else en)
    if kind == "person":
        born, bt = _wd_date(e["P569"][0], lang) if e.get("P569") else (None, None)
        died, dt = _wd_date(e["P570"][0], lang) if e.get("P570") else (None, None)
        if born:
            if bt and not died:
                now = time.gmtime(); age = now.tm_year - bt[0] - ((now.tm_mon, now.tm_mday) < (bt[1], bt[2]))
                born += L(f" (age {age})", f" ({age} лет)" if age % 10 not in (1, 2, 3, 4) or 10 < age % 100 < 15 else f" ({age} года)" if age % 10 in (2, 3, 4) else f" ({age} год)")
            plan.append((L("Born", "Дата рождения"), born, ids("P19", 1)))
        if died:
            plan.append((L("Died", "Дата смерти"), died, ids("P20", 1)))
        if ids("P106"):
            plan.append((L("Occupation", "Род деятельности"), None, ids("P106", 3)))
    elif kind == "org":
        f, _ = _wd_date(e["P571"][0], lang) if e.get("P571") else (None, None)
        if f:
            plan.append((L("Founded", "Основание"), f, []))
        for p, en, ru, n in (("P112", "Founders", "Основатели", 3), ("P169", "CEO", "Гендиректор", 1),
                             ("P159", "Headquarters", "Штаб-квартира", 1), ("P452", "Industry", "Отрасль", 2)):
            if ids(p):
                plan.append((L(en, ru), None, ids(p, n)))
        if e.get("P1128"):
            try:
                v = max(e["P1128"], key=lambda c: c.get("rank") == "preferred")["mainsnak"]["datavalue"]["value"]["amount"]
                plan.append((L("Employees", "Сотрудники"), f"{int(float(v)):,}".replace(",", " "), []))
            except (KeyError, ValueError):
                pass
    need = sorted({i for _, _, q in plan for i in q})
    labels = {}
    if need:
        lb = http_json("https://www.wikidata.org/w/api.php?" + urllib.parse.urlencode({
            "action": "wbgetentities", "format": "json", "ids": "|".join(need[:45]), "props": "labels", "languages": f"{lang}|en|mul"}), WUA, timeout=8)
        for i, v in lb.get("entities", {}).items():
            l = v.get("labels", {})
            labels[i] = (l.get(lang) or l.get("en") or l.get("mul") or {}).get("value")
    facts = []
    for label, text, qs in plan:
        names = [labels.get(i) for i in qs if labels.get(i)]
        if text and names:
            text += ", " + names[0]
        elif not text:
            text = ", ".join(names)
        if text:
            facts.append([label, text])
    site = None
    sites = [c["mainsnak"]["datavalue"]["value"] for c in current("P856")]
    if sites:
        site = min(sites, key=len)
    return {"kind": kind, "facts": facts, "site": site}


# ---------- HTTP ----------
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
         ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png",
         ".ico": "image/x-icon", ".webmanifest": "application/manifest+json", ".xml": "application/opensearchdescription+xml"}


class H(BaseHTTPRequestHandler):
    server_version = "YukiSearch"

    def log_message(self, fmt, *a):
        pass

    def send_json(self, obj, code=200, cache=0):
        b = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", f"public, max-age={cache}" if cache else "no-store")
        if self.path.startswith("/api/suggest"):
            self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        qs = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        q = (qs.get("q") or "").strip()[:300]
        try:
            if u.path == "/api/search":
                kind = qs.get("type", "web")
                if kind not in ("web", "images", "news", "videos"):
                    kind = "web"
                if not q:
                    return self.send_json({"results": []})
                offset = max(0, min(9, int(qs.get("page", "0") or 0)))
                return self.send_json(search(kind, q, offset, qs.get("lang", "")[:5]), cache=300)
            if u.path == "/api/suggest":
                s = suggest(q) if q else []
                return self.send_json([q, s] if qs.get("os") else s, cache=3600)
            if u.path == "/api/music":
                return self.send_json(music(q) if q else {}, cache=600)
            if u.path == "/api/entity":
                return self.send_json(entity(q) if q else {}, cache=3600)
            if u.path == "/api/place":
                return self.send_json(place(q) if q else {}, cache=3600)
            if u.path == "/api/overview":
                return self.overview(q)
            if u.path == "/api/health":
                return self.send_json({"brave": bool(BRAVE_KEY), "tavily": bool(TAVILY_KEY), "gemini": bool(GEMINI_KEY)})
            return self.static(u.path)
        except urllib.error.HTTPError as e:
            self.send_json({"error": f"upstream {e.code}"}, 502)
        except Exception as e:
            self.send_json({"error": str(e)[:200]}, 500)

    def overview(self, q):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        def write(obj):
            self.wfile.write(("data: " + json.dumps(obj, ensure_ascii=False) + "\n\n").encode())
            self.wfile.flush()

        if not q or not GEMINI_KEY:
            return write({"done": True, "skip": True})
        key = ("ov", q.lower())
        hit = cache_get(key)
        res = search("web", q, 0, "")["results"]
        sources = [{"n": i + 1, "title": r["title"], "url": r["url"], "site": r["site"], "icon": r.get("icon")}
                   for i, r in enumerate(res[:8])]
        write({"sources": sources})
        if hit:
            write({"t": hit})
            return write({"done": True})
        if not res:
            return write({"done": True, "skip": True})
        try:
            text = overview_stream(q, res, write)
            if text:
                cache_set(key, text)
            write({"done": True})
        except Exception as e:
            write({"error": str(e)[:120], "done": True})

    def static(self, path):
        if path in ("/", "/search", "/images", "/news", "/videos"):
            path = "/index.html"
        elif path in ("/about", "/about/"):
            path = "/about.html"
        fp = os.path.normpath(os.path.join(STATIC, path.lstrip("/")))
        if not fp.startswith(STATIC) or not os.path.isfile(fp):
            fp = os.path.join(STATIC, "index.html")
        b = open(fp, "rb").read()
        self.send_response(200)
        self.send_header("Content-Type", TYPES.get(os.path.splitext(fp)[1], "application/octet-stream"))
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-cache" if fp.endswith(".html") else "public, max-age=3600")
        self.end_headers()
        self.wfile.write(b)


if __name__ == "__main__":
    yukiindex.start()
    ThreadingHTTPServer.daemon_threads = True
    print(f"Yuki Search on 127.0.0.1:{PORT} brave={bool(BRAVE_KEY)} gemini={bool(GEMINI_KEY)}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
