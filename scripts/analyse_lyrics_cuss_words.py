#!/usr/bin/env python
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///

import json
import logging
import argparse
from pathlib import Path
from collections import defaultdict
from textwrap import dedent

log = logging.getLogger(__name__)

SCRIPT = Path(__file__)
SCRIPT_NAME = SCRIPT.stem
SCRIPT_DIR = SCRIPT.parent.resolve()
PROJECT_ROOT = SCRIPT_DIR.parent

# Input/Output configuration
LYRICS_DIR = PROJECT_ROOT / "lyrics"
OUTPUT_DIR = PROJECT_ROOT / "site"
OUTPUT_FILE = OUTPUT_DIR / "cuss_word_analysis.json"

# List of words to search for
CUSS_WORDS = ['whore', 'damn', 'goddamn', 'hell', 'bitch', 'shit', 'fuck', 'dickhead']

def analyze_lyrics():
    """Analyze all lyrics files for occurrences of specific words."""
    results = {}

    # Iterate through all year/album directories
    for year_dir in sorted(LYRICS_DIR.glob("YEAR=*")):
        year = year_dir.name.split("=")[1]

        for album_dir in sorted(year_dir.glob("ALBUM=*")):
            album_name = album_dir.name.split("=")[1].replace("_", " ")
            album_key = f"{year} - {album_name}"

            log.info(f"Processing album: {album_key}")

            # Initialize counts for this album
            album_counts = {word: 0 for word in CUSS_WORDS}
            total_songs = 0

            # Process each song in the album
            for song_file in sorted(album_dir.glob("*.md")):
                total_songs += 1
                content = song_file.read_text(encoding="utf-8").lower()

                # Count occurrences of each word
                for word in CUSS_WORDS:
                    # Use word boundaries to match whole words only
                    count = content.count(word.lower())
                    album_counts[word] += count

                    if count > 0:
                        log.debug(f"  Found {count} instance(s) of '{word}' in {song_file.name}")

            # Store results
            results[album_key] = {
                "year": int(year),
                "album": album_name,
                "total_songs": total_songs,
                "word_counts": album_counts,
                "total_count": sum(album_counts.values())
            }

            if results[album_key]["total_count"] > 0:
                log.info(f"  Total instances: {results[album_key]['total_count']}")

    return results

def main(dry_run: bool = False):
    """Main function to analyze lyrics and save results."""

    if not LYRICS_DIR.exists():
        log.error(f"Lyrics directory not found: {LYRICS_DIR}")
        return

    log.info(f"Analyzing lyrics for words: {CUSS_WORDS}")

    # Analyze lyrics
    results = analyze_lyrics()

    # Sort results by year and album
    sorted_results = dict(sorted(results.items(), key=lambda x: (x[1]["year"], x[1]["album"])))

    # Output summary
    log.info("\n=== SUMMARY ===")
    total_across_all = 0
    for album_key, data in sorted_results.items():
        if data["total_count"] > 0:
            log.info(f"{album_key}: {data['total_count']} total instances")
            for word, count in data["word_counts"].items():
                if count > 0:
                    log.info(f"  - {word}: {count}")
            total_across_all += data["total_count"]

    log.info(f"\nTotal instances across all albums: {total_across_all}")

    if not dry_run:
        # Create output directory
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        # Save results to JSON
        OUTPUT_FILE.write_text(json.dumps(sorted_results, indent=2), encoding="utf-8")
        log.info(f"\nResults saved to: {OUTPUT_FILE.relative_to(PROJECT_ROOT)}")
    else:
        log.info("\nDRY RUN: Would save results to JSON file")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=dedent(f"""\
        {SCRIPT_NAME} - Analyze lyrics for specific word occurrences

        INPUTS:
        - {LYRICS_DIR.relative_to(PROJECT_ROOT)}/YEAR=*/ALBUM=*/*.md

        OUTPUTS:
        - {OUTPUT_FILE.relative_to(PROJECT_ROOT)}

        Searches for: {', '.join(CUSS_WORDS)}
        """)
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose output")
    parser.add_argument("-q", "--quiet", action="store_true", help="Show only errors")
    parser.add_argument("-n", "--dry-run", action="store_true", help="Run without saving output")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.ERROR if args.quiet else logging.INFO,
        format="%(asctime)s|%(name)s|%(levelname)s|%(filename)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    main(dry_run=args.dry_run)