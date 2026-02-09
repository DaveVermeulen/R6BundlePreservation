local Selection = game:GetService("Selection")
local toolbar = plugin:CreateToolbar("ExportBundles")
local pluginButton = toolbar:CreateButton("ExportBundles", "Export bundles to OBJ", "", "")
pluginButton.ClickableWhenViewportHidden = true
local ServerStorage = game:GetService("ServerStorage")
local Folder = ServerStorage:FindFirstChild("Bundles") or Instance.new("Folder")

pluginButton.Click:Connect(function()
	local Bundles = Folder:GetChildren()
	
	table.sort(Bundles, function(a, b) return a.Name < b.Name end)
	
	print(pairs(Bundles))
	for _, bundle in pairs(Bundles) do
		if bundle:IsA("ModuleScript") then continue end
		bundle.Parent = workspace
		wait(2)
		-- Set selection
		Selection:Set({ bundle })
		-- Export using the plugin object directly
		local exportSuccess, exportError = pcall(function()
			PluginManager():ExportSelection(
				"C:/Users/"
					.. bundle.Name
					.. ".obj"
			)
		end)
		if exportSuccess then
			print("Successfully exported bundle")
		else
			warn("Failed to export:", exportError)
		end
		task.wait(3)
		bundle.Parent = Folder
	end
end)

	