"""CSL capability gate.

We support arbitrary CSL, but not every construct the CSL schema allows has an
implementation here. This gate turns the dangerous ones into a clear error
before rendering instead of letting an unknown element crash with a `TypeError`
or an unimplemented attribute silently change the output.

It is deliberately capability-based, not schema-only: several attributes that
the schema accepts (`display`, `range-delimiter`, `entry-spacing`, …) are used
by the bundled styles and are accepted.
"""

from __future__ import annotations

from lxml import etree

CSL_NS = "http://purl.org/net/xbiblio/csl"

MODEL = {
    "style", "locale", "citation", "bibliography", "macro", "sort", "key",
    "layout", "text", "date", "date-part", "number", "names", "name",
    "name-part", "et-al", "substitute", "label", "group", "choose", "if",
    "else-if", "else", "term",
}

METADATA = {
    "info", "title", "title-short", "id", "link", "updated", "rights",
    "category", "issn", "eissn", "issnl", "published", "author",
    "contributor", "translator", "email", "uri", "summary",
}

LOCALE_INFRA = {"terms", "style-options", "single", "multiple"}

SUPPORTED_VERSIONS = {"1.0", "1.0.1", "1.0.2"}

# Valid CSL attributes that this engine does not implement. Accepting them
# would silently change the output, so they stop the export.
UNSUPPORTED_ATTRIBUTES = {
    "et-al-subsequent-min",
    "et-al-subsequent-use-first",
    "gender",
    "gender-form",
    "suppress-author",
}

# `subsequent-author-substitute` itself is implemented for the default rule.
# The other rules substitute only part of the name list; accepting them would
# print a different bibliography than the style asks for.
SUPPORTED_SUBSTITUTE_RULES = {"complete-all"}


class CslFeatureError(ValueError):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


def _local(element) -> str:
    return etree.QName(element).localname


def _ancestor(element, name: str) -> bool:
    return any(
        isinstance(node.tag, str)
        and etree.QName(node).localname == name
        and etree.QName(node).namespace == CSL_NS
        for node in element.iterancestors()
    )


def check_style(style) -> None:
    """Raise `CslFeatureError` when a style uses an unsupported construct."""
    try:
        root = etree.parse(str(style)).getroot()
    except (OSError, etree.XMLSyntaxError) as exc:
        raise CslFeatureError([f"style cannot be parsed: {exc}"]) from exc

    errors: list[str] = []
    for element in root.iter():
        if not isinstance(element.tag, str):
            continue
        qname = etree.QName(element)
        if qname.namespace != CSL_NS:
            continue
        name = qname.localname

        if name == "info":
            if not _ancestor(element, "style"):
                errors.append("<info> appears outside <style>")
            continue
        if name in METADATA:
            if not _ancestor(element, "info"):
                errors.append(f"<{name}> appears outside <info>")
            continue
        if name in MODEL:
            pass
        elif name in LOCALE_INFRA:
            parent = "locale" if name in ("terms", "style-options") else "term"
            if not _ancestor(element, parent):
                errors.append(f"<{name}> appears outside <{parent}>")
        else:
            errors.append(f"unsupported CSL element <{name}>")

        for attr, value in element.attrib.items():
            attr_name = etree.QName(attr).localname
            if attr_name in UNSUPPORTED_ATTRIBUTES:
                errors.append(f"unsupported attribute {name}@{attr_name}={value!r}")
            elif (
                attr_name == "subsequent-author-substitute-rule"
                and value not in SUPPORTED_SUBSTITUTE_RULES
            ):
                errors.append(
                    f"unsupported attribute {name}@{attr_name}={value!r} "
                    "(only complete-all is supported)"
                )

    version = root.get("version", "")
    if version and version not in SUPPORTED_VERSIONS:
        errors.append(f"unsupported CSL version {version!r}")
    if root.get("class") == "note":
        errors.append('class="note" styles are not supported')

    if errors:
        # Deduplicate while keeping the first occurrence order.
        raise CslFeatureError(list(dict.fromkeys(errors)))
