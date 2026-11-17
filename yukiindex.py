"""Index of Yuki's own sites. Titles and descriptions are crawled from the live pages (daily);
keywords say what each page is for, in English and Russian. Matches are merged into the normal
web results and ranked like any other result: a query naming the app puts it first, a query
describing what it does puts it a few places down."""
import html, re, threading, time, urllib.request

PAGES = [
    ("https://yukichat.lol/", "YukiChat", "messenger chat messages calls video calls channels encrypted messaging app мессенджер чат сообщения звонки видеозвонки каналы переписка"),
    ("https://music.yukichat.lol/", "YukiMusic", "music streaming listen songs playlists ai dj radio музыка слушать песни плейлисты стриминг диджей"),
    ("https://maps.yukichat.lol/", "Yuki Maps", "map maps 3d map satellite directions route transit metro public transport navigation карта карты маршрут спутник метро транспорт навигация"),
    ("https://maps.yukichat.lol/about/", "Yuki Maps", "map app 3d buildings routes transit moscow st petersburg карты 3d маршруты москва петербург"),
    ("https://search.yukichat.lol/about", "Yuki Search", "search engine ai answers overview поиск поисковик поисковая система ответы ии"),
    ("https://mail.yukichat.lol/", "YukiMail", "email mail inbox address second email temp mail почта почтовый ящик электронная почта адрес"),
    ("https://meet.yukichat.lol/", "YukiMeet", "video meeting video call conference rooms видеовстреча видеоконференция созвон встреча"),
    ("https://board.yukichat.lol/", "YukiBoard", "whiteboard online board canvas draw together collaborate доска онлайн доска рисовать вместе"),
    ("https://pages.yukichat.lol/", "Yuki Pages", "website hosting free hosting static site publish website хостинг бесплатный хостинг сайт опубликовать сайт"),
    ("https://write.yukichat.lol/", "Yuki Write", "write publish article story blog post telegraph писать опубликовать статья история блог"),
    ("https://chain.yukichat.lol/", "YukiChain", "blockchain explorer crypto cryptocurrency yuki coin блокчейн обозреватель криптовалюта крипта"),
    ("https://wallet.yukichat.lol/", "Yuki Wallet", "crypto wallet wallet seed phrase send coins кошелёк кошелек криптокошелёк"),
    ("https://account.yukichat.lol/", "Yuki ID", "account sign in login single sign-on profile аккаунт вход логин профиль"),
    ("https://vinyl.yukichat.lol/", "YukiVinyl", "vinyl records record store buy vinyl lp avito ozon wildberries винил пластинки купить винил"),
    ("https://yuki.yukichat.lol/", "Yuki apps", "yuki apps all apps приложения yuki все приложения"),
    ("https://yuki.yukichat.lol/yukiweb/", "YukiWeb", "browser web browser windows android vpn браузер веб браузер"),
    ("https://kopro.mom/", "Kopro AI", "ai chatbot assistant neural network llm coding ии нейросеть чат бот ассистент"),
    ("https://docs.yukichat.lol/", "YukiChat bots docs", "bot api docs developers bots documentation боты документация api разработчикам"),
]
# Brand words: a query containing one of these is looking for that app by name.
BRANDS = {
    "yukichat": "https://yukichat.lol/", "yukimusic": "https://music.yukichat.lol/", "yukimaps": "https://maps.yukichat.lol/",
    "yukisearch": "https://search.yukichat.lol/about", "yukimail": "https://mail.yukichat.lol/", "yukimeet": "https://meet.yukichat.lol/",
    "yukiboard": "https://board.yukichat.lol/", "yukipages": "https://pages.yukichat.lol/", "yukiwrite": "https://write.yukichat.lol/",
    "yukichain": "https://chain.yukichat.lol/", "yukiwallet": "https://wallet.yukichat.lol/", "yukiid": "https://account.yukichat.lol/",
    "yukivinyl": "https://vinyl.yukichat.lol/", "yukiweb": "https://yuki.yukichat.lol/yukiweb/", "kopro": "https://kopro.mom/",
    "yukiapps": "https://yuki.yukichat.lol/", "yuki": "https://yuki.yukichat.lol/",
}
STOP = set("a an the of for to in on and or is are how what where free online app best my me i with without "
           "и в на для с по как что где бесплатно онлайн приложение лучший мой".split())

INDEX = {u: {"title": t, "desc": "", "kw": kw} for u, t, kw in PAGES}
UA = "YukiSearch-indexer/1.0 (+https://search.yukichat.lol/about)"


def _crawl_once():
    for u in INDEX:
        try:
            req = urllib.request.Request(u, headers={"User-Agent": UA})
            page = urllib.request.urlopen(req, timeout=10).read(200_000).decode("utf-8", "replace")
            t = re.search(r"<title[^>]*>(.*?)</title>", page, re.S | re.I)
            d = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']*)', page, re.I) or \
                re.search(r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']*)', page, re.I)
            if t and t.group(1).strip():
                INDEX[u]["title"] = html.unescape(re.sub(r"\s+", " ", t.group(1))).strip()
            if d:
                INDEX[u]["desc"] = html.unescape(d.group(1)).strip()
        except Exception as e:
            print("index: failed", u, e, flush=True)


def start():
    def loop():
        while True:
            _crawl_once()
            time.sleep(24 * 3600)
    threading.Thread(target=loop, daemon=True).start()


def _norm(s):
    return re.sub(r"[^\w]+", " ", (s or "").lower().replace("ё", "е")).split()


def matches(q):
    """[(position, result)] for Yuki pages that answer this query."""
    words = _norm(q)
    joined = "".join(words)
    toks = [w for w in words if w not in STOP]
    if not toks:
        return []
    out, used = [], set()
    # 1) By name ("yuki music", "yukimusic", "юки"?) → top of the results.
    for b, u in sorted(BRANDS.items(), key=lambda x: -len(x[0])):
        if u in used or (b == "yuki" and joined not in ("yuki", "yukiapps", "yukiapp")) or b not in joined:
            continue
        if True:
            used.add(u)
            out.append((0, u))
            if len(out) >= 2:
                break
    # 2) By what it does: every meaningful word of the query is one of the page's keywords.
    if not out:
        best = None
        for u, e in INDEX.items():
            kw = set(_norm(e["kw"]))
            hit = sum(1 for t in toks if t in kw)
            if hit == len(toks) and (not best or hit > best[0]):
                best = (hit, u)
        if best:
            out.append((2 if best[0] >= 2 else 4, best[1]))
    res = []
    for pos, u in out:
        e = INDEX[u]
        res.append((pos, {"title": e["title"], "url": u, "desc": e["desc"] or e["title"], "extra": [e["desc"]] if e["desc"] else [],
                          "site": u.split("/")[2],
                          "icon": None, "age": None, "thumb": None}))
    return res


def merge(results, q):
    """Insert matching Yuki pages into a web result list (no duplicates)."""
    have = {r.get("url", "").rstrip("/") for r in results}
    out = list(results)
    for pos, r in matches(q):
        if r["url"].rstrip("/") in have:
            continue
        out.insert(min(pos, len(out)), r)
        have.add(r["url"].rstrip("/"))
    return out
