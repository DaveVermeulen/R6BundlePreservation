local AssetService = game:GetService("AssetService")
local HttpService = game:GetService("HttpService")
local Players = game:GetService("Players")
local Selection = game:GetService("Selection")
local toolbar = plugin:CreateToolbar("LoadBundles")
local pluginButton = toolbar:CreateButton("LoadBundles", "Loads bundles into scene, with json data", "", "")
pluginButton.ClickableWhenViewportHidden = true
local bundleData = {}
local bundlePartData = {}
local bundleRange = 320 -- from 0 to range --320 by default
local waitTime = 3

-- Animation Packs and incompatible bundles.
local IgnoreBundles = {32,33,34,39,43,48,55,56,61,62,63,68,75,79,80,81,82,83,91,92,315,317}
local ExtraBundles = {438,410,854,382,419,427,857,381,426,855}

local Folder = workspace:FindFirstChild("Bundles") or Instance.new("Folder")
Folder.Name = "Bundles"
Folder.Parent = workspace

local function parameterize(str)
	return str
		:lower()
		:gsub("[^%w%s]", "")  -- remove punctuation
		:gsub("%s+", "_")     -- spaces -> underscore
end

function GetCharacterMeshData(rig)
	local meshData = {}

	for _, child in pairs(rig:GetDescendants()) do
		if child:IsA("CharacterMesh") then
			table.insert(meshData, {
				BaseTextureId = child.BaseTextureId,
				BodyPart = child.BodyPart.Name,
				MeshId = child.MeshId,
				OverlayTextureId = child.OverlayTextureId,
			})
		end
	end

	return meshData
end

function GetAccessoryData(rig)
	local accessoryData = {}

	for _, child in pairs(rig:GetChildren()) do
		if child:IsA("Accessory") then			
			local handle = child:FindFirstChild("Handle")
			if handle then
				local meshId = ""
				local textureId = ""
				local meshScale = ""

				-- Check for SpecialMesh
				local specialMesh = handle:FindFirstChildOfClass("SpecialMesh")
				if specialMesh then
					meshId = specialMesh.MeshId
					textureId = specialMesh.TextureId
					meshScale = tostring(specialMesh.Scale)
				end

				-- Check for MeshPart
				local meshPart = handle:IsA("MeshPart") and handle or nil
				if meshPart then
					meshId = meshPart.MeshId
					textureId = meshPart.TextureID
					meshScale = tostring(meshPart.Scale)
				end

				table.insert(accessoryData, {
					Name = child.Name,
					AccessoryType = child.AccessoryType.Name,
					MeshId = meshId,
					TextureId = textureId,
					AttachmentPointPos = tostring(child.AttachmentPoint.Position),
					AttachmentPointRot = tostring(child.AttachmentPoint.Rotation),
					RigHatAttachment = tostring(rig.Head.HatAttachment.Position)
				})
			end
		end
	end

	return accessoryData
end

function LoadBundle(Bundle, rigType)
	local OutfitID
	--export position for OBJ import in blender
	local BasePosRot = CFrame.new(0, 4.5, 0) * CFrame.Angles(0, math.rad(180), 0)
	-- Default to R6 if not specified
	rigType = rigType or Enum.HumanoidRigType.R6
	-- Check if Bundle and Items exist
	if not Bundle or not Bundle.Items then
		warn("Invalid bundle data")
		return nil
	end
	-- Find UserOutfit that's not a Head
	for i, v in pairs(Bundle.Items) do
		if v.Type == "UserOutfit" and not string.match(v.Name, "Head") then
			OutfitID = v.Id
			break
		end
	end
	-- Check if we found an OutfitID
	if not OutfitID then
		warn("No valid UserOutfit found in bundle:", Bundle.Name or "Unknown")
		-- Try to find ANY UserOutfit as fallback
		for i, v in pairs(Bundle.Items) do
			if v.Type == "UserOutfit" then
				OutfitID = v.Id
				print("Using outfit (including Head):", v.Name)
				break
			end
		end
	end
	-- Still no OutfitID? Can't proceed
	if not OutfitID then
		warn("Bundle has no UserOutfit items at all")
		return nil
	end
	-- Try to load the outfit
	local success, Description = pcall(function()
		return Players:GetHumanoidDescriptionFromOutfitIdAsync(OutfitID)
	end)
	if not success then
		warn("Failed to get humanoid description for outfit", OutfitID, ":", Description)
		return nil
	end
	-- Try to create the rig with specified rig type
	local success2, Rig = pcall(function()
		return Players:CreateHumanoidModelFromDescriptionAsync(Description, rigType)
	end)
	if not success2 then
		warn("Failed to create rig:", Rig)
		return nil
	end
	Rig:PivotTo(BasePosRot)

	Rig.Parent = workspace.Bundles
	Rig.Name = string.format("bundle_%03d_%s", Bundle.Id, parameterize(Bundle.Name))
	print("Successfully loaded", rigType.Name, "rig for bundle:", Bundle.Name or "Unknown")
	return Rig
