import os

def replace_in_file(filepath, replacements):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    for old, new in replacements:
        content = content.replace(old, new)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

index_replacements = [
    ('> Manga Library<', '> Collection<'),
    ('>Online Manga<', '>Online Media<'),
    ('READ MANGA Button', 'VIEW COLLECTION Button'),
    ('READ MANGA', 'VIEW COLLECTION'),
    ('Manga Viewer window', 'Collection Viewer window'),
    ('>Manga Viewer<', '>Collection Viewer<'),
    ('Online Manga Browser', 'Online Images/Videos'),
    ('Unmark as Manga', 'Unmark as Collection'),
]
replace_in_file('web/index.html', index_replacements)

app_replacements = [
    ('Mark as Manga Folder', 'Make Collection'),
    ('Unmark as Manga', 'Unmark as Collection'),
    ('Loading manga library...', 'Loading collection...'),
    ('Rename manga', 'Rename collection'),
    ('delete the manga', 'delete the collection'),
]
replace_in_file('web/app.js', app_replacements)

viewer_replacements = [
    ('setWindowTitle("Manga Viewer")', 'setWindowTitle("Collection Viewer")'),
    ('setWindowTitle(f"Manga Viewer - TRANSLATING...")', 'setWindowTitle(f"Collection Viewer - TRANSLATING...")'),
    ('Manga Name:', 'Collection Name:'),
    ('Enter Manga Name...', 'Enter Collection Name...'),
    ('Manga info saved successfully', 'Collection info saved successfully'),
]
replace_in_file('MangaViewer.py', viewer_replacements)

print('Replacements done.')
