"""
iTunes RSS Client for Podcast Audio Retrieval

This module provides functionality to:
1. Search for podcasts using iTunes Search API (free, no auth required)
2. Get RSS feed URL from iTunes Lookup API
3. Parse RSS feed to find specific episodes and their audio URLs

All APIs used are completely free with no authentication required.
"""

import requests
import xml.etree.ElementTree as ET
from typing import Optional, Dict, List
from datetime import datetime
import re
from difflib import SequenceMatcher


class iTunesRSSClient:
    """Client for iTunes API and RSS feed processing."""
    
    ITUNES_SEARCH_URL = "https://itunes.apple.com/search"
    ITUNES_LOOKUP_URL = "https://itunes.apple.com/lookup"
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "PodcastNotesAutomation/1.0"
        })
    
    def search_podcast(self, show_name: str, country: str = "jp") -> Optional[Dict]:
        """
        Search for a podcast by name using iTunes Search API.

        Args:
            show_name: Name of the podcast show
            country: Country code (default: jp for Japan)

        Returns:
            dict with podcast info including collectionId, or None if not found
        """
        print(f"🔍 iTunes Search: {show_name}")

        try:
            params = {
                "term": show_name,
                "media": "podcast",
                "entity": "podcast",
                "limit": 10,
                "country": country
            }

            response = self.session.get(self.ITUNES_SEARCH_URL, params=params, timeout=30)
            response.raise_for_status()

            data = response.json()
            results = data.get("results", [])

            if not results:
                print(f"   ❌ No podcasts found for: {show_name}")
                return None

            # Step 1: strict pass - a normalized-containment match on the show name
            # itself (not the artist/host bio, which causes coincidental false
            # positives like "デザインの味付け" matching an unrelated host whose
            # bio happens to contain the word "デザイン").
            for podcast in results:
                collection_name = podcast.get("collectionName", "")
                if self._podcast_names_match(show_name, collection_name):
                    print(f"   ✅ Found (strict match): {collection_name}")
                    print(f"   📌 Apple Podcast ID: {podcast.get('collectionId')}")
                    return {
                        "podcast_id": podcast.get("collectionId"),
                        "name": collection_name,
                        "artist": podcast.get("artistName"),
                        "feed_url": podcast.get("feedUrl"),
                        "artwork_url": podcast.get("artworkUrl600"),
                        "similarity_score": 1.0
                    }

            # Step 2: fuzzy fallback on the show name only (not artist name),
            # with a threshold high enough to reject coincidental overlaps.
            best_match = None
            best_score = 0

            for podcast in results:
                collection_name = podcast.get("collectionName", "")
                name_score = self._similarity(show_name.lower(), collection_name.lower())

                if name_score > best_score:
                    best_score = name_score
                    best_match = podcast

            if best_match and best_score >= 0.5:  # Minimum 50% similarity
                print(f"   ✅ Found: {best_match.get('collectionName')}")
                print(f"   📌 Apple Podcast ID: {best_match.get('collectionId')}")
                return {
                    "podcast_id": best_match.get("collectionId"),
                    "name": best_match.get("collectionName"),
                    "artist": best_match.get("artistName"),
                    "feed_url": best_match.get("feedUrl"),
                    "artwork_url": best_match.get("artworkUrl600"),
                    "similarity_score": best_score
                }
            else:
                print(f"   ❌ No good match found (best score: {best_score:.2f})")
                return None

        except requests.RequestException as e:
            print(f"   ❌ iTunes Search error: {e}")
            return None

    def _normalize_podcast_name(self, name: str) -> str:
        """Normalize podcast name for comparison (remove spaces, punctuation, lowercase)."""
        if not name:
            return ""
        name = name.lower()
        name = re.sub(r'\s*(podcast|ポッドキャスト|radio|ラジオ)\s*$', '', name, flags=re.IGNORECASE)
        name = re.sub(r'[^\w぀-ゟ゠-ヿ一-鿿]', '', name)
        return name

    def _podcast_names_match(self, expected_name: str, actual_name: str) -> bool:
        """
        Check if podcast names match strictly (same logic as ListenNotesClient).
        Returns True only if names are essentially the same podcast.
        """
        if not expected_name or not actual_name:
            return False

        norm_expected = self._normalize_podcast_name(expected_name)
        norm_actual = self._normalize_podcast_name(actual_name)

        if norm_expected == norm_actual:
            return True

        if norm_expected in norm_actual or norm_actual in norm_expected:
            shorter = min(norm_expected, norm_actual, key=len)
            longer = max(norm_expected, norm_actual, key=len)
            if len(shorter) / len(longer) >= 0.7:
                return True

        return False
    
    def get_rss_feed_url(self, podcast_id: int) -> Optional[str]:
        """
        Get RSS feed URL for a podcast using iTunes Lookup API.
        
        Args:
            podcast_id: Apple Podcast collection ID
            
        Returns:
            RSS feed URL or None if not found
        """
        print(f"🔍 iTunes Lookup: Podcast ID {podcast_id}")
        
        try:
            params = {
                "id": podcast_id,
                "media": "podcast",
                "entity": "podcast"
            }
            
            response = self.session.get(self.ITUNES_LOOKUP_URL, params=params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            results = data.get("results", [])
            
            if not results:
                print(f"   ❌ No podcast found for ID: {podcast_id}")
                return None
            
            feed_url = results[0].get("feedUrl")
            if feed_url:
                print(f"   ✅ RSS Feed URL: {feed_url}")
                return feed_url
            else:
                print(f"   ❌ No RSS feed URL found")
                return None
                
        except requests.RequestException as e:
            print(f"   ❌ iTunes Lookup error: {e}")
            return None
    
    def find_episode_audio_url(
        self,
        rss_url: str,
        episode_title: str,
        release_date: Optional[str] = None,
        duration_ms: Optional[int] = None
    ) -> Optional[Dict]:
        """
        Find a specific episode in RSS feed and return its audio URL.
        
        Args:
            rss_url: URL of the RSS feed
            episode_title: Title of the episode to find
            release_date: Release date in YYYY-MM-DD format (optional)
            duration_ms: Duration in milliseconds (optional, for verification)
            
        Returns:
            dict with episode info including audio_url, or None if not found
        """
        print(f"📡 Fetching RSS feed: {rss_url}")
        
        try:
            response = self.session.get(rss_url, timeout=60)
            response.raise_for_status()
            
            # Parse RSS XML
            root = ET.fromstring(response.content)
            
            # Find channel
            channel = root.find("channel")
            if channel is None:
                print("   ❌ Invalid RSS feed: no channel element")
                return None
            
            # Find all items (episodes)
            items = channel.findall("item")
            print(f"   📊 Found {len(items)} episodes in feed")
            
            # Search for matching episode
            best_match = None
            best_score = 0
            
            for item in items:
                item_title = self._get_text(item, "title")
                item_date = self._get_text(item, "pubDate")
                
                if not item_title:
                    continue
                
                # Calculate match score
                score = self._calculate_episode_match_score(
                    item_title, item_date,
                    episode_title, release_date
                )
                
                if score > best_score:
                    best_score = score
                    
                    # Get audio URL from enclosure
                    enclosure = item.find("enclosure")
                    audio_url = enclosure.get("url") if enclosure is not None else None
                    
                    # Also check for media:content (some feeds use this)
                    if not audio_url:
                        # Try media namespace
                        for child in item:
                            if "content" in child.tag and child.get("url"):
                                audio_url = child.get("url")
                                break
                    
                    if audio_url:
                        # Get duration if available
                        duration_str = self._get_text(item, "{http://www.itunes.com/dtds/podcast-1.0.dtd}duration")
                        if not duration_str:
                            duration_str = self._get_text(item, "duration")
                        
                        best_match = {
                            "title": item_title,
                            "audio_url": audio_url,
                            "pub_date": item_date,
                            "duration": duration_str,
                            "match_score": score
                        }
            
            if best_match and best_score >= 0.4:  # Minimum 40% match
                print(f"   ✅ Found episode: {best_match['title'][:50]}...")
                print(f"   🎵 Audio URL: {best_match['audio_url'][:80]}...")
                return best_match
            else:
                print(f"   ❌ No matching episode found (best score: {best_score:.2f})")
                
                # Show top candidates for debugging
                if items:
                    print("   📋 Recent episodes in feed:")
                    for item in items[:5]:
                        title = self._get_text(item, "title")
                        if title:
                            print(f"      - {title[:60]}...")
                
                return None
                
        except requests.RequestException as e:
            print(f"   ❌ RSS fetch error: {e}")
            return None
        except ET.ParseError as e:
            print(f"   ❌ RSS parse error: {e}")
            return None
    
    def get_episode_audio(
        self,
        show_name: str,
        episode_title: str,
        release_date: Optional[str] = None,
        duration_ms: Optional[int] = None
    ) -> Optional[Dict]:
        """
        Main method: Search podcast and find episode audio URL.
        
        This combines all steps:
        1. Search for podcast by name
        2. Get RSS feed URL
        3. Find episode in RSS and get audio URL
        
        Args:
            show_name: Name of the podcast
            episode_title: Title of the episode
            release_date: Release date (YYYY-MM-DD)
            duration_ms: Duration in milliseconds
            
        Returns:
            dict with audio_url and metadata, or None if not found
        """
        print("\n" + "=" * 50)
        print("🎙️ iTunes/RSS Audio Search")
        print("=" * 50)
        print(f"📺 Show: {show_name}")
        print(f"📝 Episode: {episode_title}")
        if release_date:
            print(f"📅 Date: {release_date}")
        
        # Step 1: Search for podcast
        podcast = self.search_podcast(show_name)
        
        if not podcast:
            # Try without special characters
            cleaned_name = re.sub(r'[【】「」『』（）\(\)]', ' ', show_name)
            cleaned_name = re.sub(r'\s+', ' ', cleaned_name).strip()
            if cleaned_name != show_name:
                print(f"   🔄 Retrying with cleaned name: {cleaned_name}")
                podcast = self.search_podcast(cleaned_name)
        
        if not podcast:
            return None
        
        # Step 2: Get RSS feed URL
        feed_url = podcast.get("feed_url")
        if not feed_url:
            feed_url = self.get_rss_feed_url(podcast["podcast_id"])
        
        if not feed_url:
            return None
        
        # Step 3: Find episode in RSS
        episode = self.find_episode_audio_url(
            feed_url,
            episode_title,
            release_date,
            duration_ms
        )
        
        if not episode:
            return None
        
        return {
            "audio_url": episode["audio_url"],
            "episode_title": episode["title"],
            "pub_date": episode.get("pub_date"),
            "duration": episode.get("duration"),
            "podcast_name": podcast["name"],
            "podcast_id": podcast["podcast_id"],
            "feed_url": feed_url,
            "match_score": episode.get("match_score", 0)
        }
    
    def download_audio(self, audio_url: str, output_path: str) -> bool:
        """
        Download audio file from URL.
        
        Args:
            audio_url: URL of the audio file
            output_path: Path to save the downloaded file
            
        Returns:
            True if download successful, False otherwise
        """
        print(f"\n📥 Downloading audio...")
        print(f"   URL: {audio_url[:80]}...")
        
        try:
            response = self.session.get(audio_url, stream=True, timeout=300)
            response.raise_for_status()
            
            # Get file size if available
            total_size = int(response.headers.get('content-length', 0))
            
            downloaded = 0
            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        # Progress indicator
                        if total_size > 0:
                            progress = (downloaded / total_size) * 100
                            print(f"\r   📊 Progress: {progress:.1f}% ({downloaded / (1024*1024):.1f}MB)", end="")
            
            print(f"\n   ✅ Downloaded: {output_path}")
            return True
            
        except requests.RequestException as e:
            print(f"\n   ❌ Download error: {e}")
            return False
    
    def _similarity(self, a: str, b: str) -> float:
        """Calculate string similarity ratio."""
        return SequenceMatcher(None, a, b).ratio()
    
    def _calculate_episode_match_score(
        self,
        item_title: str,
        item_date: Optional[str],
        target_title: str,
        target_date: Optional[str]
    ) -> float:
        """
        Calculate how well an RSS item matches the target episode.
        
        Returns a score between 0 and 1.
        """
        score = 0.0
        
        # Title similarity (weight: 0.7)
        title_sim = self._similarity(
            item_title.lower(),
            target_title.lower()
        )
        score += title_sim * 0.7
        
        # Date match (weight: 0.3)
        if target_date and item_date:
            try:
                # Parse RSS date formats
                item_date_parsed = self._parse_rss_date(item_date)
                target_date_parsed = datetime.strptime(target_date, "%Y-%m-%d")
                
                if item_date_parsed and target_date_parsed:
                    # Same day = full points, within 3 days = partial
                    day_diff = abs((item_date_parsed.date() - target_date_parsed.date()).days)
                    if day_diff == 0:
                        score += 0.3
                    elif day_diff <= 3:
                        score += 0.2
                    elif day_diff <= 7:
                        score += 0.1
            except (ValueError, TypeError):
                pass
        
        # Bonus for exact keyword matches
        target_words = set(re.findall(r'\w+', target_title.lower()))
        item_words = set(re.findall(r'\w+', item_title.lower()))
        common_words = target_words & item_words
        if len(target_words) > 0:
            keyword_bonus = len(common_words) / len(target_words) * 0.2
            score = min(1.0, score + keyword_bonus)
        
        return score
    
    def _parse_rss_date(self, date_str: str) -> Optional[datetime]:
        """Parse various RSS date formats."""
        formats = [
            "%a, %d %b %Y %H:%M:%S %z",
            "%a, %d %b %Y %H:%M:%S %Z",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(date_str.strip(), fmt)
            except ValueError:
                continue
        
        # Try removing timezone suffix
        date_str_clean = re.sub(r'\s+[A-Z]{3,4}$', '', date_str)
        date_str_clean = re.sub(r'\s+[+-]\d{4}$', '', date_str_clean)
        
        for fmt in formats:
            try:
                return datetime.strptime(date_str_clean.strip(), fmt)
            except ValueError:
                continue
        
        return None
    
    def _get_text(self, element: ET.Element, tag: str) -> Optional[str]:
        """Safely get text content of a child element."""
        child = element.find(tag)
        if child is not None and child.text:
            return child.text.strip()
        return None


# Convenience function for direct usage
def get_podcast_audio(
    show_name: str,
    episode_title: str,
    release_date: Optional[str] = None,
    duration_ms: Optional[int] = None
) -> Optional[Dict]:
    """
    Convenience function to get podcast episode audio URL.
    
    Args:
        show_name: Name of the podcast
        episode_title: Title of the episode
        release_date: Release date (YYYY-MM-DD)
        duration_ms: Duration in milliseconds
        
    Returns:
        dict with audio_url and metadata, or None if not found
    """
    client = iTunesRSSClient()
    return client.get_episode_audio(show_name, episode_title, release_date, duration_ms)


if __name__ == "__main__":
    # Test the client
    import sys
    
    if len(sys.argv) < 3:
        print("Usage: python itunes_rss.py <show_name> <episode_title> [release_date]")
        print("Example: python itunes_rss.py '神保町で会いましょう' '異星人の目で街を見る' '2025-12-26'")
        sys.exit(1)
    
    show = sys.argv[1]
    episode = sys.argv[2]
    date = sys.argv[3] if len(sys.argv) > 3 else None
    
    result = get_podcast_audio(show, episode, date)
    
    if result:
        print("\n" + "=" * 50)
        print("✅ SUCCESS")
        print("=" * 50)
        print(f"Audio URL: {result['audio_url']}")
        print(f"Podcast: {result['podcast_name']}")
        print(f"Episode: {result['episode_title']}")
    else:
        print("\n❌ Failed to find episode audio")
        sys.exit(1)






