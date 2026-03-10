import requests
import json
import os
import mesh_to_obj
import time

asset_delivery_url = "https://assetdelivery.roblox.com/v1/asset/?id="
json_path = "./BundleListCanceled.json"

current_directory = os.getcwd()
final_directory = os.path.join(current_directory, r'new_folder')
if not os.path.exists(final_directory):
   os.makedirs(final_directory)

def handle_bundle_data(bundle_data):
    print("handle")
    
    # handle body parts
    for body_part in bundle_data["CharacterMeshes"]:
        # Init directories
        texture_dir = os.path.join(final_directory, r'Textures')
        if not os.path.exists(texture_dir):
            os.makedirs(texture_dir)
            
        body_part_dir = os.path.join(final_directory, body_part["BodyPart"])
        if not os.path.exists(body_part_dir):
            os.makedirs(body_part_dir)
        
        # Get textures and meshes from url and save them to disk
        texture_file_location = os.path.join(texture_dir + "\\" + str(body_part['BaseTextureId']) + ".png")
        if not os.path.isfile(texture_file_location):
            texture_binary = requests.get(asset_delivery_url + str(body_part['BaseTextureId'])).content
            with open(texture_file_location, 'wb') as texture_data:
                texture_data.write(texture_binary)
                
        mesh_file_location = os.path.join(body_part_dir + "\\" + str(body_part['MeshId']) + ".mesh")
        if not os.path.isfile(mesh_file_location):
            mesh_binary = requests.get(asset_delivery_url + str(body_part['MeshId'])).content
            with open(mesh_file_location, 'wb') as mesh_data:
                mesh_data.write(mesh_binary)
        
            # Convert .mesh to .obj        
            with open(mesh_file_location, 'rb') as f:
                read_mesh_data = f.read()
                
            mesh = mesh_to_obj.RobloxMeshParser.parse(read_mesh_data)
            mesh_to_obj.mesh_to_obj(mesh, (body_part_dir + "/" + str(body_part['MeshId']) + ".obj" ), texture_file_location)
        
        # Wait to avoid rate limits
        time.sleep(1)
        print(body_part)

with open(json_path, 'r') as file:
    data = json.load(file)
    
handle_bundle_data(data[6])

# # Checks if the content of the response is a PNG
# file_type = ""
# if response.content[:8] == b'\x89PNG\r\n\x1a\n':
#     file_type = ".png"
# else:
#     file_type = ".mesh"    



