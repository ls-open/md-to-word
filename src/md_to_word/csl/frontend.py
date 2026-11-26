import os

from lxml import etree

from . import LOCALES_PATH
from .formatter import segments
from .model import CitationStylesElement


class CitationStylesXML:
    def __init__(self, f):
        lookup = etree.ElementNamespaceClassLookup()
        namespace = lookup.get_namespace('http://purl.org/net/xbiblio/csl')
        namespace[None] = CitationStylesElement
        namespace.update(dict([(cls.__name__.replace('_', '-').lower(), cls)
                               for cls in CitationStylesElement.__subclasses__()]))

        self.parser = etree.XMLParser(remove_comments=True, encoding='UTF-8',
                                      no_network=True)
        self.parser.set_element_class_lookup(lookup)
        self.xml = etree.parse(f, self.parser)
        self.root = self.xml.getroot()


class CitationStylesLocale(CitationStylesXML):
    def __init__(self, locale):
        locale_path = os.path.join(LOCALES_PATH, f'locales-{locale}.xml')
        try:
            super().__init__(locale_path)
        except OSError:
            raise ValueError(f"'{locale}' is not a known locale") from None


class CitationStylesStyle(CitationStylesXML):
    def __init__(self, style, locale=None):
        if not isinstance(style, str):
            style_src = style
        elif os.path.exists(style):
            style_src = style
        else:
            raise ValueError(f"'{style}' is not a known style")

        try:
            super().__init__(style_src)
        except OSError:
            raise ValueError(f"'{style}' is not a known style") from None
        if locale is None:
            locale = self.root.get('default-locale', 'en-US')
        self.root.set_locale_list(locale)

    def has_bibliography(self):
        return self.root.bibliography is not None

    def render_citation(self, citation, cites, callback=None):
        return self.root.citation.render(citation, cites, callback)

    def render_bibliography(self, citation_items):
        return self.root.bibliography.render(citation_items)


class CitationStylesBibliography:
    def __init__(self, style, source, formatter=segments):
        self.style = style
        self.source = source
        self.formatter = self.style.root.formatter = formatter
        self.keys = []
        self.items = []
        self._cites = []

    def register(self, citation, callback=None):
        citation.bibliography = self
        for item in citation.cites:
            if item.key in self.source:
                if item.key not in self.keys:
                    self.keys.append(item.key)
                    self.items.append(item)
            elif callback is not None:
                callback(item)

    def cite(self, citation, callback):
        return self.style.render_citation(citation, self._cites, callback)

    def bibliography(self):
        return self.style.render_bibliography(self.items)
