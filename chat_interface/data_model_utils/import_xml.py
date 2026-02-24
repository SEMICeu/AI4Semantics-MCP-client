from typing import (
    Dict,
    Any,
    List,
)
from io import (
    BytesIO,
)
from xml.etree.ElementTree import (
    Element,
    parse,
)


def _get_package(
    elem: Element,
) -> Dict[str, Any]:
    """
    Extracts information about a UML package from an XML element and returns it as a dictionary.

    :param elem: XML element representing a UML package.
    :return: Dictionary with package details (name, ID, type, package, and tags).
    """
    return {
        "name": elem.get('name'),
        "ID": elem.get('{http://schema.omg.org/spec/XMI/2.1}idref'),
        "type": elem.get('{http://schema.omg.org/spec/XMI/2.1}type'),
        "package": elem.find('model').get('package'),
        "tags": [
            {
                "name": tag.get('name'),
                "value": tag.get('value')
            }
            for tag
            in elem.find('tags').findall('tag')
        ]
    }


def _get_class(
    elem: Element,
) -> Dict[str, Any]:
    """
    Extracts information about a UML class from an XML element and returns it as a dictionary.

    :param elem: XML element representing a UML class.
    :return: Dictionary with class details (name, ID, type, package, tags, and attributes).
    """
    class_dict: Dict[str, Any] = {
        "name": elem.get('name'),
        "ID": elem.get('{http://schema.omg.org/spec/XMI/2.1}idref'),
        "type": elem.get('{http://schema.omg.org/spec/XMI/2.1}type'),
        "package": elem.find('model').get('package'),
        "tags": [
            {
                "name": tag.get('name'),
                "value": tag.get('value')
            }
            for tag
            in elem.find('tags').findall('tag')
        ],
        "attributes": []
    }

    if elem.find('attributes'):
        for attribute in elem.find("attributes").findall('attribute'):
            attribute_dict = {
                "name": attribute.get('name'),
                "type": next(
                    (
                        prop.get('type')
                        for prop
                        in attribute.findall('properties')
                    ),
                    None,
                ),
                "lower_bounds": next(
                    (
                        bound.get('lower')
                        for bound
                        in attribute.findall('bounds')
                    ),
                    None,
                ),
                "upper_bounds": next(
                    (
                        bound.get('upper')
                        for bound
                        in attribute.findall('bounds')
                    ),
                    None,
                ),
                "tags_attribute": [
                    {
                        "name": tag_attribute.get('name'),
                        "value": tag_attribute.get('value')
                    }
                    for tag_attribute
                    in attribute.find('tags').findall('tag')
                ]
            }
            class_dict["attributes"].append(attribute_dict)

    return class_dict


def _get_datatype(
    elem: Element,
) -> Dict[str, Any]:
    """
    Extracts information about a UML data type from an XML element and returns it as a dictionary.

    :param elem: XML element representing a UML data type.
    :return: Dictionary with data type details (name, ID, type, package, tags, and attributes).
    """
    datatype_dict: Dict[str, Any] = {
        "name": elem.get('name'),
        "ID": elem.get('{http://schema.omg.org/spec/XMI/2.1}idref'),
        "type": elem.get('{http://schema.omg.org/spec/XMI/2.1}type'),
        "package": elem.find('model').get('package'),
        "tags": [
            {
                "name": tag.get('name'),
                "value": tag.get('value')
            }
            for tag
            in elem.find('tags').findall('tag')
        ],
        "attributes": []
    }

    if elem.find('attributes'):
        for attribute in elem.find("attributes").findall('attribute'):
            attribute_dict = {
                "name": attribute.get('name'),
                "type": next(
                    (
                        prop.get('type')
                        for prop
                        in attribute.findall('properties')
                    ),
                    None,
                ),
                "lower_bounds": next(
                    (
                        bound.get('lower')
                        for bound
                        in attribute.findall('bounds')
                    ),
                    None,
                ),
                "upper_bounds": next(
                    (
                        bound.get('upper')
                        for bound
                        in attribute.findall('bounds')
                    ),
                    None,
                ),
                "tags_attribute": [
                    {
                        "name": tag_attribute.get('name'),
                        "value": tag_attribute.get('value')
                    }
                    for tag_attribute
                    in attribute.find('tags').findall('tag')
                ]
            }
            datatype_dict["attributes"].append(attribute_dict)

    return datatype_dict


