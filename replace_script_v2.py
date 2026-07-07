import os
import re

def process_file(filepath):
    if not os.path.exists(filepath):
        print(f"Skipping {filepath}, does not exist")
        return
        
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Rename marker and info files
    content = content.replace('.manga', '.collection')
    content = content.replace('manga_info.json', 'collection_info.json')

    # Rename HTML IDs / JS variables / Python methods
    replacements = {
        'openMangaLibrary': 'openCollectionLibrary',
        'closeMangaLibrary': 'closeCollectionLibrary',
        'renderMangaLibrary': 'renderCollectionLibrary',
        'openOnlineManga': 'openOnlineMedia',
        'closeOnlineManga': 'closeOnlineMedia',
        'searchOnlineManga': 'searchOnlineMedia',
        'mangaLibrary': 'collectionLibrary',
        'manga-library': 'collection-library',
        'read-manga-btn': 'view-collection-btn',
        'is_manga_folder': 'is_collection_folder',
        'is_manga': 'is_collection',
        'manga_sites': 'collection_sites',
        'manga_download_dir': 'collection_download_dir',
        'known_manga_folders': 'known_collection_folders',
        'online-manga': 'online-media',
        'manga-sort': 'collection-sort',
        'manga-tag': 'collection-tag',
        'manga-source': 'collection-source',
        'manga-columns': 'collection-columns',
        'manga-direct': 'collection-direct',
        'manga-dl': 'collection-dl',
        'tab-manga': 'tab-collection',
        'manga-max-icon': 'collection-max-icon',
        'open_manga_viewer': 'open_collection_viewer',
        'open_manga_library': 'open_collection_library',
        'get_manga_library': 'get_collection_library',
        'delete_manga_folder': 'delete_collection_folder',
        'rename_manga': 'rename_collection',
        'unmark_folder_as_manga': 'unmark_folder_as_collection',
        'mark_as_manga': 'mark_as_collection',
        'unmark_as_manga': 'unmark_as_collection',
        'save_manga_info': 'save_collection_info',
        'get_manga_info': 'get_collection_info',
        'MangaViewer': 'CollectionViewer',
        'mangaViewer': 'collectionViewer',
        'manga_translations': 'collection_translations',
        'get_manga_details': 'get_collection_details',
        'choose_manga_download_dir': 'choose_collection_download_dir',
        'get_manga_download_dir': 'get_collection_download_dir',
        'downloadDirectMangaUrl': 'downloadDirectCollectionUrl',
        'favorite_manga_tags': 'favorite_collection_tags',
        'save_favorite_manga_tags': 'save_favorite_collection_tags',
        'clean_manga_directory': 'clean_collection_directory',
    }

    # Sort replacements by length descending to prevent partial replacements
    for k in sorted(replacements.keys(), key=len, reverse=True):
        content = content.replace(k, replacements[k])

    # UI Text (specific phrases first)
    content = content.replace('Manga Library', 'Collection Library')
    content = content.replace('Online Manga', 'Online Media')
    content = content.replace('READ MANGA', 'VIEW COLLECTION')
    content = content.replace('Manga Viewer', 'Collection Viewer')
    content = content.replace('Mark as Manga Folder', 'Make Collection')
    content = content.replace('Mark as Manga', 'Make Collection')
    content = content.replace('Unmark as Manga', 'Unmark as Collection')
    content = content.replace('Online Images/Videos Browser', 'Online Images/Videos')
    content = content.replace('Online Manga Browser', 'Online Images/Videos')

    # General word replacements (safe cases)
    content = re.sub(r'\bManga\b', 'Collection', content)
    content = re.sub(r'\bmanga\b', 'collection', content)
    content = re.sub(r'\bMANGA\b', 'COLLECTION', content)
    
    # Reverts for specific third-party tools/names
    content = content.replace('Collection OCR', 'Manga OCR')
    content = content.replace('collection-ocr', 'manga-ocr')
    content = content.replace('CollectionDex', 'MangaDex')

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

for file in ['web/index.html', 'web/app.js', 'XenoPlayer.py', 'MangaViewer.py']:
    process_file(file)

if os.path.exists('MangaViewer.py'):
    os.rename('MangaViewer.py', 'CollectionViewer.py')

print('Replacements complete.')
