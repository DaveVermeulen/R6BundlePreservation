local Selection = game:GetService("Selection")
local toolbar = plugin:CreateToolbar("ExportBundles")
local pluginButton = toolbar:CreateButton("ExportBundles", "Export bundles to OBJ", "", "")
pluginButton.ClickableWhenViewportHidden = true
local Folder = workspace:FindFirstChild("Bundles") or Instance.new("Folder")

pluginButton.Click:Connect(function()
	for _, bundle in pairs(Folder:GetChildren()) do
		-- MOVE TO 2ND PLUGIN SCRIPT
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
	end)
end)

	