def _get_enumeration(
    elem: Element,
) -> Dict[str, Any]:
    """
    Extracts information about a UML enumeration from an XML element and returns it as a dictionary.

    :param elem: XML element representing a UML enumeration.
    :return: Dictionary with enumeration details (name, ID, type, package, tags, and categories).
    """
    enum_dict: Dict[str, Any] = {
        "name": elem.get('name'),
        "ID": elem.get('{http://schema.omg.org/spec/XMI/2.1}idref'),
        "type": elem.get('{http://schema.omg.org/spec/XMI/2.1}type'),
        "package": elem.find('model').get('package'),
        "tags": [
            {
                "name": tag.get('name'),
                "value": tag.get('value')
            }
            for tag
            in elem.find('tags').findall('tag')
        ],
        "categories": [
            attribute.get('name')
            for attribute
            in elem.find("attributes").findall('attribute')
        ]
        if elem.find('attributes') else
        []
    }
    return enum_dict


def _get_elements(
    root: Element,
) -> List[Dict[str, Any]]:
    """
    Extracts all UML elements (packages, classes, data types, and enumerations) from the XML tree.

    :param root: Root XML element.
    :return: List of dictionaries representing UML elements.
    """
    elements: List[Dict[str, Any]] = []
    for elem in root[2][0].iter('element'):
        element_type = elem.get('{http://schema.omg.org/spec/XMI/2.1}type')
        if element_type == 'uml:Package':
            elements.append(_get_package(elem))

        elif element_type == 'uml:Class':
            elements.append(_get_class(elem))

        elif element_type == 'uml:DataType':
            elements.append(_get_datatype(elem))

        elif element_type == 'uml:Enumeration':
            elements.append(_get_enumeration(elem))

        else:
            print(f"ERROR: {elem.tag}")

    return elements


def _get_connector(
    connector: Element,
) -> Dict[str, Any]:
    """
    Extracts information about a UML connector from an XML element and returns it as a dictionary.

    :param connector: XML element representing a UML connector.
    :return: Dictionary with connector details (source, target, relationship, labels, and tags).
    """
    connector_dict: Dict[str, Any] = {
        "source_name": connector.find('source').find('model').get('name'),
        "target_name": connector.find('target').find('model').get('name'),
        "relationship": connector.find('properties').get('ea_type'),
        "lb": connector.find('labels').get('lb'),
        "lt": connector.find('labels').get('lt'),
        "rb": connector.find('labels').get('rb'),
        "rt": connector.find('labels').get('rt'),
        "tags": [
            {
                "name": tag.get('name'),
                "value": tag.get('value')
            }
            for tag
            in connector.find('tags').findall('tag')
        ],
        "tags_source": [
            {
                "name": tag.get('name'),
                "value": tag.get('value')
            }
            for tag
            in connector.find('source').find('tags').findall('tag')
        ],
        "tags_target": [
            {
                "name": tag.get('name'),
                "value": tag.get('value')
            }
            for tag
            in connector.find('target').find('tags').findall('tag')
        ]
    }
    return connector_dict


def _get_connectors(
    root: Element,
) -> List[Dict[str, Any]]:
    """
    Extracts all UML connectors from the XML tree.

    :param root: Root XML element.
    :return: List of dictionaries representing UML connectors.
    """
    return [
        _get_connector(connector)
        for connector
        in root.iter('connector')
    ]


def _get_xml_data(
    root: Element,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Extracts UML data (elements and connectors) from the XML tree.

    :param root: Root XML element.
    :return: Dictionary containing UML elements and connectors.
    """
    return {
        "elements": _get_elements(root),
        "connectors": _get_connectors(root)
    }


def xml_to_json(
    bytes_data: BytesIO,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Converts XML data describing a UML model into a JSON-compatible dictionary.

    :param bytes_data: Bytes-like object containing XML data.
    :return: JSON-compatible dictionary representation of the UML model.
    """
    tree = parse(bytes_data)
    root = tree.getroot()
    return _get_xml_data(root)
