# Yuki Search

A search engine front end with AI overviews, image, news and video search, knowledge panels and inline widgets.

**Live:** [search.yukichat.lol](https://search.yukichat.lol)

## Features

- Web, image, news and video results
- AI overview: a short answer written from the top results with cited sources, streamed as it is generated
- Knowledge panels for people, companies and topics, from Wikipedia and Wikidata
- Map card for place queries, with an embedded [Yuki Maps](https://github.com/katsyka/yukimaps) view
- Music card with track previews, from Deezer
- Image previews in results and a full-screen image viewer
- Search suggestions, with OpenSearch support so it can be added as a browser search engine
- English and Russian UI, light and dark themes, a mobile layout

## Stack

- **Server:** Python 3.8+ standard library only (`server.py`), with an SQLite response cache
- **Frontend:** plain HTML, CSS and JavaScript (`static/`)
- **Search providers:** Brave Search API or Tavily, falling back to Bing
- **Overview model:** Google Gemini

## Configuration

Create a `.env` file next to `server.py`:

```sh
BRAVE_API_KEY=...      # optional; used first if set
TAVILY_API_KEY=...     # used when Brave is not configured
GEMINI_API_KEY=...     # AI overviews
```

## Running

```sh
python3 server.py
```

## API

| Endpoint | Description |
| --- | --- |
| `GET /api/search?q=&type=web\|images\|news\|videos&page=&lang=` | Search results |
| `GET /api/overview?q=` | AI overview (server-sent events) |
| `GET /api/suggest?q=` | Suggestions (`&os=1` for OpenSearch format) |
| `GET /api/place?q=` | Place lookup for the map card |
| `GET /api/entity?q=` | Knowledge panel data |
| `GET /api/music?q=` | Music card data |
| `GET /api/health` | Health check |

## Caching

Responses are cached in `cache.db` so repeated queries cost nothing. Lifetimes range from 1 hour (music) to 7 days (web results) and 30 days (places and entities). Failed lookups are not cached.
