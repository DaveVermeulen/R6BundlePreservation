Repository to store blocky roblox packages in R6 format.

Mostly made to use by myself, i wanted to have obj copies of these packages before anything could happen to these files.

Contains 2 Roblox Studio plugins and one Python script to be used with one of the plugins.

How to use:

Set the export paths in the scripts

Use the LoadBundles plugin in Roblox Studio to load every bundle into the scene.
This will also create modulescripts containing a json of all the related data to download and reference the parts directly from the Roblox site.

If you want to export to OBJ from studio:
Move the Bundles folder to ServerStorage and run the python script (python and lua script need the same export path)
Run the Export Bundles script, which will prompt you to save to obj every couple seconds to the export path.
