from typing import (
    Dict,
    Any,
)
from io import (
    BytesIO,
)
from streamlit import (
    session_state,
    image,
    download_button,
)
from clients import (
    MCPClient,
)
from .import_ttl import (
    ttl_to_json,
)
from .import_xml import (
    xml_to_json,
)
from .export_xml import (
    json_to_xml,
)
from .visualisation import (
    get_image_bytes,
)


# Function to import XML and convert it to JSON
async def upload_xml(
    uploaded_file: BytesIO,
) -> Dict[str, Any]:
    """
    Imports an XML file uploaded by the user and converts it to JSON.
    Adds a "Generated" package to the model for further modifications.

    :return: A dictionary containing the JSON representation of the XML file.
    """
    mcp_client: MCPClient = session_state["mcp_client"]
    
    # Read the first few bytes of the file to determine its type
    file_content = uploaded_file.read()
    uploaded_file.seek(0)  # Reset the file pointer after reading
    
    if b"<" in file_content[:10]:  # Check for XML-like content
        json_data = xml_to_json(uploaded_file)

        # Add a new package element to the model
        root_model_id = json_data["elements"][0]["ID"]
        session_state["package"] = root_model_id
        session_state["ID"] = mcp_client._generate_id()
        json_data["elements"].append({
            "name": "Generated",
            "ID": session_state["ID"],
            "type": "uml:Package",
            "package": session_state["package"],
            "tags": []
        })

    elif b"@prefix" in file_content[:100]:  # Check for TTL-like content
        json_data = ttl_to_json(uploaded_file)
        
    else:
        raise ValueError("Unsupported file format. Please upload an XMI or TTL file.")

    async with mcp_client:
        model = await mcp_client.upload_model({"model": json_data})

    return model


def download_xml(
    json_data: Dict[str, Any],
) -> None:
    bytes_data = json_to_xml(json_data)
    download_button(
        label="Download model",
        data=bytes_data,
        file_name="export.xml",
        mime="application/xml",
    )
    return


def visualise(
    json_data: Dict[str, Any],
) -> None:
    image_bytes = get_image_bytes(json_data)
    image(image_bytes)
    return
