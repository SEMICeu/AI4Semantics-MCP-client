from io import BytesIO
import rdflib

def ttl_to_json(uploaded_file):
    """
    Imports a TTL file, parses it as an RDF graph, and retrieves the concepts as a pandas DataFrame.  
  
    :param uploaded_file: The uploaded TTL file to be imported.  
    :return: A tuple containing the parsed RDF graph and a pandas DataFrame with the concepts.  
    """
    bytes_data = BytesIO(uploaded_file.read())

    g = rdflib.Graph()
    g.parse(bytes_data, format="ttl")
    
    # Serialize the graph to JSON-LD
    json_ld_data = g.serialize(format="json-ld", indent=4)

    # Convert the JSON-LD string to a Python dictionary
    import json
    json_data = json.loads(json_ld_data)

    return {
        "ttl": json_data
    }

