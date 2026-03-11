import os
import sys
import time
import shutil
import re
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class BundleOrganizer(FileSystemEventHandler):
    def __init__(self, watch_dir):
        self.watch_dir = Path(watch_dir)
        self.processed_files = set()
        self.processing_lock = False
        
    def on_created(self, event):
        if event.is_directory:
            return
            
        file_path = Path(event.src_path)
        file_ext = file_path.suffix.lower()
        
        # Only process obj, mtl, and png files
        if file_ext not in ['.obj', '.mtl', '.png']:
            return
            
        # Avoid processing the same file twice
        if str(file_path) in self.processed_files:
            return
            
        print(f"Detected new file: {file_path.name}")
        
        # Wait a moment to ensure file is fully written
        time.sleep(1)
        
        # If it's an OBJ file, process the bundle
        if file_ext == '.obj':
            # Wait to ensure all files are written
            time.sleep(0.5)
            self.process_bundle(file_path)
    
    def on_modified(self, event):
        # Sometimes files trigger modified instead of created
        if event.is_directory:
            return
            
        file_path = Path(event.src_path)
        file_ext = file_path.suffix.lower()
        
        if file_ext == '.obj' and str(file_path) not in self.processed_files:
            print(f"Detected modified file: {file_path.name}")
            time.sleep(1)
            self.process_bundle(file_path)
    
    def process_bundle(self, obj_path):
        """Process an OBJ file and move it with its associated files"""
        
        # Check if file still exists (might have been moved already)
        if not obj_path.exists():
            print(f"  File already processed or doesn't exist")
            return
            
        # Mark as being processed
        if self.processing_lock:
            return
        self.processing_lock = True
        
        try:
            obj_name = obj_path.stem  # Filename without extension
            
            # Create destination folder
            dest_folder = self.watch_dir / obj_name
            dest_folder.mkdir(exist_ok=True)
            
            print(f"\n{'='*50}")
            print(f"Processing bundle: {obj_name}")
            print(f"{'='*50}")
            
            # Find associated MTL file
            mtl_path = obj_path.with_suffix('.mtl')
            png_files = []
            
            if mtl_path.exists():
                # Parse MTL to find referenced PNG files
                png_files = self.extract_textures_from_mtl(mtl_path)
            
            # Move OBJ file
            if obj_path.exists():
                shutil.move(str(obj_path), str(dest_folder / obj_path.name))
                self.processed_files.add(str(obj_path))
                print(f"  ✓ Moved: {obj_path.name}")
            
            # Move MTL file
            if mtl_path.exists():
                shutil.move(str(mtl_path), str(dest_folder / mtl_path.name))
                self.processed_files.add(str(mtl_path))
                print(f"  ✓ Moved: {mtl_path.name}")
            
            # Move PNG files
            for png_name in png_files:
                png_path = self.watch_dir / png_name
                if png_path.exists():
                    shutil.move(str(png_path), str(dest_folder / png_name))
                    self.processed_files.add(str(png_path))
                    print(f"  ✓ Moved: {png_name}")
            
            print(f"\n✓ Bundle organized successfully!")
            print(f"Waiting for next bundle...\n")
            
        except Exception as e:
            print(f"Error processing bundle: {e}")
        finally:
            self.processing_lock = False
    
    def extract_textures_from_mtl(self, mtl_path):
        """Extract texture filenames from MTL file"""
        textures = []
        
        try:
            with open(mtl_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    # Look for texture map declarations
                    if line.startswith('map_Kd') or line.startswith('map_Ka') or line.startswith('map_Ks'):
                        # Extract filename (everything after the command)
                        parts = line.split()
                        if len(parts) > 1:
                            texture_name = parts[1]
                            # Remove any path separators, keep just filename
                            texture_name = os.path.basename(texture_name)
                            if texture_name not in textures:
                                textures.append(texture_name)
        except Exception as e:
            print(f"  Warning: Could not read MTL file: {e}")
        
        return textures

def main():
    if len(sys.argv) < 2:
        print("Usage: py MoveExportsToFolders.py \"path\"")
        sys.exit(1)
    watch_directory = sys.argv[1]
    
    print("="*60)
    print("ROBLOX BUNDLE ORGANIZER - RUNNING")
    print("="*60)
    print(f"Monitoring: {watch_directory}")
    print("Press Ctrl+C to stop")
    print("="*60)
    print("\nWaiting for new bundles...\n")
    
    # Create event handler and observer
    event_handler = BundleOrganizer(watch_directory)
    observer = Observer()
    observer.schedule(event_handler, watch_directory, recursive=False)
    observer.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        print("\n\nStopping monitor...")
    
    observer.join()
    print("Monitor stopped.")

if __name__ == "__main__":
    main()