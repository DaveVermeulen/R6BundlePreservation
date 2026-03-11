import requests
import json
import os
import mesh_to_obj
import time
import glob
from typing import Optional

asset_delivery_url = "https://assetdelivery.roblox.com/v1/asset/?id="
json_path = "./BundleList.json"
   
def handle_asset(tex_dir, tex_id, mesh_dir: Optional[str] = None, mesh_id: Optional[int] = None):
    mesh_skipped = False
    tex_skipped = False    
    if not tex_dir or not tex_id:
        return print("Texture path or id missing!")
    
    # Get texture from asset delivery and save to disk
    texture_file_location = os.path.join(tex_dir + "\\" + str(tex_id) + ".png")
    if not os.path.isfile(texture_file_location): # if file already exists, don't overwrite
        texture_binary = requests.get(asset_delivery_url + str(tex_id)).content
        with open(texture_file_location, 'wb') as texture_data:
            texture_data.write(texture_binary)
    else:
        tex_skipped = True
    
    if not mesh_dir or not mesh_id:
        mesh_skipped = True
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
    else: 
        mesh_skipped = True
        
    if not mesh_skipped and not tex_skipped:
        # Avoid rate limits in loops
        time.sleep(1)
        
def asset_id_to_id(asset_id: str):
    return int(asset_id.split("//").pop())

def handle_bundle_data(bundle_data):
    base_dir = os.getcwd()
    
    # Check to see if its a Marketplace or Canceled bundle
    # Then sets the path to the bundle folder
    if "Id" in bundle_data:
        print("Marketplace Bundle")
        market_bundle_dir = os.path.join(base_dir, r'Bundles')
        bundle_id_string = "bundle_" + str(bundle_data["Id"]).zfill(3)
        bundle_dir = glob.glob(os.path.join(market_bundle_dir, bundle_id_string) + "*")[0]
        base_dir = bundle_dir
    else:
        print("Canceled Bundle")
        canceled_bundle_dir = os.path.join(base_dir, r'CanceledBundles')
        bundle_dir = os.path.join(canceled_bundle_dir, bundle_data["Name"])
        base_dir = bundle_dir
    
    # Set path to textures folder, creates if it does not exist yet
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

with open(json_path, 'r', encoding='utf8') as file:
    data = json.load(file)
    
handle_bundle_data(data[0])

# for bundle in data:
#     handle_bundle_data(bundle)

# # Checks if the content of the response is a PNG
# file_type = ""
# if response.content[:8] == b'\x89PNG\r\n\x1a\n':
#     file_type = ".png"
# else:
#     file_type = ".mesh"    



