#!/usr/bin/env python
# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "requests>=2.31.0",
#   "beautifulsoup4>=4.12.0",
#   "lxml>=4.9.0",
#   "tqdm"
# ]
# ///

"""
Fetch lyrics for tracks from albums_metadata.json using web scraping.

This script iterates through the tracks in albums_metadata.json and attempts
to fetch lyrics from public sources, saving them to the appropriate files.
"""

import argparse
import json
import logging
import re
import time
from pathlib import Path
from textwrap import dedent
from urllib.parse import quote_plus
from tqdm import tqdm

import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

# Configuration
SCRIPT = Path(__file__)
SCRIPT_NAME = SCRIPT.stem
SCRIPT_DIR = SCRIPT.parent.resolve()
PROJECT_ROOT = SCRIPT_DIR.parent

# Input/Output paths
METADATA_FILE = PROJECT_ROOT / "albums_metadata.json"
CACHE_DIR = PROJECT_ROOT / "tmp" / "claude_cache" / SCRIPT_NAME

# Rate limiting
REQUEST_DELAY = 1.5  # Seconds between requests to be respectful
MAX_RETRIES = 3
TIMEOUT = 10

# User agent to identify our script
USER_AGENT = "Mozilla/5.0 (Educational Lyrics Research Script)"


def load_metadata(metadata_path: Path) -> dict:
    """Load the albums metadata from JSON file."""
    with open(metadata_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def clean_artist_name(text: str) -> str:
    """Clean artist name for search - remove special characters."""
    # Remove special characters but keep spaces
    cleaned = re.sub(r'[^\w\s]', '', text)
    return cleaned.strip()


def clean_song_title(text: str) -> str:
    """Clean song title for search - remove parenthetical content and special chars."""
    # Remove content in parentheses for search
    cleaned = re.sub(r'\([^)]*\)', '', text)
    # Remove special characters but keep spaces
    cleaned = re.sub(r'[^\w\s]', '', cleaned)
    return cleaned.strip()


def search_lyrics_genius(artist: str, title: str, session: requests.Session) -> str | None:
    """
    Search for lyrics on Genius.com (public website).

    Returns the lyrics text or None if not found.
    """
    # Clean inputs for search
    clean_artist = clean_artist_name(artist)
    clean_title = clean_song_title(title)

    # Construct search URL
    search_query = f"{clean_artist} {clean_title}"
    search_url = f"https://genius.com/api/search/multi?q={quote_plus(search_query)}"

    try:
        # Search for the song
        headers = {'User-Agent': USER_AGENT}
        response = session.get(search_url, headers=headers, timeout=TIMEOUT)
        response.raise_for_status()

        data = response.json()

        # Find the first song result
        sections = data.get('response', {}).get('sections', [])
        for section in sections:
            if section.get('type') == 'song':
                hits = section.get('hits', [])
                if hits:
                    # Get the URL of the first matching song
                    song_url = hits[0].get('result', {}).get('url')
                    if song_url:
                        return fetch_lyrics_from_genius_url(song_url, session)

        log.warning(f"No results found for: {artist} - {title}")
        return None

    except Exception as e:
        log.error(f"Error searching Genius for {artist} - {title}: {e}")
        return None


def clean_lyrics_text(lyrics: str, title: str) -> str:
    """Remove metadata cruft from fetched lyrics.

    Filters out:
    - Contributor count lines
    - Translation language lists
    - Song title with 'Lyrics' suffix
    - Background information paragraphs
    - 'Read More' links
    """
    lines = lyrics.split('\n')
    cleaned_lines = []
    skip_metadata = True

    # Common language names to filter
    languages = {
        'Türkçe', 'Español', 'Français', 'Deutsch', 'Italiano',
        'Português', 'Polski', 'Svenska', 'Afrikaans', 'srpski',
        'Українська', 'Беларуская', 'Slovenščina', '日本語', '中文',
        'Русский', 'العربية', 'हिन्दी', 'Nederlands', 'Norsk'
    }

    for line in lines:
        line_stripped = line.strip()

        # Skip empty lines at the beginning
        if skip_metadata and not line_stripped:
            continue

        # Skip contributor lines
        if 'Contributors' in line_stripped or 'Contributor' in line_stripped:
            continue

        # Skip "Translations" header
        if line_stripped == 'Translations':
            continue

        # Skip language names
        if line_stripped in languages:
            continue

        # Skip the "Song Title Lyrics" line
        if line_stripped.endswith(' Lyrics') and title in line_stripped:
            continue

        # Skip "Read More" lines
        if line_stripped == 'Read More':
            continue

        # Detect start of actual lyrics - usually starts with [Verse, [Chorus, [Intro, etc
        # or starts with quotes or regular text that's not metadata
        if skip_metadata and (
            line_stripped.startswith('[') or
            line_stripped.startswith('"') or
            (line_stripped and not any(x in line_stripped for x in ['Contributors', 'Translations', 'Lyrics']))
        ):
            # Check if this might be background info (usually longer sentences)
            # Background info typically contains "wrote", "was", "dating", etc.
            background_indicators = [
                'wrote', 'was', 'were', 'dated', 'dating', 'recorded',
                'released', 'produced', 'inspired', 'about', 'song is',
                'track is', 'single', 'album', 'This song', 'The song'
            ]

            if len(line_stripped) > 100 and any(indicator in line_stripped.lower() for indicator in background_indicators):
                continue

            skip_metadata = False

        # Once we're past metadata, include all lines
        if not skip_metadata:
            cleaned_lines.append(line)

    return '\n'.join(cleaned_lines).strip()


def fetch_lyrics_from_genius_url(url: str, session: requests.Session) -> str | None:
    """Fetch lyrics from a Genius song URL."""
    try:
        headers = {'User-Agent': USER_AGENT}
        response = session.get(url, headers=headers, timeout=TIMEOUT)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'lxml')

        # Genius stores lyrics in divs with data-lyrics-container="true"
        lyrics_divs = soup.find_all('div', {'data-lyrics-container': 'true'})

        if not lyrics_divs:
            log.warning(f"No lyrics container found at {url}")
            return None

        # Extract text from all lyrics containers
        lyrics_parts = []
        for div in lyrics_divs:
            # Get text and preserve line breaks
            text = div.get_text(separator='\n', strip=True)
            if text:
                lyrics_parts.append(text)

        return '\n\n'.join(lyrics_parts) if lyrics_parts else None

    except Exception as e:
        log.error(f"Error fetching lyrics from {url}: {e}")
        return None


