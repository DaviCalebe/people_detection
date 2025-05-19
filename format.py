import json
import re
import os

def slugify(text, upper=False):
    """Sanitize text: remove accents/specials, replace spaces and dashes with underscores. Set upper=True for uppercase."""
    text = re.sub(r"[^\w\s-]", "", text)  # remove punctuation
    text = re.sub(r"[-\s]+", "_", text.strip())  # replace spaces and dashes with underscore
    return text.upper() if upper else text.lower()

def sanitize_remote_url(remote_url):
    """Replace 'Indisponível' values with None in remoteUrl dict"""
    sanitized = {}
    for key, value in remote_url.items():
        sanitized[key] = None if value.strip().lower() == "indisponível" else value
    return sanitized

def import_json_to_structure(input_file, server_id, output_file="unified_inventory.json"):
    """
    Load a raw JSON file from a server, format and integrate it into a unified structure.
    
    Parameters:
    - input_file (str): path to the raw JSON file from one server
    - server_id (str): unique identifier for the server (e.g., "server1", "server2")
    - output_file (str): path to the final unified JSON (default: unified_inventory.json)
    """

    # Load raw data from file
    with open(input_file, 'r', encoding='utf-8') as f:
        raw_data = json.load(f)

    # Load or create the final structure
    if os.path.exists(output_file):
        with open(output_file, 'r', encoding='utf-8') as f:
            structure = json.load(f)
    else:
        structure = {"servers": {}}

    # Initialize the server structure if not present
    if server_id not in structure["servers"]:
        structure["servers"][server_id] = {"recorders": {}}

    # Process each recorder
    for recorder in raw_data:
        recorder_key = slugify(recorder["name"], upper=True)
        recorder_guid = recorder["guid"]

        recorder_object = {
            "guid": recorder_guid,
            "cameras": {}
        }

        for camera in recorder.get("cameras", []):
            camera_key = slugify(camera["name"], upper=False)
            sanitized_streams = []
            for stream in camera.get("streams", []):
                stream_copy = stream.copy()
                stream_copy["remoteUrl"] = sanitize_remote_url(stream["remoteUrl"])
                sanitized_streams.append(stream_copy)

            recorder_object["cameras"][camera_key] = {
                "id": camera["id"],
                "streams": sanitized_streams
            }

        # Add to structure
        structure["servers"][server_id]["recorders"][recorder_key] = recorder_object

    # Save updated structure to file
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(structure, f, indent=2, ensure_ascii=False)

    print(f"Imported '{input_file}' under server '{server_id}' -> saved to '{output_file}'")


import_json_to_structure("recorders_data_20250516_200943.json", "server2")