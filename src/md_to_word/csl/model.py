
import re
import threading
import unicodedata
from contextvars import ContextVar
from functools import cmp_to_key
from operator import itemgetter

from lxml import etree

from . import DATES, LANGUAGE_NAMES, NAMES, NUMBERS, PRIMARY_DIALECTS
from .source import DateRange, LiteralDate, VariableError
from .string import String, join, normalize_seam

LANG_KEY = '{http://www.w3.org/XML/1998/namespace}lang'

CSL_NAMESPACE = 'http://purl.org/net/xbiblio/csl'


def _is_csl(node, *names):
    """`node` 是 CSL 命名空间下的 `names` 之一。"""
    tag = node.tag if node is not None else None
    return (isinstance(tag, str)
            and tag.startswith('{' + CSL_NAMESPACE + '}')
            and tag.rsplit('}', 1)[-1] in names)


def _ancestor(node, *names, include_self=False):
    """最近的 CSL 祖先（或自身）；xpath 的 `ancestor::…[1]` 慢在每次重新求值。"""
    if not include_self:
        node = node.getparent()
    while node is not None and not _is_csl(node, *names):
        node = node.getparent()
    return node


def _script_language(text):
    if re.search(r'[぀-ヿ]', text):
        return 'ja'
    if re.search(r'[Ѐ-ӿ]', text):
        return 'ru'
    if re.search(r'[㐀-鿿]', text):
        return 'zh'
    if re.search(r'[A-Za-zÀ-ɏ]', text):
        return 'en'
    return None


def item_language(item):
    """CSL-JSON `language` of the item, or a script-based inference.

    Terms are looked up per item, not per document: a Chinese paper can cite an
    English work, and GB/T 7714 requires `et al.` for that entry while Chinese
    entries use `等`. Many BibTeX entries omit `language`, so fall back to the
    script of the title (then the names) rather than the document locale.
    """
    if item is None:
        return None
    reference = getattr(item, 'reference', None)
    if reference is None:
        return None
    try:
        language = str(reference.language).strip()
    except (AttributeError, VariableError, KeyError):
        language = ''
    if language:
        return language

    title = reference.get('title')
    if title:
        inferred = _script_language(str(title))
        if inferred:
            return inferred
    for role in ('author', 'editor', 'translator'):
        people = reference.get(role) or []
        text = ' '.join(
            str(person.get('family') or person.get('literal') or '')
            for person in people
        )
        inferred = _script_language(text)
        if inferred:
            return inferred
    return None

# 消歧阶段由适配层写入；`<if disambiguate="true">` 在渲染期读取。
DISAMBIGUATE_KEYS: ContextVar[frozenset[str]] = ContextVar(
    "md2word_disambiguate_keys", default=frozenset()
)


class _ThreadLocalList:
    """每个线程一份的列表，接口与 `list` 相同。

    渲染期的 `<group>` / `<substitute>` 帧栈是可变状态；MCP 会在线程池里并发导出，
    模块级列表会让两个导出互相串帧，所以按线程转发。
    """

    def __init__(self) -> None:
        self._local = threading.local()

    @property
    def _items(self) -> list:
        try:
            return self._local.items
        except AttributeError:
            items: list = []
            self._local.items = items
            return items

    def __getitem__(self, index):
        return self._items[index]

    def __setitem__(self, index, value) -> None:
        self._items[index] = value

    def __delitem__(self, index) -> None:
        del self._items[index]

    def __len__(self) -> int:
        return len(self._items)

    def __bool__(self) -> bool:
        return bool(self._items)

    def __iter__(self):
        return iter(self._items)

    def __repr__(self) -> str:
        return repr(self._items)

    def append(self, value) -> None:
        self._items.append(value)

    def pop(self, index=-1):
        return self._items.pop(index)

    def clear(self) -> None:
        self._items.clear()


# [var_called, var_rendered]
group_frames = _ThreadLocalList()
# (parent_names_elem, staging_repressed)
sub_frames = _ThreadLocalList()


def _is_repressed(elem, var, context) -> bool:
    if not var:
        return False
    ctx = context if context is not None else elem
    try:
        repressed = getattr(ctx.get_layout(), "repressed", {})
    except Exception:
        return False
    for item_var in repressed.get(elem.tag, ()):
        if item_var and var in item_var.split():
            return True
    return False



# Base class
class SomewhatObjectifiedElement(etree.ElementBase):
    nsmap = {'cs': 'http://purl.org/net/xbiblio/csl',
             'xml': 'http://www.w3.org/XML/1998/namespace'}

    # TODO: what about multiple instances of the same name?
    def __getattr__(self, name):
        return self.find('cs:' + name, self.nsmap)