end

function SaveDataInChunks(data, baseName, maxChars)
	local jsonData = HttpService:JSONEncode(data)
	local chunkSize = maxChars or 150000
	local chunks = {}
	local currentChunk = ""
	local inString = false
	local escapeNext = false
	local braceDepth = 0

	print("Total JSON size:", #jsonData, "chars")
	print("Splitting into chunks at object boundaries...")

	-- Simple approach: split the array at commas between objects
	if string.sub(jsonData, 1, 1) == "[" then
		-- It's an array, split between objects
		local objectStart = 1
		local depth = 0

		for i = 1, #jsonData do
			local char = string.sub(jsonData, i, i)

			-- Track string context to ignore brackets inside strings
			if char == '"' and not escapeNext then
				inString = not inString
			elseif char == "\\" then
				escapeNext = not escapeNext
			else
				escapeNext = false
			end

			if not inString then
				if char == "{" then
					depth = depth + 1
				elseif char == "}" then
					depth = depth - 1

					-- We've closed an object at the top level of the array
					if depth == 0 and i > objectStart then
						local potentialChunk = currentChunk .. string.sub(jsonData, objectStart, i)

						-- If adding this object would exceed limit and we have content, save chunk
						if #potentialChunk > chunkSize and #currentChunk > 0 then
							table.insert(chunks, currentChunk)
							currentChunk = string.sub(jsonData, objectStart, i)
						else
							currentChunk = potentialChunk
						end

						-- Look ahead for comma
						local nextPos = i + 1
						while nextPos <= #jsonData and string.match(string.sub(jsonData, nextPos, nextPos), "%s") do
							nextPos = nextPos + 1
						end

						if nextPos <= #jsonData and string.sub(jsonData, nextPos, nextPos) == "," then
							currentChunk = currentChunk .. ","
							objectStart = nextPos + 1
						else
							objectStart = nextPos
						end
					end
				end
			end
		end

		-- Add remaining content
		if #currentChunk > 0 then
			if objectStart <= #jsonData then
				currentChunk = currentChunk .. string.sub(jsonData, objectStart)
			end
			table.insert(chunks, currentChunk)
		end
	else
		-- Not an array, use simple character-based splitting
		local totalChunks = math.ceil(#jsonData / chunkSize)
		for i = 1, totalChunks do
			local startPos = (i - 1) * chunkSize + 1
			local endPos = math.min(i * chunkSize, #jsonData)
			table.insert(chunks, string.sub(jsonData, startPos, endPos))
		end
	end

	-- Save all chunks
	for i, chunk in ipairs(chunks) do
		local module = Instance.new("ModuleScript")
		module.Name = baseName .. "_Part" .. i .. "_of_" .. #chunks .. "_" .. os.time()
		module.Source = chunk
		module.Parent = workspace.Bundles

		print("Saved chunk", i, "of", #chunks, "(" .. #chunk .. " chars)")
	end

	print("Finished saving", baseName, "in", #chunks, "chunks")
end

function HandleBundle(id)
	local rig
	local success, bundleDetails = pcall(function()
		return AssetService:GetBundleDetailsAsync(id)
	end)
	if success and bundleDetails then
		print("Successfully loaded bundle", id)
		rig = LoadBundle(bundleDetails, Enum.HumanoidRigType.R6)
		if rig then
			-- Wait a moment for the rig to fully load
			task.wait(0.5)

			-- Extract CharacterMesh and Accessory data
			local characterMeshes = GetCharacterMeshData(rig)
			local accessories = GetAccessoryData(rig)

			-- Add the extracted data to bundle details
			bundleDetails.CharacterMeshes = characterMeshes
			bundleDetails.Accessories = accessories
			table.insert(bundleData, bundleDetails)
		end
	else
		warn("Failed to load bundle", id, ":", bundleDetails)
	end
end

pluginButton.Click:Connect(function()
	Folder:ClearAllChildren()
	for i = 1, bundleRange do
		if table.find(IgnoreBundles, i) then
			print("Skipping bundle", i)
			continue
		end

		HandleBundle(i)
		task.wait(waitTime)
	end

	for _, bundleId in ExtraBundles do
		--Handles specific bundles outside of the default 0-320 range, these are hand picked from the catalog
		HandleBundle(bundleId)
		task.wait(waitTime)
	end

	-- Save data in chunks
	print("=== Saving BundleData ===")
	SaveDataInChunks(bundleData, "BundleData")

	print("Successfully saved all bundle data in chunks.")
end)
