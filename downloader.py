import requests
import json
import os
import mesh_to_obj
import time
from typing import Optional

asset_delivery_url = "https://assetdelivery.roblox.com/v1/asset/?id="
json_path = "./BundleListCanceled.json"

# TODO: Move to handle_bundle_data, and get either bundle id or the name of the bundle to find the correct directory
current_directory = os.getcwd()
final_directory = os.path.join(current_directory, r'new_folder')
if not os.path.exists(final_directory):
   os.makedirs(final_directory)
   
def handle_asset(tex_dir, tex_id, mesh_dir: Optional[str] = None, mesh_id: Optional[int] = None):
    # Avoid rate limits in loops
    time.sleep(1)
    
    if not tex_dir or not tex_id:
        return print("Texture path or id missing!")
    
    # Get texture from asset delivery and save to disk
    texture_file_location = os.path.join(tex_dir + "\\" + str(tex_id) + ".png")
    if not os.path.isfile(texture_file_location): # if file already exists, don't overwrite
        texture_binary = requests.get(asset_delivery_url + str(tex_id)).content
        with open(texture_file_location, 'wb') as texture_data:
            texture_data.write(texture_binary)
    
    if not mesh_dir or not mesh_id:
        return print("Mesh path or id missing, skipping.")
    
    # Get mesh from asset delivery and save to disk
    mesh_file_location = os.path.join(mesh_dir + "\\" + str(mesh_id) + ".mesh")
    if not os.path.isfile(mesh_file_location): # if file already exists, don't overwrite
        mesh_binary = requests.get(asset_delivery_url + str(mesh_id)).content
        with open(mesh_file_location, 'wb') as mesh_data:
            mesh_data.write(mesh_binary)
    
        # Convert .mesh to .obj        
        with open(mesh_file_location, 'rb') as f:
            read_mesh_data = f.read()
        mesh = mesh_to_obj.RobloxMeshParser.parse(read_mesh_data)
        mesh_to_obj.mesh_to_obj(mesh, (mesh_dir + "/" + str(mesh_id) + ".obj" ), texture_file_location)
        
def asset_id_to_id(asset_id: str):
    return int(asset_id.split("//").pop())

def handle_bundle_data(bundle_data):
    base_dir = os.getcwd()
    canceled_bundle = False
        
    # find the right dir based on bundle name or id
    # Generally means if it has an ID it's an existing bundle, and if not it's a canceled bundle. 
    # The difference is important as RBXM files are impossible to download straight from the site.
    if "Id" in bundle_data:
        print("Marketplace Bundle")
        base_dir = final_directory
    else:
        print("Canceled Bundle")
        base_dir = final_directory
    
    texture_dir = os.path.join(base_dir, r'Textures')
    if not os.path.exists(texture_dir):
        os.makedirs(texture_dir)
    
    # Handle body parts
    for body_part in bundle_data["CharacterMeshes"]:
        body_part_dir = os.path.join(base_dir, r'BodyParts', body_part["BodyPart"])
        if not os.path.exists(body_part_dir):
            os.makedirs(body_part_dir)
        
        handle_asset(
            texture_dir, 
            body_part['BaseTextureId'], 
            body_part_dir, 
            body_part['MeshId']
            )
        
    # Handle accessories
    for accessory in bundle_data["Accessories"]:
        accessory_dir = os.path.join(base_dir, r'Accessories', accessory["Name"])
        if not os.path.exists(accessory_dir):
            os.makedirs(accessory_dir)
        
        handle_asset(
            texture_dir, 
            asset_id_to_id(accessory['TextureId']), 
            accessory_dir, 
            asset_id_to_id(accessory['MeshId'])
            )    
    
    # Handle head meshes and face textures (if present) 'Head'
    if ("HeadData" in bundle_data) and (len(bundle_data["HeadData"]) > 0):
        for head_data in bundle_data["HeadData"]:
            if head_data["BodyPart"] == "Head":
                head_dir = os.path.join(base_dir, r'BodyParts', r'Head')
                if not os.path.exists(head_dir):
                    os.makedirs(head_dir)
                    
                handle_asset(
                    texture_dir, 
                    asset_id_to_id(head_data["TextureId"]),
                    head_dir,
                    asset_id_to_id(head_data["MeshId"])
                    )
                
            elif head_data["BodyPart"] == "Face":
                handle_asset(
                    texture_dir, 
                    asset_id_to_id(head_data["TextureId"])
                    )
    
    #TODO:
    # Download RBXMs from Items when its a regular bundle 'GeneratedRXBMs'

with open(json_path, 'r') as file:
    data = json.load(file)
    
handle_bundle_data(data[73])

# for bundle in data:
#     handle_bundle_data(bundle)

# # Checks if the content of the response is a PNG
# file_type = ""
# if response.content[:8] == b'\x89PNG\r\n\x1a\n':
#     file_type = ".png"
# else:
#     file_type = ".mesh"    



