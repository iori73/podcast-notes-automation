#!/usr/bin/env python3
"""
Export the latest N Notion podcast entries into an Obsidian vault as a linked
note network (for graph view).

Creates, under the vault's `03_Resources/podcasts/` folder:
  episodes/    - one note per episode (Summary / Key Takeaways / Timestamps + links)
  shows/       - one hub note per Podcast (select)
  categories/  - one hub note per Category (select)
  topics/      - one hub note per Gemini-extracted topic
  people/      - one hub note per Gemini-extracted person/guest

Episodes link OUT to their show/category/topic/people hubs via [[wikilinks]];
shared topics/people across episodes are what create the cross-cluster network.

Reuses the proven Notion + Gemini helpers from batch_update_episodes.py.

Usage (from repo root, venv active):
    python scripts/export_to_obsidian.py                 # export latest 50
    python scripts/export_to_obsidian.py --limit 20      # fewer
    python scripts/export_to_obsidian.py --no-gemini     # metadata-only links
    python scripts/export_to_obsidian.py --check         # link-integrity report only
"""

import argparse
import json
import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(_REPO / "src"))
sys.path.insert(0, str(_REPO / "src" / "integrations"))

import requests  # noqa: E402
from integrations.notion_client import NotionClient  # noqa: E402
import batch_update_episodes as bue  # noqa: E402  (reuse gemini + block helpers)

VAULT = (
    Path.home()
    / "Library/Mobile Documents/iCloud~md~obsidian/Documents"
    / "ai-ops-vault/03_Resources/podcasts"
)
SUBDIRS = ["episodes", "shows", "categories", "topics", "people"]
GEMINI_BATCH = 7  # episodes per Gemini call (keeps us well under free-tier RPD)
CACHE = Path("data/obsidian_export_cache.json")  # cached Gemini topics/people


# --------------------------------------------------------------------------- #
# Notion read
# --------------------------------------------------------------------------- #
def query_latest(notion: NotionClient, n: int) -> list:
    """Latest N pages by created_time (descending)."""
    url = f"https://api.notion.com/v1/databases/{notion.database_id}/query"
    payload = {
        "sorts": [{"timestamp": "created_time", "direction": "descending"}],
        "page_size": min(n, 100),
    }
    resp = requests.post(url, headers=notion.headers, json=payload)
    resp.raise_for_status()
    return resp.json().get("results", [])[:n]


def prop_url(page):
    return page.get("properties", {}).get("URL", {}).get("url")


def prop_date(page):
    d = page.get("properties", {}).get("Release Date", {}).get("date")
    return d.get("start") if d else None


def prop_duration(page):
    return page.get("properties", {}).get("1. Duration", {}).get("number")


def extract_sections(blocks: list) -> dict:
    """Pull Summary / Key Takeaways / Timestamps text from page blocks.

    Transcript (toggle / heading) is intentionally skipped — summary-only export.
    """
    out = {"summary": [], "key_takeaways": [], "timestamps": []}
    current = None
    for b in blocks:
        bt = b.get("type", "")
        if bt in ("heading_2", "heading_3"):
            t = bue.extract_block_text(b).strip()
            tl = t.lower()
            if "transcript" in tl or "文字起こし" in t:
                current = "transcript"
            elif "timestamp" in tl or "タイムスタンプ" in t:
                current = "timestamps"
            elif "key takeaway" in tl:
                current = "key_takeaways"
            elif "summary" in tl or "要約" in t:
                current = "summary"
            else:
                current = None  # Basic Information, etc.
            continue
        if bt == "toggle":  # the Transcript toggle — skip its content
            current = "transcript"
            continue
        if current in out:
            txt = bue.extract_block_text(b).strip()
            if txt:
                out[current].append(txt)
    return out


