# Aseprite Extension Toolkit

![Aseprite](https://img.shields.io/badge/Aseprite-1.3+-white.svg)
![Python](https://img.shields.io/badge/Python-3.12+-green.svg)
![License](https://img.shields.io/badge/License-MIT-blue.svg)

Development tool for packaging and live-reloading Aseprite extensions (you still need to restart Aseprite to see the extension changes).

## Features

- Package extension into `.aseprite-extension` archive
- Live reload extension during development
- Automatic installation to Aseprite extensions folder
- Extension structure validation
- Cross-platform support (Windows, macOS, Linux) (tested on Windows 11)

## Installation

### Using executable file

1. Go to [Releases](https://github.com/fresh-milkshake/aseprite-extension-toolkit/releases) and download the latest executable file.
2. Run the executable file.

### Using python

1. Clone the repository `git clone https://github.com/fresh-milkshake/aseprite-extension-toolkit`
2. Install dependencies `uv sync` or `pip install -r pyproject.toml`
3. Activate virtual environment if used and run the script `uv run extension-toolkit.py` (or `python extension-toolkit.py`)

## Extension Structure

Required structure:

```
my-extension/
├── package.json          # Extension configuration
├── extension.lua         # Main script
└── scripts/              # Additional scripts (optional)
    ├── other.lua
    └── ...
```

> Note: assets packing are not supported yet, only code files are packed.

## How It Works

### Packaging
1. Scans extension directory for `package.json`
2. Validates configuration
3. Collects code files
4. Creates `.aseprite-extension` archive

### Live Reload
1. Scans extension directory for `package.json`
2. Validates configuration
3. Generates `extension.json` and `__info.json` for Aseprite
4. Monitors file changes in extension directory
5. Automatically copies extension to Aseprite folder
6. You can restart Aseprite to see the changes whenever you want

## Extensions Directory Default

Default locations:

- Windows: `%APPDATA%/Aseprite/extensions`
- macOS: `~/Library/Application Support/Aseprite/extensions`
- Linux: `~/.config/Aseprite/extensions`

## Command Line Options

```
Usage: extension-toolkit.py [OPTIONS] COMMAND [ARGS]...

  Aseprite extension packaging and live reloading tool

Options:
  -h, --help  Show this message and exit.

Commands:
  live-reload  Watch for changes and auto-reload extension
  pack         Pack extension into .aseprite-extension file
```

### `pack`

```
Usage: extension-toolkit.py pack [OPTIONS] EXTENSION_PATH

  Pack extension into .aseprite-extension file

Options:
  -c, --clean             Clean previous builds first
  -i, --install           Install to Aseprite after build
  -o, --output TEXT       Custom output name (without extension)
  --output-dir DIRECTORY  Output directory (default: extension directory)
  -h, --help              Show this message and exit.
```

### `live-reload`

```
Usage: extension-toolkit.py live-reload [OPTIONS] EXTENSION_PATH

  Watch for changes and auto-reload extension

Options:
  -d, --debounce FLOAT        Debounce time in seconds (default: 1.0)
  --extensions-dir DIRECTORY  Custom Aseprite extensions directory
  -h, --help                  Show this message and exit.
```

## License

This project is licensed under the [MIT License](LICENSE.txt). Please see the [LICENSE](LICENSE.txt) file for more information.