#!/usr/bin/env python
# /// script
# requires-python = ">=3.12"
# dependencies = [
# ]
# ///

"""
Process studio albums markdown file to create lyrics folder structure and JSON metadata.

This script parses the studio-albums.md file and:
1. Creates a folder structure under lyrics/ with YEAR/ALBUM/track format
2. Generates a structured JSON file with album and track metadata
"""

import argparse
import json
import logging
import re
from pathlib import Path
from textwrap import dedent

log = logging.getLogger(__name__)

# Configuration
SCRIPT = Path(__file__)
SCRIPT_NAME = SCRIPT.stem
SCRIPT_DIR = SCRIPT.parent.resolve()
PROJECT_ROOT = SCRIPT_DIR.parent

# Input/Output paths
INPUT_FILE = PROJECT_ROOT / "studio-albums.md"
OUTPUT_DIR = PROJECT_ROOT / "lyrics"
OUTPUT_JSON = PROJECT_ROOT / "albums_metadata.json"


def sanitize_for_path(text: str) -> str:
    """
    Sanitize text for use in file/folder names.
    - Replace spaces with underscores
    - Replace other invalid characters with hyphens
    """
    # First, replace spaces with underscores
    text = text.replace(" ", "_")

    # Replace common invalid path characters with hyphens
    # Keep parentheses, letters, numbers, underscores, and hyphens
    invalid_chars = r'[<>:"/\\|?*]'
    text = re.sub(invalid_chars, "-", text)

    # Replace other problematic characters
    text = text.replace("'", "-")
    text = text.replace(",", "-")
    text = text.replace(".", "-")
    text = text.replace("!", "-")
    text = text.replace("&", "-")
    text = text.replace("...", "-")

    # Clean up multiple hyphens
    text = re.sub(r'-+', '-', text)

    # Remove trailing/leading hyphens or underscores
    text = text.strip('-_')

    return text


def parse_albums_file(file_path: Path) -> list[dict]:
    """
    Parse the studio albums markdown file.

    Returns a list of album dictionaries with tracks.
    """
    albums = []
    current_album = None
    track_number = 0

    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    for line in lines:
        line = line.strip()

        # Check for album header
        if line.startswith('## album:'):
            # Extract album title and year using regex
            match = re.match(r'## album: "([^"]+)" \((\d{4})\)', line)
            if match:
                album_title = match.group(1)
                year = match.group(2)

                # Save previous album if exists
                if current_album:
                    albums.append(current_album)

                # Start new album
                current_album = {
                    'title': album_title,
                    'year': year,
                    'sanitized_title': sanitize_for_path(album_title),
                    'tracks': []
                }
                track_number = 0
                log.debug(f"Found album: {album_title} ({year})")

        # Check for track (non-empty line that's not a header and not bonus track indicator)
        elif line and not line.startswith('#') and current_album:
            # Skip lines that are just bonus track indicators
            if line.startswith('(') and line.endswith(')'):
                continue

            # This is a track
            track_number += 1
            track = {
                'number': track_number,
                'title': line,
                'sanitized_title': sanitize_for_path(line)
            }
            current_album['tracks'].append(track)
            log.debug(f"  Track {track_number}: {line}")

    # Don't forget the last album
    if current_album:
        albums.append(current_album)

    return albums


def create_folder_structure(albums: list[dict], output_dir: Path, dry_run: bool = False):
    """
    Create the folder structure for lyrics based on parsed albums.
    """
    created_paths = []

    for album in albums:
        year = album['year']
        album_name = album['sanitized_title']

        # Create album directory
        album_dir = output_dir / f"YEAR={year}" / f"ALBUM={album_name}"

        if not dry_run:
            album_dir.mkdir(parents=True, exist_ok=True)
            log.info(f"Created directory: {album_dir.relative_to(PROJECT_ROOT)}")
        else:
            log.info(f"DRY RUN: Would create directory: {album_dir.relative_to(PROJECT_ROOT)}")

        # Create track files
        for track in album['tracks']:
            track_num = str(track['number']).zfill(2)
            track_title = track['sanitized_title']
            track_file = album_dir / f"{track_num}_{track_title}.md"

            if not dry_run:
                track_file.touch(exist_ok=True)
                log.debug(f"  Created file: {track_file.name}")
            else:
                log.debug(f"  DRY RUN: Would create file: {track_file.name}")

            created_paths.append(str(track_file.relative_to(PROJECT_ROOT)))

    return created_paths


def save_metadata(albums: list[dict], output_path: Path, dry_run: bool = False):
    """
    Save the structured album metadata to a JSON file.
    """
    # Create metadata structure
    metadata = {
        'total_albums': len(albums),
        'total_tracks': sum(len(album['tracks']) for album in albums),
        'albums': []
    }

    for album in albums:
        album_data = {
            'title': album['title'],
            'year': album['year'],
            'sanitized_title': album['sanitized_title'],
            'track_count': len(album['tracks']),
            'folder_path': f"lyrics/YEAR={album['year']}/ALBUM={album['sanitized_title']}",
            'tracks': []
        }

        for track in album['tracks']:
            track_data = {
                'number': track['number'],
                'title': track['title'],
                'sanitized_title': track['sanitized_title'],
                'file_path': f"{album_data['folder_path']}/{str(track['number']).zfill(2)}_{track['sanitized_title']}.md"
            }
            album_data['tracks'].append(track_data)

        metadata['albums'].append(album_data)

    if not dry_run:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        log.info(f"Saved metadata to: {output_path.relative_to(PROJECT_ROOT)}")
    else:
        log.info(f"DRY RUN: Would save metadata to: {output_path.relative_to(PROJECT_ROOT)}")

    return metadata


def main(dry_run: bool = False):
    """Main processing function."""

    # Check if input file exists
    if not INPUT_FILE.exists():
        log.error(f"Input file not found: {INPUT_FILE}")
        return

    log.info(f"Processing: {INPUT_FILE.relative_to(PROJECT_ROOT)}")

    # Parse the albums file
    albums = parse_albums_file(INPUT_FILE)
    log.info(f"Found {len(albums)} albums")

    # Create folder structure
    created_paths = create_folder_structure(albums, OUTPUT_DIR, dry_run=dry_run)
    log.info(f"Created {len(created_paths)} track files")

    # Save metadata
    metadata = save_metadata(albums, OUTPUT_JSON, dry_run=dry_run)
    log.info(f"Total tracks processed: {metadata['total_tracks']}")

    # Summary
    log.info("\nSummary:")
    for album in albums:
        log.info(f"  {album['title']} ({album['year']}): {len(album['tracks'])} tracks")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=dedent(f"""\
        {SCRIPT_NAME} - Parse studio albums and create lyrics folder structure

        INPUTS:
        - studio-albums.md

        OUTPUTS:
        - lyrics/ folder structure (YEAR=YYYY/ALBUM=Name/XX_Track_Title.md)
        - albums_metadata.json

        This script parses the studio albums markdown file and creates:
        1. A folder structure for lyrics organized by year and album
        2. A JSON metadata file with structured album and track information
        """)
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging")
    parser.add_argument("-q", "--quiet", action="store_true", help="Show only errors")
    parser.add_argument("-n", "--dry-run", action="store_true",
                       help="Run without creating files/folders")

    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.ERROR if args.quiet else logging.INFO,
        format="%(asctime)s|%(name)s|%(levelname)s|%(filename)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    main(dry_run=args.dry_run)