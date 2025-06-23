"""Simple build script for creating executable file"""

import sys
import subprocess
import platform
from pathlib import Path

def get_platform_name():
    """Get platform name for the executable filename"""
    system = platform.system().lower()
    if system == "windows":
        return "windows"
    elif system == "linux":
        return "linux"
    elif system == "darwin":
        return "macos"
    else:
        return system

def main():
    print("Building aseprite-extension-toolkit...")
    
    if not Path("extension-toolkit.py").exists():
        print("Error: extension-toolkit.py not found!")
        return 1

    platform_name = get_platform_name()
    executable_name = f"aseprite-extension-toolkit-{platform_name}"
    
    print(f"Building for platform: {platform_name}")

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--name", executable_name,
        "extension-toolkit.py"
    ]
    
    try:
        subprocess.run(cmd, check=True)
        print(f"Build complete! Check dist/ folder for {executable_name}")
        return 0
    except subprocess.CalledProcessError:
        print("Build failed!")
        return 1

if __name__ == "__main__":
    exit(main())