class CitationStylesElement(SomewhatObjectifiedElement):
    _default_options = {
                        # global options
                        'initialize-with-hyphen': 'true',
                        'page-range-format': None,
                        'demote-non-dropping-particle': 'display-and-sort',

                        # inheritable name(s) options
                        'and': None,
                        'delimiter-precedes-et-al': 'contextual',
                        'delimiter-precedes-last': 'contextual',
                        'et-al-min': 0,
                        'et-al-use-first': 1,
                        'et-al-subsequent-min': 0,
                        'et-al-subsequent-use-first': 1,
                        'et-al-use-last': 'false',
                        'initialize-with': None,
                        'name-as-sort-order': None,
                        'sort-separator': ', ',

                        'name-form': 'long',
                        'name-delimiter': ', ',
                        'names-delimiter': ''}

    def get_root(self):
        return self.getroottree().getroot()

    def xpath_search(self, expression):
        """带缓存的 XPath。

        样式树解析之后不再改动，查询（term、macro、date-part、子元素）结果都是固定的；
        lxml 每次重新求值要几十微秒，一次导出会问上万次。缓存挂在文档根上：lxml 只有
        在 Python 还引用着代理对象时才复用同一个代理，挂在元素自己身上会在代理回收后
        丢掉；以元素为键顺带把代理钉住。不同的样式副本各有各的树，互不影响。
        """
        root = self.get_root()
        cache = root.__dict__.get('_xpath_cache')
        if cache is None:
            cache = root.__dict__['_xpath_cache'] = {}
        key = (self, expression)
        result = cache.get(key)
        if result is None:
            result = self.xpath(expression, namespaces=self.nsmap)
            cache[key] = result
        return result

    def get_option(self, name):
        return self.get(name, self._default_options[name])

    def get_macro(self, name):
        expression = f"cs:macro[@name='{name}'][1]"
        return self.get_root().xpath_search(expression)[0]

    def get_layout(self):
        layout = _ancestor(self, 'layout', include_self=True)
        if layout is None:
            raise IndexError('no enclosing layout')
        return layout

    def get_formatter(self):
        if isinstance(self.get_root(), Locale):
            return self.get_root().style.formatter
        else:
            return self.get_root().formatter

    def preformat(self, text):
        return self.get_formatter().preformat(text)

    def unicode_character(self, name):
        return self.preformat(unicodedata.lookup(name))

    def render(self, *args, **kwargs):
        return self.markup(self.process(*args, **kwargs))

    # TODO: Locale methods
    def _locales_for(self, language):
        """Locale chain for one item, most specific first.

        The style's own locales keep their precedence; the document locale stays
        as fallback. A language missing from the chain (e.g. a French item in a
        Chinese paper) is loaded from the bundled locale files on demand.
        """
        root = self.get_root()
        locales = list(getattr(root, 'locales', ()) or ())
        language = str(language).replace('_', '-')
        base = language.split('-')[0].lower()

        def tag(locale):
            return (locale.get(LANG_KEY) or '').strip()

        # In-style `<locale>` elements have the style as parent; system locale
        # files are standalone roots. Style-level overrides must stay ahead of
        # the system locale for the item language (e.g. a generic `<locale>`
        # declaring the page-range delimiter as `-`).
        in_style = [locale for locale in locales if locale.getparent() is not None]
        system = [locale for locale in locales if locale.getparent() is None]

        def matches(locale):
            value = tag(locale)
            return bool(value) and (
                value.lower() == language.lower()
                or value.split('-')[0].lower() == base
            )

        preferred_in_style = [locale for locale in in_style if matches(locale)]
        generic_in_style = [locale for locale in in_style if not tag(locale)]
        preferred_system = [locale for locale in system if matches(locale)]
        rest = [locale for locale in locales
                if locale not in preferred_in_style
                and locale not in generic_in_style
                and locale not in preferred_system]
        if not preferred_system:
            extra = self._load_locale(language)
            if extra is not None:
                preferred_system = [extra]
        for group in (preferred_in_style, preferred_system):
            group.sort(key=lambda locale: 0 if tag(locale).lower() == language.lower() else 1)
        return preferred_in_style + generic_in_style + preferred_system + rest

    def _load_locale(self, language):
        root = self.get_root()
        cache = getattr(root, '_md2word_locale_cache', None)
        if cache is None:
            cache = {}
            root._md2word_locale_cache = cache
        key = language.lower()
        if key in cache:
            return cache[key]
        from .frontend import CitationStylesLocale

        code = language
        if '-' not in code:
            code = PRIMARY_DIALECTS.get(code.lower(), code)
        try:
            locale = CitationStylesLocale(code).root
        except (OSError, ValueError):
            cache[key] = None
            return None
        locale.style = root
        cache[key] = locale
        return locale

    def get_term(self, name, form=None, fallback_locale=True, zero_padded=False,
                 language=None):
        if isinstance(self.get_root(), Locale):
            return self.get_root().get_term(name, form)
        else:
            locales = (self._locales_for(language) if language
                       else self.get_root().locales)
            if not fallback_locale and len(locales) > 1:
                main_locale = locales[0]
                main_lg = main_locale.attrib.get(LANG_KEY, None)
                if main_lg:
                    new_locales = [main_locale]
                    for locale in locales[1::]:
                        if locale.get(LANG_KEY, main_lg) == main_lg:
                            new_locales.append(locale)
                    locales = new_locales
            for locale in locales:
                try:
                    return locale.get_term(name, form, zero_padded=zero_padded)
                except IndexError:  # TODO: create custom exception
                    continue

    def get_plural_term(self, name, *args, **kwargs):
        """
        Return plural form of the term or empty string if no term found
        """
        if (term := self.get_term(name, *args, **kwargs)) is not None:
            return term.multiple
        return String('')

    def get_single_term(self, name, *args, **kwargs):
        """
        Return singular form of the term or empty string if no term found
        """
        if (term := self.get_term(name, *args, **kwargs)) is not None:
            return term.single
        return String('')

    def get_date(self, form):
        for locale in self.get_root().locales:
            try:
                return locale.get_date(form)
            except IndexError:
                continue

    def get_locale_option(self, name):
        root = self.get_root()
        if not hasattr(root, 'locales') or root.locales is None:
            # root element is Locale, not an iterable of Locales
            return root.get_option(name)
        for locale in root.locales:
            try:
                return locale.get_option(name)
            except IndexError:
                continue


# Top level elements

class Style(CitationStylesElement):
    def set_locale_list(self, output_locale):
        """Set up list of locales in which to search for localizable units"""
        from .frontend import CitationStylesLocale

        self.locales = []
        system_locales_added = set()

        def add_instyle_locale(locale):
            expr = (f'./cs:locale[@xml:lang="{locale}"]'
                    if locale else './cs:locale[not(@xml:lang)]')
            results = self.xpath_search(expr)
            if results:
                locale_element, = results
                self.locales.append(locale_element)

        def add_system_locale(locale):
            if locale not in system_locales_added:
                csl_locale = CitationStylesLocale(locale)
                self.locales.append(csl_locale.root)
                system_locales_added.add(locale)

        # 1) (in-style locale) chosen dialect
        add_instyle_locale(output_locale)
        # 2) (in-style locale) matching language
        language = output_locale.split('-')[0]
        add_instyle_locale(language)
        # 3) (in-style locale) no language set
        add_instyle_locale(None)
        # 4) (locale files) chosen or primary dialect
        if output_locale in LANGUAGE_NAMES:
            add_system_locale(output_locale)
        # 5) (locale files) fall back to primary language dialect
        if language in PRIMARY_DIALECTS:
            add_system_locale(PRIMARY_DIALECTS[language])
        # 6) (locale files) default locale (en-US)
        add_system_locale('en-US')
        for locale in self.locales:
            locale.style = self


class Locale(CitationStylesElement):
    _default_options = {'limit-day-ordinals-to-day-1': 'false',
                        'punctuation-in-quote': 'false'}

    def get_term(self, name, form=None, zero_padded=False):
        attributes = f"@name='{name}'"
        if form is not None:
            attributes += f" and @form='{form}'"
        else:
            attributes += ' and not(@form)'
        if zero_padded:
            attributes += "and not(@match='whole-number')"
            attributes += "and not(@match='last-two-digits')"
        expr = f'./cs:term[{attributes}]'
        try:
            return self.terms.xpath_search(expr)[0]
        except AttributeError:
            raise IndexError from None

    def get_date(self, form):
        expr = f"./cs:date[@form='{form}']"
        return self.xpath_search(expr)[0]

    def get_option(self, name):
        options = self.find('cs:style-options', self.nsmap)
        if options is None:
            raise IndexError
        return options.get(name, self._default_options[name])

    def get_formatter(self):
        return self.style.formatter


class FormattingInstructions:
    def get_option(self, name):
        if name in self._default_options:
            return self.get(name, self._default_options[name])
        else:
            return self.get(name, self.get_root().get_option(name))

    def render(self, reference):
        raise NotImplementedError

    def layouts(self):
        return self.findall('cs:layout', self.nsmap)

    def default_layout(self):
        layouts = self.layouts()
        return next((layout for layout in layouts if not layout.get('locale')),
                    layouts[0] if layouts else None)

    def layout_for(self, item):
        """CSL-M: choose the layout whose `locale` matches the item language.

        GB/T's bilingual styles use one layout per language. Items without a
        language use the layout without a `locale` attribute.
        """
        language = item_language(item)
        if language:
            language = language.replace('_', '-').lower()
            base = language.split('-')[0]
            for layout in self.layouts():
                tag = (layout.get('locale') or '').lower()
                if tag and (tag == language or tag.split('-')[0] == base):
                    return layout
        return self.default_layout()


class Citation(FormattingInstructions, CitationStylesElement):
    _default_options = {
                        # disambiguation
                        'disambiguate-add-names': False,
                        'disambiguate-add-givenname': False,
                        'givenname-disambiguation-rule': 'all-names',
                        'disambiguate-add-year-suffix': False,

                        # citation collapsing
                        'collapse': None,
                        'year-suffix-delimiter': None,
                        'after-collapse-delimiter': None,

                        # note distance
                        'near-note-distance': 5}

    def render(self, citation, cites, callback):
        self.cites = cites
        return self.default_layout().render_citation(
            citation, callback, layout_for=self.layout_for)


class Bibliography(FormattingInstructions, CitationStylesElement):
    _default_options = {
                        # whitespace
                        'hanging-indent': False,
                        'second-field-align': None,
                        'line-spacing': 1,
                        'entry-spacing': 1,

                        # reference grouping
                        'subsequent-author-substitute': None}

    def render(self, citation_items):
        return self.default_layout().render_bibliography(
            citation_items, layout_for=self.layout_for)