# --------------------------------------------------------------------------- #
# Gemini topic/people extraction (batched)
# --------------------------------------------------------------------------- #
def extract_topics_people(client, models, episodes: list) -> None:
    """Mutate each episode dict, adding 'topics' and 'people' lists."""
    for ep in episodes:
        ep.setdefault("topics", [])
        ep.setdefault("people", [])
    if not client:
        return

    for i in range(0, len(episodes), GEMINI_BATCH):
        batch = episodes[i : i + GEMINI_BATCH]
        items = []
        for idx, ep in enumerate(batch):
            body = (ep["title"] + "\n" + ep["summary_text"] + "\n" + ep["takeaways_text"])[:2500]
            items.append(f"### EP{idx}\n{body}")
        prompt = (
            "次の各ポッドキャストエピソードについて、主要トピック(3〜6個)と"
            "登場人物・ゲスト名(0〜4個)を抽出してください。\n"
            "- トピックは日本語の短い名詞句（例: 発酵, 麹菌, 生成AI）。一般語(雑談,話 等)は避ける。\n"
            "- 人物は実在の人名のみ。役職や敬称は除く。不明なら空配列。\n"
            "出力は厳密なJSON配列のみ。各要素は "
            '{"ep": <番号>, "topics": [..], "people": [..]} の形式。\n\n'
            + "\n\n".join(items)
        )
        raw = bue.gemini_generate(client, models, prompt)
        parsed = _parse_json(raw)
        if not parsed:
            print(f"   ⚠️ batch {i//GEMINI_BATCH}: Gemini抽出失敗 → このバッチはメタデータのみ")
            continue
        by_ep = {int(o.get("ep", -1)): o for o in parsed if isinstance(o, dict)}
        for idx, ep in enumerate(batch):
            o = by_ep.get(idx, {})
            ep["topics"] = [t.strip() for t in o.get("topics", []) if t and t.strip()]
            ep["people"] = [p.strip() for p in o.get("people", []) if p and p.strip()]
        print(f"   ✅ topics/people: {i+1}–{i+len(batch)} / {len(episodes)}")


def _parse_json(raw):
    if not raw:
        return None
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()
    m = re.search(r"\[.*\]", raw, re.DOTALL)
    if m:
        raw = m.group(0)
    try:
        return json.loads(raw)
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# Vault writing
# --------------------------------------------------------------------------- #
def sanitize(name: str) -> str:
    """Safe for both filenames and [[wikilink]] targets."""
    name = (name or "").strip()
    repl = {"/": "／", "\\": "＼", ":": "：", "?": "？", "*": "＊", '"': "'", "<": "", ">": ""}
    for a, b in repl.items():
        name = name.replace(a, b)
    name = re.sub(r"[\[\]#\^|]", "", name)  # Obsidian-illegal in wikilinks
    name = name.rstrip(". ")  # no trailing dot/space
    return name[:180] or "untitled"


def yaml_str(s) -> str:
    return '"' + str(s).replace('"', "'") + '"'


def slug_tag(s: str) -> str:
    return re.sub(r"\s+", "-", sanitize(s)).strip("-")


