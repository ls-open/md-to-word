
import json
import os

from . import formatter

LOCALES_PATH = os.path.join(
    os.path.abspath(os.path.dirname(__file__)), 'data', 'locales')


# CSL 1.0.2 的全部 name 变量。漏一个，Zotero/CSL-JSON 里该角色会被当成普通
# 字符串塞进 Reference，渲染时 `Name.process` 调 `.parts()` 直接崩。
NAMES = ['author', 'chair', 'collection_editor', 'compiler', 'composer',
         'container_author', 'contributor', 'curator', 'director', 'editor',
         'editorial_director', 'editor_translator', 'executive_producer',
         'guest', 'host', 'illustrator', 'interviewer', 'narrator',
         'organizer', 'original_author', 'performer', 'producer', 'recipient',
         'reviewed_author', 'script_writer', 'series_creator', 'translator']

DATES = ['accessed', 'available_date', 'container', 'event_date', 'issued',
         'original_date', 'submitted']

NUMBERS = ['chapter_number', 'collection_number', 'edition', 'issue', 'number',
           'number_of_pages', 'number_of_volumes', 'volume']

VARIABLES = (['abstract', 'annote', 'archive', 'archive_location',
              'archive_place', 'authority', 'call_number', 'citation_label',
              'citation_number', 'collection_title', 'container_title',
              'container_title_short', 'dimensions', 'DOI', 'event',
              'event_place', 'first_reference_note_number', 'genre', 'ISBN',
              'ISSN', 'jurisdiction', 'keyword', 'language', 'locator',
              'medium', 'note', 'original_publisher',
              'original_publisher_place', 'original_title', 'page',
              'page_first', 'PMCID', 'PMID', 'publisher', 'publisher_place',
              'references', 'section', 'source', 'status', 'title',
              'title_short', 'URL', 'version', 'year_suffix'] +
             NAMES + DATES + NUMBERS)

with open(os.path.join(LOCALES_PATH, 'locales.json'),
          encoding='utf-8') as file:
    locales_json = json.load(file)
    PRIMARY_DIALECTS = locales_json['primary-dialects']
    LANGUAGE_NAMES = locales_json['language-names']


from .frontend import CitationStylesBibliography, CitationStylesStyle  # noqa: E402
from .source import Citation, CitationItem, Locator  # noqa: E402

__all__ = [
    'Citation',
    'CitationItem',
    'CitationStylesBibliography',
    'CitationStylesStyle',
    'DATES',
    'LANGUAGE_NAMES',
    'LOCALES_PATH',
    'Locator',
    'NAMES',
    'NUMBERS',
    'PRIMARY_DIALECTS',
    'VARIABLES',
    'formatter',
]