# Style behavior

class Formatted:
    def format(self, string):
        if isinstance(string, (int, float)):
            string = str(string)
        text = self.font_style(string)
        text = self.font_variant(text)
        text = self.font_weight(text)
        text = self.text_decoration(text)
        text = self.vertical_align(text)
        return text

    def font_style(self, text):
        formatter = self.get_formatter()
        font_style = self.get('font-style', 'normal')
        if font_style == 'normal':
            formatted = text
        elif font_style == 'italic':
            formatted = formatter.Italic(text)
        elif font_style == 'oblique':
            formatted = formatter.Oblique(text)
        return formatted

    def font_variant(self, text):
        formatter = self.get_formatter()
        font_variant = self.get('font-variant', 'normal')
        if font_variant == 'normal':
            formatted = text
        elif font_variant == 'small-caps':
            formatted = formatter.SmallCaps(text)
        return formatted

    def font_weight(self, text):
        formatter = self.get_formatter()
        font_weight = self.get('font-weight', 'normal')
        if font_weight == 'normal':
            formatted = text
        elif font_weight == 'bold':
            formatted = formatter.Bold(text)
        elif font_weight == 'light':
            formatted = formatter.Light(text)
        return formatted

    def text_decoration(self, text):
        formatter = self.get_formatter()
        text_decoration = self.get('text-decoration', 'none')
        if text_decoration == 'none':
            formatted = text
        elif text_decoration == 'underline':
            formatted = formatter.Underline(text)
        return formatted

    def vertical_align(self, text):
        formatter = self.get_formatter()
        vertical_align = self.get('vertical-align', 'baseline')
        if vertical_align == 'baseline':
            formatted = text
        elif vertical_align == 'sup':
            formatted = formatter.Superscript(text)
        elif vertical_align == 'sub':
            formatted = formatter.Subscript(text)
        return formatted


class Affixed:
    def wrap(self, string):
        if string is not None:
            prefix = self.get('prefix', '')
            suffix = self.get('suffix', '')
            string = normalize_seam(prefix, string)
            # `String.__add__` keeps formatting objects intact; a raw `str +`
            # would flatten a structured run back to plain text.
            text = String(prefix) + string
            return text + normalize_seam(text, suffix)
        return None


class Delimited:
    def join(self, strings, default_delimiter=''):
        delimiter = self.get('delimiter', default_delimiter)
        try:
            text = join((s for s in strings if s is not None), delimiter)
        except Exception:
            text = String('')
        return text


class Displayed:
    pass


class Quoted:
    def quote(self, string, language=None):
        # `punctuation-in-quote` is handled once on the final runs (see
        # transform/citation_postprocess.py): the punctuation can come from a
        # group delimiter outside this element, so it is not visible here.
        if self.get('quotes', 'false').lower() == 'true':
            open_quote = self.get_single_term(name='open-quote', language=language)
            close_quote = self.get_single_term(name='close-quote', language=language)
            string = open_quote + string + close_quote
        return string


class StrippedPeriods:
    def strip_periods(self, string):
        strip_periods = self.get('strip-periods', 'false').lower() == 'true'
        if strip_periods:
            string = string.replace('.', '')
        return string


class TextCased:
    _stop_words = ['a', 'an', 'and', 'as', 'at', 'but', 'by', 'down', 'for',
                   'from', 'in', 'into', 'nor', 'of', 'on', 'onto', 'or',
                   'over', 'so', 'the', 'till', 'to', 'up', 'via', 'with',
                   'yet']

    def case(self, text, language=None):
        text_case = self.get('text-case')
        if text_case is not None:
            if language != 'en' and text_case == 'title':
                return text
            if text_case == 'lowercase':
                text = text.lower()
            elif text_case == 'uppercase':
                text = text.upper()
            elif text_case == 'capitalize-first':
                text = text.capitalize_first()
            elif text_case == 'capitalize-all':
                output = []
                for word in text.words():
                    word = word.capitalize_first()
                    output.append(word)
                text = ' '.join(output)
            elif text_case == 'title':
                output = []
                prev = ':'   # This ensures first word is capitilized
                for word in text.words():
                    if word.islower() and (str(word) not in self._stop_words or
                        prev in (':', '.')):
                        word = word.capitalize_first()
                    elif word.islower():  # Lowercase stop words
                        word = word.soft_lower()
                    prev = word[-1]
                    output.append(word)
                text = ' '.join(output)
            elif text_case == 'sentence':
                output = []
                for i, word in enumerate(text.words()):
                    if not text.isupper() and not word.isupper():
                        word = word.soft_lower()
                    if i == 0:
                        word = word.capitalize_first()
                    output.append(word)
                text = ' '.join(output)
        return text


# Locale elements

class Term(CitationStylesElement):
    @property
    def single(self):
        try:
            text = self.find('cs:single', self.nsmap).text
        except AttributeError:
            text = self.text
        text = self.preformat(text or '')
        return String(text)

    @property
    def multiple(self):
        try:
            text = self.find('cs:multiple', self.nsmap).text
        except AttributeError:
            text = self.text
        text = self.preformat(text or '')
        return String(text)


# Sorting elements

class Sort(CitationStylesElement):
    def sort(self, items, context):
        # custom sort function to push items with None keys to bottom
        def multi_key_sort(items, keys, descending):
            lst = zip(items, *keys)
            comparers = [(itemgetter(i + 1), descending[i])
                         for i in range(len(keys))]

            def mycmp(left, right):
                for getter, desc in comparers:
                    left_key, right_key = getter(left), getter(right)
                    if left_key is not None and right_key is not None:
                        try:
                            left_key = str(left_key.lower())
                            right_key = str(right_key.lower())
                        except AttributeError:
                            pass
                        try:
                            left_key, right_key = (int(str(left_key)),
                                                   int(str(right_key)))
                        except ValueError:
                            pass
                        result = (left_key > right_key) - (left_key < right_key)
                        if result:
                            return -1 * result if desc else result
                    elif left_key is not None:
                        return -1
                    elif right_key is not None:
                        return 1
                    else:
                        continue
                else:
                    return 0

            sorted_lst = sorted(lst, key=cmp_to_key(mycmp))
            return [item[0] for item in sorted_lst]

        sort_descending = []
        sort_keys = []
        for key in self.findall('cs:key', self.nsmap):
            descending = key.get('sort', 'ascending').lower() == 'descending'
            sort_descending.append(descending)
            sort_keys.append(key.sort_keys(items, context))

        return multi_key_sort(items, sort_keys, sort_descending)


