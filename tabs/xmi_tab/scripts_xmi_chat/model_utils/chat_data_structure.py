def _shorten_package(elem):
    package_dict = {}
    package_dict["name"] = elem["name"]

    tags = []
    for tag in elem["tags"]:
        if "definition" in tag["name"] or "uri" in tag["name"]:
            tag_dict = {}
            tag_dict["name"] = tag["name"]
            tag_dict["value"] = tag["value"]
            tags.append(tag_dict)

    package_dict["tags"] = tags

    return package_dict


def _shorten_class(elem):
    class_dict = {}
    class_dict["name"] = elem["name"]

    tags = []
    for tag in elem["tags"]:
        if "definition" in tag["name"] or "uri" in tag["name"]:
            tag_dict = {}
            tag_dict["name"] = tag["name"]
            tag_dict["value"] = tag["value"]
            tags.append(tag_dict)
    class_dict["tags"] = tags

    try:
        attributes = []
        for attribute in elem["attributes"]:
            attribute_dict = {}
            attribute_dict["name"] = attribute["name"]
            attribute_dict["type"] = attribute["type"]
            #attribute_dict["lower_bounds"] = attribute["lower_bounds"]
            #attribute_dict["upper_bounds"] = attribute["upper_bounds"]
            attribute_dict["tags"] = attribute["tags_attribute"]
            attributes.append(attribute_dict)

        class_dict["attributes"] = attributes

    except Exception:
        pass

    return class_dict


def _shorten_datatype(elem):
    datatype_dict = {}
    datatype_dict["name"] = elem["name"]

    tags = []
    for tag in elem["tags"]:
        if "definition" in tag["name"] or "uri" in tag["name"]:
            tag_dict = {}
            tag_dict["name"] = tag["name"]
            tag_dict["value"] = tag["value"]
            tags.append(tag_dict)
    datatype_dict["tags"] = tags

    try:
        attributes = []
        for attribute in elem["attributes"]:
            attribute_dict = {}
            attribute_dict["name"] = attribute["name"]
            attribute_dict["type"] = attribute["type"]
            attribute_dict["lower_bounds"] = attribute["lower_bounds"]
            attribute_dict["upper_bounds"] = attribute["upper_bounds"]

        datatype_dict["attributes"] = attributes

    except Exception:
        pass

    return datatype_dict


def _shorten_enum(elem):
    enum_dict = {}
    enum_dict["name"] = elem["name"]

    tags = []
    for tag in elem["tags"]:
        if "definition" in tag["name"] or "uri" in tag["name"]:
            tag_dict = {}
            tag_dict["name"] = tag["name"]
            tag_dict["value"] = tag["value"]
            tags.append(tag_dict)
    enum_dict["tags"] = tags
    try:
        enum_dict["categories"] = elem["categories"]

    except Exception:
        pass

    return enum_dict


def _shorten_elements(elements):
    packages = []
    classes = []
    datatypes = []
    enumerations = []

    for elem in elements:
        if elem["type"] == "uml:Package":
            packages.append(_shorten_package(elem))
        elif elem["type"] == "uml:Class":
            classes.append(_shorten_class(elem))
        elif elem["type"] == "uml:DataType":
            datatypes.append(_shorten_datatype(elem))
        elif elem["type"] == "uml:Enumeration":
            enumerations.append(_shorten_enum(elem))
        else:
            print(f"ERROR SHORTEN: {elem}")

    elements = {
        "packages": packages,
        "classes": classes,
        "datatypes": datatypes,
        "enumerations": enumerations,
    }

    return elements


def _shorten_connector(conn):
    conn_dict = {}
    conn_dict["source_name"] = conn["source_name"]
    conn_dict["target_name"] = conn["target_name"]
    conn_dict["relationship"] = conn["relationship"]
    if conn["lb"] is not None:
        conn_dict["lb"] = conn["lb"]
    if conn["lt"] is not None:
        conn_dict["lt"] = conn["lt"]
    if conn["rb"] is not None:
        conn_dict["rb"] = conn["rb"]
    if conn["rt"] is not None:
        conn_dict["rt"] = conn["rt"]
    return conn_dict


def shorten_json(json_data):
    data_model = {}

    data_model["elements"] = _shorten_elements(json_data["elements"])

    connectors = []
    for conn in json_data["connectors"]:
        connectors.append(_shorten_connector(conn))

    data_model["connectors"] = connectors

    return data_model