def search_lyrics_azlyrics(artist: str, title: str, session: requests.Session) -> str | None:
    """
    Search for lyrics on AZLyrics (public website).

    Returns the lyrics text or None if not found.
    """
    # AZLyrics URL format: azlyrics.com/lyrics/artist/songtitle.html
    # Remove all non-alphanumeric characters and lowercase
    clean_artist = re.sub(r'[^a-z0-9]', '', artist.lower())
    clean_title = re.sub(r'[^a-z0-9]', '', title.lower())

    url = f"https://www.azlyrics.com/lyrics/{clean_artist}/{clean_title}.html"

    try:
        headers = {'User-Agent': USER_AGENT}
        response = session.get(url, headers=headers, timeout=TIMEOUT)

        if response.status_code == 404:
            log.debug(f"AZLyrics page not found for: {artist} - {title}")
            return None

        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')

        # Find the lyrics div (comes after a specific comment)
        lyrics_div = None
        for comment in soup.find_all(string=lambda text: isinstance(text, str) and "Usage of azlyrics.com content" in text):
            lyrics_div = comment.find_next('div')
            if lyrics_div:
                break

        if not lyrics_div:
            log.warning(f"No lyrics div found on AZLyrics for: {artist} - {title}")
            return None

        # Extract and clean lyrics
        lyrics = lyrics_div.get_text(separator='\n', strip=True)
        return lyrics if lyrics else None

    except Exception as e:
        log.error(f"Error fetching from AZLyrics for {artist} - {title}: {e}")
        return None


def save_lyrics(file_path: Path, lyrics: str, track_info: dict):
    """Save lyrics to the appropriate file with metadata header."""
    content = f"""# {track_info['title']}

Album: {track_info['album']}
Track: {track_info['number']}
Year: {track_info['year']}

---

{lyrics}
"""

    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)

    log.debug(f"Saved lyrics to: {file_path.relative_to(PROJECT_ROOT)}")