class Key(CitationStylesElement):
    def sort_keys(self, items, context):
        if 'variable' in self.attrib:
            variable = self.get('variable').replace('-', '_')
            if variable in NAMES:
                sort_keys = [self._format_name(item, variable)
                             for item in items]
            elif variable in DATES:
                sort_keys = []
                for item in items:
                    date = item.reference.get(variable)
                    if date is not None:
                        sort_keys.append(date.sort_key())
                    else:
                        sort_keys.append(None)
            elif variable in NUMBERS:
                sort_keys = [self._format_number(item, variable)
                             for item in items]
            elif variable == 'citation_number':
                sort_keys = [item.number for item in items]
            else:
                sort_keys = [item.get_field(variable) for item in items]
        elif 'macro' in self.attrib:
            layout = context.get_layout()
            # override name options
            sort_options = {'name-as-sort-order': 'all'}
            for option in ('names-min', 'names-use-first', 'names-use-last'):
                if option in self.attrib:
                    name = option.replace('names', 'et-al')
                    sort_options[name] = self.get(option)
            macro = self.get_macro(self.get('macro'))
            sort_keys = []
            for item in items:
                layout.repressed = {}
                sort_key = macro.render(item, context=context,
                                        sort_options=sort_options)
                sort_keys.append(sort_key)

        return sort_keys

    def _format_name(self, item, variable):
        names = item.reference.get(variable)
        if names is not None:
            output = []
            for name in names:
                demote_ndp = self.get_root().get('demote-non-dropping-particle',
                                                 'display-and-sort').lower()
                sort_separator = self._default_options['sort-separator']

                # TODO: encapsulate in function (to share with Name)
                given, family, dp, ndp, suffix = name.parts()
                if demote_ndp in ('sort-only', 'display-and-sort'):
                    given = ' '.join([n for n in (given, dp, ndp) if n])
                else:
                    family = ' '.join([n for n in (ndp, family) if n])
                    given = ' '.join([n for n in (given, dp) if n])

                order = family, given, suffix
                output.append(sort_separator.join([n for n in order if n]))
            return ';'.join(output)
        else:
            return None

    def _format_number(self, item, variable):
        date = item.reference.get(variable)
        if date is not None:
            try:
                return str(Number.re_numeric.match(date).group(1))
            except AttributeError:
                return date
        else:
            return None


# Rendering elements

class Parent:

    def render_children(self, item, delimiter='', **kwargs):
        # `delimiter` is the delimiter inherited from an enclosing element (a
        # `cs:group`). `cs:choose` is transparent, so this delimiter has to be
        # threaded through `cs:if`/`cs:else-if`/`cs:else` to delimit their
        # rendered children (and any nested `cs:choose`).
        output = []
        for child in self.iterchildren():
            try:
                if isinstance(child, Choose):
                    text = child.render(item, delimiter=delimiter, **kwargs)
                else:
                    text = child.render(item, **kwargs)
                if text is not None:
                    output.append(text)
            except VariableError:
                pass
        if output:
            return join(output, delimiter)
        else:
            return None


class Macro(CitationStylesElement, Parent):

    def render(self, item, context=None, sort_options=None):
        frame = [False, False]
        group_frames.append(frame)
        failed = False
        try:
            out = self.render_children(item, context=context,
                                       sort_options=sort_options)
        except VariableError:
            failed = True
            out = None
        finally:
            group_frames.pop()
        if failed or (frame[0] and not frame[1]):
            if group_frames and frame[0]:
                group_frames[-1][0] = True
            return None
        if out and group_frames:
            # CSL 1.0：非空 macro 自身未因变量全空失败时，在外层 `<group>` 中视同非空变量输出
            group_frames[-1][0] = True
            group_frames[-1][1] = True
        return out


class Layout(CitationStylesElement, Parent, Formatted, Affixed, Delimited):
    def render_citation(self, citation, callback, layout_for=None):
        # first sort citation items according to bibliography order
        bibliography = citation.bibliography
        good_cites = [cite for cite in citation.cites if not cite.is_bad()]
        bad_cites = [cite for cite in citation.cites if cite.is_bad()]
        good_cites.sort(key=lambda item: bibliography.keys.index(item.key))
        # sort using citation/sort element
        if self.getparent().sort is not None:
            good_cites = self.getparent().sort.sort(good_cites, self)
        out = []
        for item in good_cites:
            layout = layout_for(item) if layout_for else self
            layout.repressed = {}
            prefix = item.get('prefix', '')
            suffix = item.get('suffix', '')
            try:
                output = layout.render_children(item)
                if output is not None:
                    text = prefix + output + suffix
                    out.append(text)
                    self.getparent().cites.append(item)
            except VariableError:
                pass
        for item in bad_cites:
            callback_value = callback(item)
            out.append(callback_value or f'{item.key}?')
        return self.format(self.wrap(self.join(out)))

    def render_bibliography(self, citation_items, layout_for=None):
        output_items = []
        for item in citation_items:
            layout = layout_for(item) if layout_for else self
            layout.repressed = {}
            text = layout.format(layout.wrap(layout.render_children(item)))
            if text is not None:
                output_items.append(text)
        return output_items


class FormatNumber:
    def _process(self, value, variable, language=None):
        page_range_delimiter = self.get_single_term(
            name='page-range-delimiter', language=language) \
            if variable.startswith('page') else None
        range_delimiter = (page_range_delimiter
                           or self.unicode_character('EN DASH'))

        en_dash = unicodedata.lookup('EN DASH')

        def format_number_or_range(item):
            try:
                first, last = (number.strip() for number
                               in item.replace(en_dash, '-').split('-'))
            except ValueError:
                return self.format_number(item.strip(), language=language)
            first = self.format_number(first, language=language)
            if variable == 'page-first':
                return first
            last = self.format_number(self._format_last_page(first, last)
                                      if variable == 'page' else last,
                                      language=language)
            return join((first, last), range_delimiter)

        amp_delimiter = ' ' + self.unicode_character('AMPERSAND') + ' '
        return join((join((format_number_or_range(item)
                           for item in comma_item.split('&')), amp_delimiter)
                     for comma_item in str(value).split(',')), delimiter=', ')

    def _format_last_page(self, first, last):
        def find_common(first, last):
            for index, (first_char, last_char) in enumerate(zip(first, last)):
                if first_char != last_char:
                    return index
            return len(first)

        range_format = self.get_root().get_option('page-range-format')
        common = find_common(first, last)

        if range_format in ('minimal', 'minimal-two'):
            # Equal-length numbers only: `1-40` is not `1-0`, it is the full
            # last page; unequal lengths mean the caller cannot abbreviate.
            if len(first) != len(last) or common == len(first):
                return last
            index = (common if range_format == 'minimal'
                     else max(0, min(common, len(first) - 2)))
            return last[index:]

        if range_format in ('chicago', 'chicago-15', 'chicago-16'):
            m = re.search(r'\d+', first)
            if not m:
                return last
            first_number = int(m.group())
            if first_number < 100 or first_number % 100 == 0:
                range_format = 'expanded'
            elif len(first) >= 4 and common < 2:
                range_format = 'expanded'
            elif first_number % 100 in range(1, 10):
                range_format = 'minimal'
            elif first_number % 100 in range(10, 100):
                range_format = 'minimal-two'

        index = 0  # 'expanded' format (and default): return the full last page
        if range_format == 'minimal':
            index = common
        elif range_format == 'minimal-two':
            index = min(common, len(first) - 2)
        return last[index:]

    def format_number(self, number, language=None):
        return str(number)