def write_note(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_hub(kind: str, name: str, desc: str):
    safe = sanitize(name)
    fm = f"---\ntype: {kind}\nname: {yaml_str(name)}\n---\n\n# {name}\n\n{desc}\n"
    write_note(VAULT / kind / f"{safe}.md", fm)


def build_episode_note(ep: dict, linked_topics: set, linked_people: set) -> str:
    fm = ["---"]
    fm.append(f"title: {yaml_str(ep['title'])}")
    if ep["podcast"]:
        fm.append(f"podcast: {yaml_str(ep['podcast'])}")
    if ep["category"]:
        fm.append(f"category: {yaml_str(ep['category'])}")
    if ep["date"]:
        fm.append(f"release_date: {ep['date']}")
    if ep["duration"] is not None:
        fm.append(f"duration_min: {round(ep['duration'], 1)}")
    if ep["url"]:
        fm.append(f"spotify_url: {yaml_str(ep['url'])}")
    tags = ["podcast"]
    if ep["category"]:
        tags.append("category/" + slug_tag(ep["category"]))
    fm.append("tags: [" + ", ".join(tags) + "]")
    fm.append("---\n")

    body = [f"# {ep['title']}\n"]
    if ep["summary_text"]:
        body.append("## Summary\n\n" + ep["summary_text"] + "\n")
    if ep["takeaways_list"]:
        body.append("## Key Takeaways\n\n" + "\n".join(f"- {t}" for t in ep["takeaways_list"]) + "\n")
    if ep["timestamps_list"]:
        body.append("## Timestamps\n\n" + "\n".join(ep["timestamps_list"]) + "\n")

    links = ["## Links\n"]
    if ep["podcast"]:
        links.append(f"- Podcast: [[{sanitize(ep['podcast'])}]]")
    if ep["category"]:
        links.append(f"- Category: [[{sanitize(ep['category'])}]]")
    # Only wikilink topics/people shared across episodes (graph nodes);
    # render one-off mentions as plain text so they don't clutter the graph.
    t_link = [t for t in ep["topics"] if t in linked_topics]
    t_plain = [t for t in ep["topics"] if t not in linked_topics]
    p_link = [p for p in ep["people"] if p in linked_people]
    p_plain = [p for p in ep["people"] if p not in linked_people]
    if t_link:
        links.append("- Topics: " + ", ".join(f"[[{sanitize(t)}]]" for t in t_link))
    if t_plain:
        links.append("- Topics (mentioned): " + ", ".join(t_plain))
    if p_link:
        links.append("- People: " + ", ".join(f"[[{sanitize(p)}]]" for p in p_link))
    if p_plain:
        links.append("- People (mentioned): " + ", ".join(p_plain))
    if ep["url"]:
        links.append(f"- [Spotify]({ep['url']})")

    return "\n".join(fm) + "\n".join(body) + "\n" + "\n".join(links) + "\n"


def clean_vault():
    """Remove prior *.md in our subdirs so re-runs don't leave stale hubs."""
    for sub in SUBDIRS:
        d = VAULT / sub
        if d.exists():
            for f in d.glob("*.md"):
                f.unlink()


# --------------------------------------------------------------------------- #
# Link-integrity check
# --------------------------------------------------------------------------- #
def check_links() -> int:
    existing = {f.stem for sub in SUBDIRS for f in (VAULT / sub).glob("*.md")} if VAULT.exists() else set()
    dangling = {}
    for f in (VAULT / "episodes").glob("*.md"):
        for target in re.findall(r"\[\[([^\]]+)\]\]", f.read_text(encoding="utf-8")):
            if target not in existing:
                dangling.setdefault(f.name, []).append(target)
    if dangling:
        print("❌ Dangling wikilinks (missing graph nodes):")
        for note, targets in dangling.items():
            print(f"   {note}: {targets}")
    else:
        print(f"✅ Link integrity OK — {len(existing)} nodes, no dangling links.")
    return len(dangling)


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(description="Export latest Notion entries to Obsidian")
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--no-gemini", action="store_true", help="skip topic/people extraction")
    ap.add_argument("--from-cache", action="store_true", help="reuse cached Gemini topics/people (no API calls)")
    ap.add_argument("--min-link-degree", type=int, default=2,
                    help="min #episodes a topic/person must span to become a graph node (else plain text)")
    ap.add_argument("--check", action="store_true", help="only run link-integrity check")
    args = ap.parse_args()

    if args.check:
        check_links()
        return

    print(f"📂 Vault target: {VAULT}")
    notion = NotionClient()

    print(f"\n📡 Querying latest {args.limit} entries (by created_time)...")
    pages = query_latest(notion, args.limit)
    print(f"   ✅ {len(pages)} pages")

    print("\n📄 Reading page bodies...")
    episodes, skipped = [], []
    for p in pages:
        title = bue.get_page_title(p)
        if not title:
            continue
        blocks = bue.fetch_all_block_children(notion, p["id"])
        sec = extract_sections(blocks)
        summary_text = "\n\n".join(sec["summary"]).strip()
        if not summary_text:
            skipped.append(title)
        episodes.append(
            {
                "title": title,
                "podcast": bue.get_page_podcast(p),
                "category": bue.get_page_category(p) or "",
                "date": prop_date(p),
                "duration": prop_duration(p),
                "url": prop_url(p),
                "summary_text": summary_text,
                "takeaways_list": sec["key_takeaways"],
                "takeaways_text": "\n".join(sec["key_takeaways"]),
                "timestamps_list": sec["timestamps"],
            }
        )
    print(f"   ✅ {len(episodes)} episodes parsed ({len(skipped)} missing Summary)")

    # Gemini topics/people (with cache to avoid re-calling on re-tune)
    cache = {}
    if args.from_cache and CACHE.exists():
        cache = json.loads(CACHE.read_text(encoding="utf-8"))
        for ep in episodes:
            c = cache.get(ep["title"], {})
            ep["topics"], ep["people"] = c.get("topics", []), c.get("people", [])
        print(f"\n💾 Loaded topics/people from cache ({len(cache)} episodes) — no Gemini calls.")
    else:
        client, models = (None, [])
        if not args.no_gemini:
            print("\n🧠 Initializing Gemini for topic/people extraction...")
            client, models = bue.init_gemini()
            if not client:
                print("   ⚠️ Gemini unavailable — falling back to metadata-only links (shows+categories).")
        extract_topics_people(client, models, episodes)
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(
            {ep["title"]: {"topics": ep["topics"], "people": ep["people"]} for ep in episodes},
            ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"   💾 Cached topics/people → {CACHE}")

    # Degree counts → only terms spanning ≥ min-link-degree episodes become graph nodes
    import collections
    t_deg, p_deg = collections.Counter(), collections.Counter()
    for ep in episodes:
        for t in set(ep["topics"]):
            t_deg[t] += 1
        for pp in set(ep["people"]):
            p_deg[pp] += 1
    linked_topics = {t for t, n in t_deg.items() if n >= args.min_link_degree}
    linked_people = {p for p, n in p_deg.items() if n >= args.min_link_degree}

    # Write vault
    print("\n📝 Writing Obsidian notes...")
    clean_vault()
    for sub in SUBDIRS:
        (VAULT / sub).mkdir(parents=True, exist_ok=True)

    shows, cats = set(), set()
    for ep in episodes:
        write_note(VAULT / "episodes" / f"{sanitize(ep['title'])}.md",
                   build_episode_note(ep, linked_topics, linked_people))
        if ep["podcast"]:
            shows.add(ep["podcast"])
        if ep["category"]:
            cats.add(ep["category"])

    for s in shows:
        write_hub("shows", s, f"Podcast show. Episodes link here.")
    for c in cats:
        write_hub("categories", c, f"Category. Episodes in this category link here.")
    for t in linked_topics:
        write_hub("topics", t, f"Topic shared by {t_deg[t]} episodes.")
    for pp in linked_people:
        write_hub("people", pp, f"Person / guest in {p_deg[pp]} episodes.")

    print(
        f"   ✅ {len(episodes)} episodes, {len(shows)} shows, {len(cats)} categories, "
        f"{len(linked_topics)} topic-nodes (of {len(t_deg)}), "
        f"{len(linked_people)} people-nodes (of {len(p_deg)}) "
        f"[threshold ≥{args.min_link_degree} eps]"
    )
    if skipped:
        print(f"   ℹ️ {len(skipped)} episodes had no Summary (linked by metadata only).")

    print("\n🔗 Verifying link integrity...")
    check_links()
    print(f"\n✅ Done. Open Obsidian → Graph view, filter path:03_Resources/podcasts")


if __name__ == "__main__":
    main()
