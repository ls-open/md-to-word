"""Small XML helpers shared by the XML stages."""

from lxml import etree


def local_name(element) -> str:
    """Local part of an element or attribute name (`{namespace}tag` → `tag`)."""
    return etree.QName(element).localname
