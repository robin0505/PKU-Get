#!/usr/bin/env python3
"""
Build script for PKU-Get application
Usage: uv run build.py
"""

import sys
import io

# Fix encoding issues on Windows - MUST be done before any other code
if sys.platform == 'win32':
    # Reconfigure stdout and stderr to use UTF-8
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    if hasattr(sys.stderr, 'buffer'):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

import subprocess
import shutil
from pathlib import Path

def run_command(cmd, cwd=None):
    """Run shell command and print output"""
    print(f"\n{'='*60}")
    print(f"Running: {cmd}")
    print(f"{'='*60}")
    result = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=False, text=True)
    if result.returncode != 0:
        print(f"❌ Command failed with exit code {result.returncode}")
        sys.exit(1)
    print("✅ Command completed successfully")

def main():
    project_root = Path(__file__).parent
    gui_dir = project_root / "gui"
    dist_dir = project_root / "dist"
    
    print("""
╔═══════════════════════════════════════╗
║     PKU-Get Build Script              ║
║     Building Desktop Application      ║
╚═══════════════════════════════════════╝
""")
    
    # Step 1: Build frontend
    print("\n📦 Step 1/3: Building React frontend...")
    if not gui_dir.exists():
        print(f"❌ GUI directory not found: {gui_dir}")
        sys.exit(1)
    
    run_command("npm install", cwd=gui_dir)
    run_command("npm run build", cwd=gui_dir)
    
    # Step 2: Install PyInstaller if not present
    print("\n📦 Step 2/3: Ensuring PyInstaller is available...")
    try:
        import PyInstaller
        print("✅ PyInstaller is already installed")
    except ImportError:
        print("Installing PyInstaller...")
        run_command("uv pip install pyinstaller")
    
    # Step 3: Build executable
    print("\n📦 Step 3/3: Building executable with PyInstaller...")
    
    # Clean previous builds
    if dist_dir.exists():
        print(f"Cleaning previous build: {dist_dir}")
        shutil.rmtree(dist_dir)
    
    build_dir = project_root / "build"
    if build_dir.exists():
        print(f"Cleaning build artifacts: {build_dir}")
        shutil.rmtree(build_dir)
    
    # PyInstaller command
    pyinstaller_cmd = [
        "pyinstaller",
        "--name=PKU-Get",
        "--windowed",  # No console window
        "--onefile",   # Single executable
        f"--add-data=gui/dist{';' if sys.platform == 'win32' else ':'}gui/dist",
        # Note: icon removed - SVG not supported, would need ICO format
        "--clean",
        "gui.py"
    ]
    
    pyinstaller_cmd = [arg for arg in pyinstaller_cmd if arg]  # Remove empty args
    run_command(" ".join(pyinstaller_cmd), cwd=project_root)
    
    print(f"""
╔═══════════════════════════════════════╗
║   ✅ Build completed successfully!   ║
╚═══════════════════════════════════════╝

📁 Executable location: {dist_dir / 'PKU-Get.exe' if sys.platform == 'win32' else dist_dir / 'PKU-Get'}

To run the application:
  Windows: .\\dist\\PKU-Get.exe
  macOS/Linux: ./dist/PKU-Get
""")

if __name__ == "__main__":
    main()