class Text(CitationStylesElement, FormatNumber, Formatted, Affixed, Quoted,
           TextCased, StrippedPeriods):
    generated_variables = ('year-suffix',)

    def render(self, *args, **kwargs):
        text, language = self.process(*args, **kwargs)
        return self.markup(text, language)

    def process(self, item, context=None, **kwargs):
        if context is None:
            context = self

        language = item_language(item) or self.get_root().get('default-locale', 'en')
        language = str(language)[:2]
        if 'variable' in self.attrib:
            text = self._variable(item, context)
        elif 'macro' in self.attrib:
            text = self.get_macro(self.get('macro')).render(item, context)
        elif 'term' in self.attrib:
            text = self._term(item)
        elif 'value' in self.attrib:
            text = String(self.preformat(self.get('value')))

        return text, language

    def _term(self, item):
        form = self.get('form', 'long')
        plural = self.get('plural', 'false').lower() == 'true'
        variable = self.get('term')
        language = item_language(item)
        if plural:
            text = self.get_plural_term(name=variable,
                                        form=form if form != 'long' else None,
                                        language=language)
        else:
            text = self.get_single_term(name=variable,
                                        form=form if form != 'long' else None,
                                        language=language)

        return text

    def markup(self, text, language):
        if text:
            tmp = self.format(self.case(self.strip_periods(text), language))
            return self.wrap(self.quote(tmp, language))
        else:
            return None

    def _variable(self, item, context):
        variable = self.get("variable")
        is_generated = variable in self.generated_variables
        if group_frames and not is_generated:
            group_frames[-1][0] = True
        if _is_repressed(self, variable, context):
            return None

        repressed = context.get_layout().repressed
        if self.tag in repressed and variable in repressed[self.tag]:
            return None

        if self.get('form') == 'short':
            short_variable = variable + '-short'
            if short_variable.replace('-', '_') in item.reference:
                variable = short_variable

        if variable.startswith('page'):
            val = self._process(item.reference.page, variable,
                                language=item_language(item))
        elif variable == 'citation-number':
            val = item.number
        elif variable == 'locator':
            en_dash = self.unicode_character('EN DASH')
            val = str(item.locator.identifier).replace('-', en_dash)
        else:
            val = item.reference[variable.replace('-', '_')]

        if val is not None and str(val) != "":
            if group_frames and not is_generated:
                group_frames[-1][1] = True
            if sub_frames and variable and not is_generated:
                sub_frames[-1][1].setdefault(self.tag, set()).add(variable)
        return val


class Date(CitationStylesElement, Parent, Formatted, Affixed, Delimited):

    def is_locale_date(self):
        return _ancestor(self, 'locale') is not None

    def render_single_date(self, date, show_parts=None, context=None):
        if context != self:
            parts = self.parts(date, show_parts, context)
        else:
            parts = self.parts(date, show_parts)
        if parts:
            style_context = context if self.is_locale_date() else self
            return style_context.join(parts)
        else:
            return None

    def render_date_range(self, date_range, show_parts=None, context=None):
        same_show_parts = []
        if date_range.end.is_nil():
            same = None
            diff_begin = self.render_single_date(date_range.begin, show_parts,
                                                 context)
            diff_end = ''
        else:
            if date_range.begin.year == date_range.end.year:
                show_parts.remove('year')
                same_show_parts.append('year')
                try:
                    if ('month' in show_parts and
                        date_range.begin.month == date_range.end.month):
                        show_parts.remove('month')
                        same_show_parts.append('month')
                        try:
                            if ('day' in show_parts and
                                date_range.begin.day == date_range.end.day):
                                show_parts.remove('day')
                                same_show_parts.append('day')
                        except AttributeError:
                            show_parts.remove('day')
                except AttributeError:
                    show_parts.remove('month')

            same = self.render_single_date(date_range.end, same_show_parts,
                                           context)
            diff_begin = self.render_single_date(date_range.begin, show_parts,
                                                 context)
            diff_end = self.render_single_date(date_range.end, show_parts,
                                               context)

        if not (diff_begin and diff_begin):
            return None

        diff = (diff_begin.rstrip() + self.unicode_character('EN DASH') +
                diff_end)
        if same:
            text = context.join([diff, same.rstrip()])
        else:
            text = diff

        return text

    def parts(self, date, show_parts, context=None):
        output = []
        for part in self.iterchildren():
            if part.get('name') in show_parts:
                try:
                    part_text = part.render(date, context)
                    if part_text is not None:
                        output.append(part_text)
                except VariableError:
                    pass
        return output

    def markup(self, text):
        # TODO: fix
        return text

    def process(self, item, variable=None, show_parts=None, context=None, **kwargs):
        var = variable or self.get("variable")
        ctx = context if context is not None else self
        track_var = not self.is_locale_date()
        if track_var and group_frames:
            group_frames[-1][0] = True
        if _is_repressed(self, var, ctx):
            return None

        if variable is None:
            variable = self.get('variable')
        if show_parts is None:
            show_parts = ['year', 'month', 'day']
        if context is None:
            context = self

        form = self.get('form')
        date_parts = self.get('date-parts')
        if not self.is_locale_date() and form is not None:
            localized_date = self.get_date(form)
            if date_parts is not None:
                show_parts = date_parts.split('-')
            val = localized_date.render(item, variable,
                                        show_parts=show_parts, context=self)
        else:
            date_or_range = item.reference[variable.replace('-', '_')]
            if not date_or_range:
                text = None
            elif isinstance(date_or_range, LiteralDate):
                text = date_or_range.text
            elif isinstance(date_or_range, DateRange):
                text = self.render_date_range(date_or_range, show_parts,
                                              context)
            else:
                text = self.render_single_date(date_or_range, show_parts,
                                               context)
            if text is not None:
                style_context = context if self.is_locale_date() else self
                val = style_context.wrap(text)
            else:
                val = None

        if val is not None and str(val) != "" and track_var:
            if group_frames:
                group_frames[-1][1] = True
            if sub_frames and var:
                sub_frames[-1][1].setdefault(self.tag, set()).add(var)
        return val


class Date_Part(CitationStylesElement, Formatted, Affixed, TextCased,
                StrippedPeriods):
    def process(self, date, context=None):
        name = self.get('name')
        attrib = self.attrib

        if context is None:
            context = self
        try:
            expr = f'./cs:date-part[@name="{name}"]'
            attrib.update(dict(context.xpath_search(expr)[0].attrib))
        except (AttributeError, IndexError):
            pass

        if name == 'day':
            form = self.get('form', 'numeric')
            if (form == 'ordinal'
                and self.get_locale_option('limit-day-ordinals-to-day-1')
                    .lower() == 'true'
                and date.day > 1):
                form = 'numeric'

            if form == 'numeric':
                text = date.day
            elif form == 'numeric-leading-zeros':
                text = f'{date.day:02}'
            elif form == 'ordinal':
                text = to_ordinal(date.day, context)
        elif name == 'month':
            form = self.get('form', 'long')
            try:
                index = date.month
                term = 'month'
            except VariableError:
                index = date.season
                term = 'season'

            if form == 'long' or form == 'short':
                text = context.get_single_term(name=f'{term}-{index:02}',
                                               form='short' if form == 'short' else None)
            else:
                assert term == 'month'
                if form == 'numeric':
                    text = f'{index}'
                elif form == 'numeric-leading-zeros':
                    text = f'{index:02}'
        elif name == 'year':
            form = self.get('form', 'long')
            if form == 'long':
                text = str(abs(date.year))
                if date.year < 0:
                    text += context.get_single_term(name='bc')
                elif date.year < 1000:
                    text += context.get_single_term(name='ad')
            elif form == 'short':
                text = str(date.year)[-2:]

        return text

    def markup(self, text):
        if text:
            return self.wrap(self.format(self.case(self.strip_periods(text))))
        else:
            return None


class Number(CitationStylesElement, FormatNumber, Formatted, Affixed, Displayed,
             TextCased, StrippedPeriods):

    def format_number(self, number, language=None):
        form = self.get('form', 'numeric')
        try:
            number = int(number)
        except ValueError:
            return number
        if form == 'numeric':
            text = str(number)
        elif form == 'ordinal' or form == 'long-ordinal' and number > 10:
            text = to_ordinal(number, self, language=language)
        elif form == 'long-ordinal':
            text = self.get_single_term(name=f'long-ordinal-{number:02}',
                                        language=language)
        elif form == 'roman':
            text = romanize(number).lower()
        return text

    def markup(self, text):
        if text:
            return self.wrap(self.format(self.case(self.strip_periods(text))))
        else:
            return None

    def process(self, item, context=None, **kwargs):
        var = self.get("variable")
        ctx = context if context is not None else self
        if group_frames:
            group_frames[-1][0] = True
        if _is_repressed(self, var, ctx):
            return None

        variable = var
        if variable == 'locator':
            try:
                variable = item.locator.label
                value = item.locator.identifier
            except KeyError:
                return None
        elif variable == 'page-first':
            value = item.reference.page
        else:
            value = item.reference[variable]
        val = self._process(value, variable, language=item_language(item))

        if val is not None and str(val) != "":
            if group_frames:
                group_frames[-1][1] = True
            if sub_frames and var:
                sub_frames[-1][1].setdefault(self.tag, set()).add(var)
        return val


