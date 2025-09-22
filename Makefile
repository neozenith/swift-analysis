layout_folders:
	uv run scripts/process_albums_to_lyrics_structure.py

fetch_lyrics: layout_folders
	uv run scripts/fetch_lyrics_for_tracks.py

analyse: fetch_lyrics
	uv run scripts/analyse_lyrics_cuss_words.py

vis: analyse
	uv run -m http.server 8008 --directory site/