def fetch_lyrics_for_track(track: dict, album: dict, session: requests.Session,
                           force: bool = False) -> bool:
    """
    Fetch lyrics for a single track.

    Returns True if lyrics were fetched and saved, False otherwise.
    """
    file_path = PROJECT_ROOT / track['file_path']

    # Check if file already has content (unless force flag is set)
    if not force and file_path.exists() and file_path.stat().st_size > 0:
        log.debug(f"Skipping (already has content): {track['title']}")
        return False

    artist = "Taylor Swift"  # Hardcoded for this project
    title = track['title']

    log.debug(f"Fetching lyrics for: {title} ({album['title']})")

    # Try different sources
    lyrics = None

    # Try Genius first (usually most complete)
    lyrics = search_lyrics_genius(artist, title, session)

    # If not found, try AZLyrics as fallback
    if not lyrics:
        time.sleep(REQUEST_DELAY)  # Rate limit between different sources
        lyrics = search_lyrics_azlyrics(artist, title, session)

    # Clean the fetched lyrics to remove metadata cruft
    if lyrics:
        lyrics = clean_lyrics_text(lyrics, title)

    if lyrics:
        track_info = {
            'title': title,
            'album': album['title'],
            'number': track['number'],
            'year': album['year']
        }
        save_lyrics(file_path, lyrics, track_info)
        return True
    else:
        log.warning(f"Could not find lyrics for: {title}")
        # Do not save a file if failed to load.

        return False


def main(dry_run: bool = False, force: bool = False, limit: int | None = None,
         album_filter: str | None = None, year_filter: str | None = None):
    """Main processing function."""

    # Load metadata
    if not METADATA_FILE.exists():
        log.error(f"Metadata file not found: {METADATA_FILE}")
        return

    metadata = load_metadata(METADATA_FILE)
    log.info(f"Loaded metadata for {metadata['total_albums']} albums, {metadata['total_tracks']} tracks")

    # Create session for connection pooling
    session = requests.Session()

    # Statistics
    processed = 0
    successful = 0
    skipped = 0
    failed = 0

    # Process albums and tracks
    for album in metadata['albums']:
        # Apply filters if specified
        if album_filter and album_filter.lower() not in album['title'].lower():
            continue
        if year_filter and album['year'] != year_filter:
            continue

        title_string = f"ALBUM: {album['title']} ({album['year']})"
        log.info("=" * len(title_string))
        log.info(title_string)
        log.info("=" * len(title_string))

        for track in tqdm(album['tracks'], desc="Processing tracks", unit="track"):
            if limit and processed >= limit:
                log.info(f"Reached limit of {limit} tracks")
                break

            if dry_run:
                log.info(f"DRY RUN: Would fetch lyrics for: {track['title']}")
                processed += 1
                continue

            # Rate limiting
            if processed > 0:
                time.sleep(REQUEST_DELAY)

            # Fetch lyrics
            success = fetch_lyrics_for_track(track, album, session, force=force)

            processed += 1
            if success:
                successful += 1
            else:
                file_path = PROJECT_ROOT / track['file_path']
                if file_path.exists() and file_path.stat().st_size > 0 and not force:
                    skipped += 1
                else:
                    failed += 1

        if limit and processed >= limit:
            break

    # Summary
    log.info("\n" + "="*50)
    log.info("Summary:")
    log.info(f"  Total processed: {processed}")
    log.info(f"  Successfully fetched: {successful}")
    log.info(f"  Skipped (already exist): {skipped}")
    log.info(f"  Failed to fetch: {failed}")

    session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=dedent(f"""\
        {SCRIPT_NAME} - Fetch lyrics for all tracks in albums_metadata.json

        INPUTS:
        - albums_metadata.json

        OUTPUTS:
        - Lyrics files in lyrics/ directory structure

        This script fetches lyrics from public sources for educational purposes.
        It includes rate limiting to be respectful to source websites.

        Examples:
          # Fetch all missing lyrics
          uv run {SCRIPT_NAME}.py

          # Test with first 5 tracks
          uv run {SCRIPT_NAME}.py --limit 5

          # Fetch only for a specific album
          uv run {SCRIPT_NAME}.py --album "folklore"

          # Re-fetch all lyrics (overwrite existing)
          uv run {SCRIPT_NAME}.py --force
        """)
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging")
    parser.add_argument("-q", "--quiet", action="store_true", help="Show only errors")
    parser.add_argument("-n", "--dry-run", action="store_true",
                       help="Run without fetching (show what would be done)")
    parser.add_argument("-f", "--force", action="store_true",
                       help="Re-fetch lyrics even if files already have content")
    parser.add_argument("-L", "--limit", type=int,
                       help="Limit number of tracks to process")
    parser.add_argument("--album", dest="album_filter",
                       help="Filter to specific album (partial match)")
    parser.add_argument("--year", dest="year_filter",
                       help="Filter to specific year")

    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.ERROR if args.quiet else logging.INFO,
        format="%(asctime)s|%(name)s|%(levelname)s|%(filename)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    main(
        dry_run=args.dry_run,
        force=args.force,
        limit=args.limit,
        album_filter=args.album_filter,
        year_filter=args.year_filter
    )