class Names(CitationStylesElement, Parent, Formatted, Affixed, Delimited):

    def get_parent_delimiter(self, context=None):
        if context is None:
            context = self
        parent = _ancestor(context, 'citation', 'bibliography')
        if parent is None:
            raise IndexError('no enclosing citation or bibliography')
        return parent.get_option('names-delimiter')

    def substitute(self):
        expr = './cs:substitute[1]'
        try:
            result = self.xpath_search(expr)[0]
        except IndexError:
            result = None
        return result

    def markup(self, text):
        if text:
            return self.wrap(self.format(text))
        else:
            return None

    def process(self, item, names_context=None, context=None, **kwargs):
        ctx = context if context is not None else self
        if names_context is None and self.name is None and sub_frames:
            parent_names = sub_frames[-1][0]
            if parent_names is not None and parent_names is not self:
                names_context = parent_names

        try:
            layout = ctx.get_layout()
            repressed_list = getattr(layout, "repressed", {}).get(self.tag, [])
        except Exception:
            repressed_list = []
        repressed_vars: set[str] = set()
        for var in repressed_list:
            if var:
                repressed_vars.update(var.split())

        orig_var = self.get("variable") or ""
        roles = orig_var.split()
        filtered = [role for role in roles if role not in repressed_vars]
        if group_frames:
            group_frames[-1][0] = True
        if roles and not filtered:
            # 声明的 role 全被前一个 `<substitute>` 抑制掉了：这里本来就不该出东西。
            # 不能把 `variable` 改成空串再交给渲染器——它会当成「变量缺失」，把本元素
            # 自己的 `<substitute>` 再渲染一遍。
            return None
        present = [r for r in filtered if r in item.reference and item.reference[r]]
        context = ctx
        if names_context is None:
            names_context = self

        def render_roles(active_roles):
            try:
                ed_trans = (set(active_roles) == set(['editor', 'translator']) and
                            item.reference.editor == item.reference.translator and
                            self.get_term('editortranslator',
                                          language=item_language(item)).getchildren())
                if ed_trans:
                    active_roles = ['editor']
            except VariableError:
                ed_trans = False

            output = []
            for role in active_roles:
                if role in item.reference:
                    name_elem = names_context.name
                    if name_elem is None:
                        name_elem = Name()
                        names_context.insert(0, name_elem)
                    text = name_elem.render(item, role, context=context, **kwargs)
                    plural = len(item.reference[role]) > 1
                    try:
                        if ed_trans:
                            role = 'editortranslator'
                        label_element = names_context.label
                        label = label_element.render(item, role, plural, **kwargs)
                        if label is not None:
                            if label_element is names_context.getchildren()[0]:
                                text = label + text
                            else:
                                text = text + label
                    except AttributeError:
                        pass
                    output.append(text)

            if output:
                try:
                    total = sum(output)
                except TypeError:
                    is_int = False
                else:
                    is_int = isinstance(total, int)
                if is_int:
                    text = str(total) if total > 0 else None
                else:
                    text = self.join(output, self.get_parent_delimiter(context))
            else:
                substitute = self.substitute()
                if substitute is not None:
                    text = substitute.render(item, context=context, **kwargs)

            try:
                return text
            except NameError:
                raise VariableError from None

        out = render_roles(filtered)
        if out:
            if group_frames:
                group_frames[-1][1] = True
            if present and sub_frames:
                sub_frames[-1][1].setdefault(self.tag, set()).update(present)
        return out

class Name(CitationStylesElement, Formatted, Affixed, Delimited):
    def get_option(self, name, context=None, sort_options=None):
        try:
            value = sort_options[name]
        except (TypeError, KeyError):
            if context is None:
                context = self
            parent = _ancestor(context, 'citation', 'bibliography')
            if parent is None:
                raise IndexError('no enclosing citation or bibliography') from None
            if name in ('form', 'delimiter'):
                value = self.get(name, parent.get_option('name-' + name))
            else:
                value = self.get(name, parent.get_option(name))

        if name in ('initialize-with-hyphen', 'et-al-use-last'):
            value = value.lower() == 'true'
        elif name.startswith('et-al'):
            value = int(value)

        return value

    def et_al(self, item=None):
        expr = './following-sibling::cs:et-al[1]'
        try:
            result = self.xpath_search(expr)[0].render(item)
        except IndexError:
            result = self.get_single_term(name='et-al',
                                          language=item_language(item))
        return result

    def process(self, item, variable, context=None, sort_options=None, **kwargs):
        def get_option(name):
            return self.get_option(name, context, sort_options)

        and_ = get_option('and')
        delimiter = get_option('delimiter')
        delimiter_precedes_et_al = get_option('delimiter-precedes-et-al')
        delimiter_precedes_last = get_option('delimiter-precedes-last')

        et_al_min = get_option('et-al-min')
        et_al_use_first = get_option('et-al-use-first')
        # et_al_subseq_min = get_option('et-al-subsequent-min')
        # et_al_subseq_use_first = get_option('et-al-subsequent-use-first')
        et_al_use_last = get_option('et-al-use-last')

        initialize_with = get_option('initialize-with')
        name_as_sort_order = get_option('name-as-sort-order')
        sort_separator = get_option('sort-separator')

        form = get_option('form')
        demote_ndp = get_option('demote-non-dropping-particle')

        def format_name_parts(given, family):
            for part in self.findall('cs:name-part', self.nsmap):
                given, family = part.format_part(given, family)
            return given, family

        names = item.reference.get(variable, [])

        language = item_language(item)
        if and_ == 'text':
            and_term = self.get_single_term(name='and', language=language)
        elif and_ == 'symbol':
            and_term = self.preformat('&')

        et_al = self.et_al(item)
        output = []
        if form == 'count':
            count = min(len(names), et_al_use_first)
            output.append(count)
            return sum(output)
        else:
            et_al_truncate = (len(names) > 1 and et_al_min and
                              len(names) >= et_al_min)
            et_al_last = et_al_use_last and et_al_use_first <= et_al_min - 2
            if et_al_truncate:
                if et_al_last:
                    names = names[:et_al_use_first] + [names[-1]]
                else:
                    names = names[:et_al_use_first]
            for i, name in enumerate(names):
                given, family, dp, ndp, suffix = name.parts()

                if given is not None and initialize_with is not None:
                    given = self.initialize(given, initialize_with, context)

                if form == 'long':
                    if (name_as_sort_order == 'all' or
                            (name_as_sort_order == 'first' and i == 0)):
                        if demote_ndp in ('never', 'sort-only'):
                            family = join([n for n in (ndp, family) if n], ' ')
                            given = join([n for n in (given, dp) if n], ' ')
                        else:
                            given = join([n for n in (given, dp, ndp) if n], ' ')

                        given, family = format_name_parts(given, family)
                        order = family, given, suffix
                        text = join([n for n in order if n], sort_separator)
                    else:
                        family = join([n for n in (dp, ndp, family) if n], ' ')
                        given, family = format_name_parts(given, family)
                        order = given, family, suffix
                        text = join([n for n in order if n], ' ')
                elif form == 'short':
                    family = join([n for n in (ndp, family) if n], ' ')
                    given, family = format_name_parts(given, family)
                    text = family

                output.append(text)

            if et_al_truncate and et_al:
                if et_al_last:
                    ellipsis = self.unicode_character('horizontal ellipsis')
                    output[-1] = ellipsis + ' ' + output[-1]
                    text = self.join(output, delimiter)
                elif (delimiter_precedes_et_al == 'always' or
                      (delimiter_precedes_et_al == 'contextual' and
                     len(output) >= 2)):
                    output.append(et_al)
                    text = self.join(output, delimiter)
                else:
                    text = self.join(output, delimiter) + ' ' + et_al
            elif and_ is not None and len(output) > 1:
                text = self.join(output[:-1], ', ')
                if (delimiter_precedes_last == 'always'
                    or (delimiter_precedes_last == 'contextual' and len(output) > 2)):
                    text = self.join([text, ''], ', ')
                else:
                    text += ' '
                text = text + and_term + ' ' + output[-1]
            else:
                text = self.join(output, delimiter)

            return text

    def markup(self, text):
        if text:
            return self.wrap(self.format(text))
        else:
            return None

    def initialize(self, given, mark, context=None):
        init_opt = self.get("initialize")
        if init_opt is None:
            ctx = context if context is not None else self
            parent = _ancestor(ctx, 'citation', 'bibliography')
            init_opt = parent.get("initialize") if parent is not None else None
            if init_opt is None:
                try:
                    init_opt = self.get_root().get("initialize")
                except Exception:
                    init_opt = None
        if init_opt is not None and str(init_opt).lower() == "false":
            return given

        if self.get_option('initialize-with-hyphen', context):
            hyphen_parts = given.split('-')
        else:
            hyphen_parts = [given.replace('-', ' ')]

        result_parts = []
        for hyphen_part in hyphen_parts:
            parts = hyphen_part.replace('.', ' ').split()
            hyphen_result = ''
            group = []
            for part in parts:
                if part[0].isupper():
                    group.append(part[0])
                else:
                    # don't initialize particles (which aren't capitalized)
                    hyphen_result += mark.join(group) + mark + ' ' + part + ' '
                    group = []
            hyphen_result += mark.join(group) + mark
            hyphen_result = ' '.join(hyphen_result.split())
            result_parts.append(hyphen_result)
        return '-'.join(result_parts)


class Name_Part(CitationStylesElement, Formatted, Affixed, TextCased):
    def format_part(self, given, family):
        if self.get('name') == 'given':
            given = self.wrap(self.format(self.case(given)))
        elif self.get('name') == 'family':
            family = self.wrap(self.format(self.case(family)))
        return given, family


class Et_Al(CitationStylesElement, Formatted, Affixed):
    def process(self, item=None):
        variable = self.get('term', 'et-al')
        return self.get_single_term(variable, language=item_language(item))

    def markup(self, text):
        if text:
            return self.wrap(self.format(text))
        else:
            return None


class Substitute(CitationStylesElement, Parent):

    def render(self, item, context=None, **kwargs):
        ctx = context if context is not None else self
        parent = self.getparent()
        parent_names = parent if _is_csl(parent, 'names') else None
        for child in self.getchildren():
            staging: dict[str, set[str]] = {}
            sub_group_frame = [False, False]
            sub_frames.append((parent_names, staging))
            group_frames.append(sub_group_frame)
            text = None
            try:
                if isinstance(child, Names) and child.name is None and parent_names is not None:
                    text = child.render(item, names_context=parent_names, context=ctx, **kwargs)
                else:
                    text = child.render(item, context=ctx, **kwargs)
            except VariableError:
                continue
            finally:
                sub_frames.pop()
                group_frames.pop()
            if text:
                if group_frames and sub_group_frame[1]:
                    group_frames[-1][0] = True
                    group_frames[-1][1] = True
                try:
                    layout = ctx.get_layout()
                except Exception:
                    return text
                for rtag, rvars in staging.items():
                    bucket = layout.repressed.setdefault(rtag, [])
                    for rvar in rvars:
                        if rvar not in bucket:
                            bucket.append(rvar)
                direct_var = child.get("variable")
                if direct_var:
                    bucket = layout.repressed.setdefault(child.tag, [])
                    for rvar in direct_var.split():
                        if rvar not in bucket:
                            bucket.append(rvar)
                return text
        if group_frames:
            group_frames[-1][0] = True
        return None


class Label(CitationStylesElement, Formatted, Affixed, StrippedPeriods,
            TextCased):

    def markup(self, text):
        if text:
            return self.wrap(self.format(self.case(self.strip_periods(text))))
        else:
            return None

    # Content is plural when it holds multiple numbers separated by a list or
    # range separator (e.g. "1, 2" or "1-3"). A period is not such a separator:
    # it is part of a single dotted number/version (e.g. "2.0"), which stays
    # singular ("Version 2.0", not "Versions 2.0").
    RE_MULTIPLE_NUMBERS = re.compile(r'\d+[^\d.]+\d+')

    def _variable_is_set(self, item, variable):
        """Whether the labelled variable holds a value for this item.

        The lookup follows the one in `Text._variable`: `locator` lives on the
        citation item rather than the reference, `citation-number` is generated
        and is set for every registered item, and the `page-first` virtual
        variable is derived from `page`.
        """
        if variable == 'locator':
            return item.has_locator
        elif variable == 'citation-number':
            return True
        elif variable.startswith('page'):
            variable = 'page'

        try:
            value = item.reference[variable.replace('-', '_')]
        except VariableError:
            return False

        return value is not None and str(value) != ''

    def process(self, item, variable=None, plural=None, context=None, **kwargs):
        var = variable or self.get("variable")
        standalone = variable is None
        if var == "locator":
            if group_frames:
                group_frames[-1][0] = True
            if not getattr(item, "has_locator", False):
                return None
        elif var and standalone and group_frames:
            # 独立 `<label variable="X"/>` 在变量为空时不渲染——`_variable_is_set`
            # 认 `page-first` / `citation-number` 这些派生变量，这里只补 group 的
            # 运行期变量追踪。
            group_frames[-1][0] = True

        if variable is None:
            variable = self.get('variable')
            if not self._variable_is_set(item, variable):
                return None
        form = self.get('form', 'long')
        plural_option = self.get('plural', 'contextual')
        if plural is None:
            plural = self._is_plural(item)
        if variable == 'locator' and item.has_locator:
            variable = item.locator.label

        language = item_language(item)
        if (plural_option == 'contextual' and plural or
            plural_option == 'always'):
            val = self.get_plural_term(name=variable,
                                       form=form if form != 'long' else None,
                                       language=language)
        else:
            val = self.get_single_term(name=variable,
                                       form=form if form != 'long' else None,
                                       language=language)

        if val is not None and str(val) != "" and (var == "locator" or (var and standalone)) and group_frames:
            group_frames[-1][1] = True
        return val

    def _is_plural(self, item):
        var = self.get("variable")
        if var in ("version", "number", "collection-number"):
            try:
                value = item.reference[var.replace("-", "_")]
            except VariableError:
                return False
            # 复数 = 整串就是「数字 分隔符 数字…」：`3-5` / `1, 2` / `1 & 2` / `1/2`。
            # 上游 0.12 的 `\d+[^\d.]+\d+` 会匹配到 `3.5.0--rc1`（`--rc` 里带字母），
            # 那是一条版本号不是区间；反过来我们的旧正则不认 `-`，`3-5` 又丢复数。
            # 用整串匹配同时挡住 `TR-2023-04` 这类编号：它不是区间，不该复数。
            return bool(
                re.fullmatch(
                    r"\d+(?:\s*[-–—,;，；/、&]\s*\d+)+",
                    str(value).strip(),
                )
            )
        variable = self.get('variable')
        if variable == 'locator':
            value = item.locator.identifier
        else:
            try:
                value = item.reference[variable.replace('-', '_')]
            except VariableError:
                return False

        if variable.startswith('number-of') and int(item[variable]) > 1:
            return True
        return self.RE_MULTIPLE_NUMBERS.search(str(value)) is not None

    def render(self, *args, **kwargs):
        text = self.process(*args, **kwargs)
        if not text:
            return None
        item = kwargs.get("item") if "item" in kwargs else (args[0] if args else None)
        lang = item_language(item)
        if not lang:
            root = self.get_root()
            default_locale = root.get("default-locale", "en") if root is not None else "en"
            lang = default_locale
        lang = str(lang)[:2].lower()
        return self.wrap(self.format(self.case(self.strip_periods(text), lang)))


class Group(CitationStylesElement, Parent, Formatted, Affixed, Delimited):

    def markup(self, text):
        if text:
            return self.wrap(self.format(text))
        else:
            return None

    def process(self, item, context=None, **kwargs):
        frame = [False, False]
        group_frames.append(frame)
        try:
            output = []
            delimiter = self.get("delimiter", "")
            for child in self.iterchildren():
                try:
                    if isinstance(child, Choose):
                        child_text = child.render(item, context=context, delimiter=delimiter, **kwargs)
                    else:
                        child_text = child.render(item, context=context, **kwargs)
                    if child_text is not None:
                        output.append(child_text)
                except VariableError:
                    pass
            output = [part for part in output if part is not None]
            success = (not frame[0]) or frame[1]
            if output and success:
                return self.join(output)
            raise VariableError
        finally:
            group_frames.pop()
            if group_frames:
                group_frames[-1][0] = group_frames[-1][0] or frame[0]
                group_frames[-1][1] = group_frames[-1][1] or frame[1]


class ConditionFailed(Exception):
    pass


class Choose(CitationStylesElement, Parent):
    def render(self, item, context=None, delimiter='', **kwargs):
        # `cs:choose` is transparent: the delimiter of the enclosing element is
        # forwarded to the children of the matching branch.
        for child in self.getchildren():
            try:
                return child.render(item, context=context,
                                    delimiter=delimiter, **kwargs)
            except ConditionFailed:
                continue

        return None


class If(CitationStylesElement, Parent):
    def _type(self, item):
        return [typ.lower() == item.reference.type
                for typ in self.get('type').split()]

    def _variable(self, item):
        variables = [var.replace('-', '_')
                     for var in self.get('variable').split()]
        output = []
        for variable in variables:
            if variable == 'locator':
                output.append('locator' in item)
            else:
                output.append(variable in item.reference)
        return output

    re_numeric = re.compile(r'^([A-Z]*\d+[A-Z]*)$', re.I)

    def _is_numeric(self, item):
        numeric_match = self.re_numeric.match
        return [var.replace('-', '_') in item.reference and
                numeric_match(str(item.reference[var.replace('-', '_')]))
                for var in self.get('is-numeric').split()]

    def _is_uncertain_date(self, item):
        result = []
        for date in self.get('is-uncertain-date').split():
            date_variable = date.replace('-', '_')
            try:
                circa = item.reference[date_variable].get('circa', False)
            except VariableError:
                circa = False
            except AttributeError:
                circa = False
            result.append(circa)
        return result

    def _locator(self, item):
        return [item.has_locator and var.replace('-', ' ') == item.locator.label
                for var in self.get('locator').split()]

    def _position(self, item, context):
        if context is None:
            context = self
        if _ancestor(context, 'bibliography') is not None:
            return [False]
        # citation node
        cites = context.get_layout().getparent().cites
        last_cite = cites[-1] if cites else None
        already_cited = item.key in (cite.key for cite in cites)
        possibly_ibid = (already_cited
                         and item.key == last_cite.key
                         and (item.citation is last_cite.citation
                              or len(last_cite.citation.cites) == 1))
        results = []
        for position in self.get('position').split():
            result = False
            if position == 'first':
                result = not already_cited
            elif position == 'subsequent':
                result = already_cited
            elif possibly_ibid and position == 'ibid':
                result = item.has_locator or not last_cite.has_locator
            elif possibly_ibid and position == 'ibid-with-locator':
                result = (item.has_locator and not last_cite.has_locator
                          or (item.has_locator and last_cite.has_locator
                              and item.locator != last_cite.locator))
            elif already_cited and position == 'near-note':
                max_distance = self.get_root().get_option('near-note-distance')
                citations = 1
                last_citation = None
                for cite in reversed(cites):
                    if item.key == cite.key and citations <= max_distance:
                        result = True
                        break
                    elif cite.citation is not last_citation:
                        citations += 1
                        last_citation = cite.citation
            results.append(result)
        return results

    def render(self, item, context=None, delimiter="", **kwargs):
        results: list[bool] = []
        if "disambiguate" in self.attrib:
            want = str(self.get("disambiguate")).lower() == "true"
            results.append((item.key in DISAMBIGUATE_KEYS.get()) == want)
        if "type" in self.attrib:
            results += self._type(item)
        if "variable" in self.attrib:
            results += self._variable(item)
        if "is-numeric" in self.attrib:
            results += self._is_numeric(item)
        if "is-uncertain-date" in self.attrib:
            results += self._is_uncertain_date(item)
        if "locator" in self.attrib:
            results += self._locator(item)
        if "position" in self.attrib:
            results += self._position(item, context)
        match_mode = self.get("match")
        if match_mode == "any":
            result = any(results)
        elif match_mode == "none":
            result = not any(results)
        else:
            result = all(results)
        if not result:
            raise ConditionFailed
        return self.render_children(item, context=context, delimiter=delimiter, **kwargs)


class Else_If(If, CitationStylesElement):
    pass


class Else(CitationStylesElement, Parent):
    def render(self, item, context=None, delimiter='', **kwargs):
        return self.render_children(item, context=context,
                                    delimiter=delimiter, **kwargs)


# utility functions

def to_ordinal(number, context, language=None):
    lg_key = "{http://www.w3.org/XML/1998/namespace}lang"

    def _find(fallback_locale: bool):
        locales = (context._locales_for(language) if language
                   else context.get_root().locales)
        if not fallback_locale and locales:
            main_lg = (locales[0].get(lg_key) or "").split("-")[0]
            if main_lg:
                candidates = [
                    loc for loc in locales
                    if (loc.get(lg_key) or main_lg).split("-")[0] == main_lg
                ]
            else:
                candidates = list(locales[:1])
        else:
            candidates = list(locales)

        keys = [
            (f"ordinal-{number:02}" if len(str(number)) == 1 else f"ordinal-{number}", False),
            (f"ordinal-{int(str(number)[-1]):02}", True),
            ("ordinal", False),
        ]
        for term_name, zp in keys:
            for loc in candidates:
                try:
                    t_el = loc.get_term(term_name, zero_padded=zp)
                except IndexError:
                    continue
                if t_el is not None:
                    return True, str(t_el.single)
        return False, ""

    found, suffix = _find(fallback_locale=False)
    if not found:
        _f2, suffix = _find(fallback_locale=True)
    return str(number) + suffix


def romanize(n):
    # by Kay Schluehr - from http://billmill.org/python_roman.html
    numerals = (('M', 1000), ('CM', 900), ('D', 500), ('CD', 400),
                ('C', 100), ('XC', 90), ('L', 50), ('XL', 40), ('X', 10),
                ('IX', 9), ('V', 5), ('IV', 4), ('I', 1))
    roman = []
    for ltr, num in numerals:
        (k, n) = divmod(n, num)
        roman.append(ltr * k)
    return ''.join(roman)
