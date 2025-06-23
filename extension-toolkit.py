"""Aseprite Extension Toolkit main script"""

import json
import shutil
import sys
import time
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Set, Any
from dataclasses import dataclass

import click
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent

try:
    DEFAULT_EXTENSIONS_FOLDER: Path = {
        "linux": Path("~/.config/Aseprite/extensions"),
        "win32": Path("~/AppData/Roaming/Aseprite/extensions"),
        "darwin": Path("~/Library/Application Support/Aseprite/extensions"),
    }[sys.platform].expanduser().resolve()
except KeyError:
    click.echo(f"❌ Unsupported platform: {sys.platform}")
    sys.exit(1)


def print_header(title: str, width: int = 60) -> None:
    """Print a beautiful header with the given title"""
    title = title.strip()
    title_len = len(title)

    min_width = title_len + 8
    actual_width = max(width, min_width)

    total_padding = actual_width - title_len - 2
    left_padding = total_padding // 2
    right_padding = total_padding - left_padding - 1

    horizontal_line = "─" * (actual_width - 2)
    top_line = f"╭{horizontal_line}╮"
    middle_line = f"│{' ' * left_padding}{title}{' ' * right_padding}│"
    bottom_line = f"╰{horizontal_line}╯"

    click.echo()
    click.echo(top_line)
    click.echo(middle_line)
    click.echo(bottom_line)
    click.echo()


class ExtensionError(Exception):
    """Base exception for extension-related errors"""

    pass


class ValidationError(ExtensionError):
    """Raised when validation fails"""

    pass


class FileOperationError(ExtensionError):
    """Raised when file operations fail"""

    pass


@dataclass
class ExtensionConfig:
    """Configuration for an Aseprite extension"""

    name: str
    version: str
    main_script: str
    path: Path
    display_name: str = ""
    description: str = ""
    author: str = ""
    website: str = ""
    source: str = ""
    license: str = ""
    categories: Optional[List[str]] = None
    api_version: str = "1.3"

    def __post_init__(self):
        if self.categories is None:
            self.categories = ["Scripts"]

    @property
    def package_json(self) -> Path:
        return self.path / "package.json"

    @property
    def extension_keys(self) -> Path:
        return self.path / "extension-keys.aseprite-keys"

    @property
    def extension_json(self) -> Path:
        return self.path / "extension.json"

    @property
    def main_script_path(self) -> Path:
        return self.path / self.main_script

    @classmethod
    def from_path(cls, extension_path: Path) -> "ExtensionConfig":
        """Load extension configuration from package.json"""
        extension_path = extension_path.resolve()

        if not extension_path.exists():
            raise ValidationError(f"Extension path does not exist: {extension_path}")

        if not extension_path.is_dir():
            raise ValidationError(
                f"Extension path is not a directory: {extension_path}"
            )

        package_json_path = extension_path / "package.json"

        if not package_json_path.exists():
            raise ValidationError(f"package.json not found at {package_json_path}")

        try:
            with open(package_json_path, "r", encoding="utf-8") as f:
                data: Dict[str, Any] = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            raise ValidationError(f"Failed to read package.json: {e}")

        if not isinstance(data, dict):
            raise ValidationError("package.json must contain a JSON object")

        name = data.get("name", "").strip()
        if not name:
            raise ValidationError("Extension name is required in package.json")

        invalid_chars = '<>:"/\\|?*'
        if any(char in name for char in invalid_chars):
            raise ValidationError(
                f"Extension name contains invalid characters: {invalid_chars}"
            )

        main_script = "extension.lua"
        contributes = data.get("contributes", {})
        if isinstance(contributes, dict):
            scripts = contributes.get("scripts", [])
            if isinstance(scripts, list) and scripts:
                first_script = scripts[0]
                if isinstance(first_script, dict) and "path" in first_script:
                    script_path = first_script["path"].strip("./")
                    if script_path:
                        main_script = script_path

        author_info = data.get("author", {})
        if isinstance(author_info, str):
            author = author_info
            website = ""
        elif isinstance(author_info, dict):
            author = author_info.get("name", "")
            website = author_info.get("url", "")
        else:
            author = ""
            website = ""

        return cls(
            name=name,
            version=data.get("version", "1.0.0").strip() or "1.0.0",
            main_script=main_script,
            path=extension_path,
            display_name=data.get("displayName", name).strip() or name,
            description=data.get("description", "").strip(),
            author=author.strip(),
            website=website.strip(),
            source=website.strip(),
            license=data.get("license", "").strip(),
            categories=data.get("categories", ["Scripts"]),
            api_version="1.3",
        )

    def generate_extension_json(self) -> Dict[str, Any]:
        """Generate extension.json content from configuration"""
        return {
            "name": self.name,
            "displayName": self.display_name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "website": self.website,
            "source": self.source,
            "license": self.license,
            "categories": self.categories,
            "apiVersion": self.api_version,
            "main": f"./{self.main_script}",
        }


class ExtensionPacker:
    """Handles building and packaging Aseprite extensions"""

    def __init__(
        self, config: ExtensionConfig, extensions_folder: Optional[Path] = None
    ):
        self.config = config
        self.extensions_folder = extensions_folder or DEFAULT_EXTENSIONS_FOLDER
        self._validate_config()

    def _validate_config(self) -> None:
        """Validate extension configuration"""
        main_script_path = self.config.main_script_path
        if not main_script_path.exists():
            click.echo(f"⚠️  Main script not found: {main_script_path}")

        if not self.config.package_json.exists():
            click.echo(f"⚠️  package.json not found: {self.config.package_json}")

    def collect_scripts(self) -> List[Path]:
        """Collect all .lua scripts from the extension directory"""
        if not self.config.path.exists():
            click.echo(f"⚠️  Extension directory not found: {self.config.path}")
            return []

        try:
            scripts = list(self.config.path.rglob("*.lua"))
            if not scripts:
                click.echo("⚠️  No .lua scripts found in extension directory")
            return scripts
        except OSError as e:
            click.echo(f"⚠️  Error reading extension directory: {e}")
            return []

    def get_files_to_package(self, scripts: List[Path]) -> Set[Path]:
        """Get all files that should be included in the package"""
        files = {self.config.main_script_path, self.config.package_json, *scripts}

        if self.config.extension_keys.exists():
            files.add(self.config.extension_keys)

        existing_files = set()
        for file_path in files:
            if file_path.exists():
                existing_files.add(file_path)
            else:
                click.echo(f"⚠️  File not found: {file_path}")

        return existing_files

    def create_package(
        self, output_dir: Optional[Path] = None, custom_name: Optional[str] = None
    ) -> str:
        """Create .aseprite-extension package"""
        scripts = self.collect_scripts()
        files_to_include = self.get_files_to_package(scripts)

        if not files_to_include:
            raise FileOperationError(
                "No files to package! Check your extension structure."
            )

        package_name = custom_name or self.config.name
        output_filename = f"{package_name}-{self.config.version}.aseprite-extension"

        if output_dir:
            if not output_dir.exists():
                try:
                    output_dir.mkdir(parents=True, exist_ok=True)
                except OSError as e:
                    raise FileOperationError(f"Cannot create output directory: {e}")
            output_path = output_dir / output_filename
        else:
            output_path = self.config.path / output_filename

        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            test_file = output_path.parent / ".write_test"
            test_file.touch()
            test_file.unlink()
        except OSError as e:
            raise FileOperationError(f"Cannot write to output location: {e}")

        print_header("🔧 Aseprite Extension Packaging Tool")
        click.echo(f"📦 Creating: {package_name} v{self.config.version}")
        click.echo(f"📁 Source: {self.config.path}")
        click.echo(f"📂 Packaging {len(files_to_include)} files...")

        temp_extension_json = self.config.path / "extension.json"
        extension_json_data = self.config.generate_extension_json()

        try:
            with open(temp_extension_json, "w", encoding="utf-8") as f:
                json.dump(extension_json_data, f, ensure_ascii=False, indent=2)

            files_to_include.add(temp_extension_json)

            self._create_zip_package(files_to_include, output_path)
            self._show_package_info(output_path)

        finally:
            if temp_extension_json.exists():
                try:
                    temp_extension_json.unlink()
                except OSError:
                    pass

        return str(output_path)

    def _create_zip_package(self, files: Set[Path], output_path: Path) -> None:
        """Create ZIP package with all files"""
        try:
            with zipfile.ZipFile(
                output_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9
            ) as zipf:
                for file_path in files:
                    try:
                        arcname = self._get_archive_name(file_path)
                        zipf.write(file_path, arcname)
                        click.echo(f"  📄 {file_path.name} -> {arcname}")
                    except OSError as e:
                        click.echo(f"  ⚠️  Skipping {file_path.name}: {e}")
                        continue
        except Exception as e:
            if output_path.exists():
                try:
                    output_path.unlink()
                except OSError:
                    pass
            raise FileOperationError(f"Failed to create package: {e}")

    def _get_archive_name(self, file_path: Path) -> str:
        """Get the archive name for a file preserving structure"""
        if file_path.is_relative_to(self.config.path):
            return str(file_path.relative_to(self.config.path).as_posix())
        return file_path.name

    def _show_package_info(self, output_path: Path) -> None:
        """Display package information"""
        try:
            file_size = output_path.stat().st_size
            size_str = self._format_file_size(file_size)

            click.echo(f"\n✅ Extension created: {output_path}")
            click.echo(f"📊 File size: {size_str}")
            click.echo("\n🎉 Extension ready for installation!")
        except OSError as e:
            click.echo(f"⚠️  Could not get file info: {e}")

    @staticmethod
    def _format_file_size(size: int) -> str:
        """Format file size in human readable format"""
        if size < 1024:
            return f"{size} bytes"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        else:
            return f"{size / (1024 * 1024):.1f} MB"

    def install_to_aseprite(self) -> bool:
        """Install extension directly to Aseprite extensions folder"""
        try:
            if not self.extensions_folder.exists():
                try:
                    self.extensions_folder.mkdir(parents=True, exist_ok=True)
                except OSError as e:
                    click.echo(f"❌ Cannot create extensions folder: {e}")
                    return False

            try:
                test_file = self.extensions_folder / ".write_test"
                test_file.touch()
                test_file.unlink()
            except OSError as e:
                click.echo(f"❌ No write access to extensions folder: {e}")
                return False

            scripts = self.collect_scripts()
            extension_folder = self.extensions_folder / self.config.name

            if extension_folder.exists():
                try:
                    shutil.rmtree(extension_folder)
                except OSError as e:
                    click.echo(f"❌ Cannot remove existing extension: {e}")
                    return False

            try:
                extension_folder.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                click.echo(f"❌ Cannot create extension folder: {e}")
                return False

            click.echo(f"✅ Created extension folder: {extension_folder}")

            files_to_copy = [
                *scripts,
                self.config.package_json,
                self.config.extension_keys,
            ]

            if not self._copy_files_to_folder(files_to_copy, extension_folder):
                return False

            self._generate_extension_json(extension_folder)
            self._create_info_json(scripts, extension_folder)

            click.echo(f"🔄 Extension {self.config.name} updated in Aseprite!")
            return True

        except Exception as e:
            click.echo(f"❌ Unexpected error during installation: {e}")
            return False

    def _copy_files_to_folder(self, files: List[Path], target_folder: Path) -> bool:
        """Copy files to target folder preserving structure"""
        success = True

        for file_path in files:
            if not file_path.exists():
                continue

            try:
                if file_path.is_relative_to(self.config.path):
                    relative_path = file_path.relative_to(self.config.path)
                    target_path = target_folder / relative_path
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                else:
                    target_path = target_folder / file_path.name

                shutil.copy2(file_path, target_path)
                click.echo(f"✅ Copied: {file_path.name}")

            except OSError as e:
                click.echo(f"⚠️  Failed to copy {file_path.name}: {e}")
                success = False
                continue

        return success

    def _generate_extension_json(self, target_folder: Path) -> None:
        """Generate extension.json dynamically"""
        extension_json = self.config.generate_extension_json()
        extension_json_path = target_folder / "extension.json"

        try:
            with open(extension_json_path, "w", encoding="utf-8") as f:
                json.dump(extension_json, f, ensure_ascii=False, indent=2)
            click.echo("✅ extension.json created")
        except OSError as e:
            click.echo(f"⚠️  Failed to create extension.json: {e}")

    def _create_info_json(self, scripts: List[Path], target_folder: Path) -> None:
        """Create __info.json file for Aseprite"""
        installed_files = []

        for script in scripts:
            if script.is_relative_to(self.config.path):
                relative_path = script.relative_to(self.config.path)
                installed_files.append(str(relative_path.as_posix()))
            else:
                installed_files.append(script.name)

        installed_files.extend(["extension.json", "package.json"])

        if self.config.extension_keys.exists():
            installed_files.append(self.config.extension_keys.name)

        info_data = {"installedFiles": installed_files}
        info_path = target_folder / "__info.json"

        try:
            with open(info_path, "w", encoding="utf-8") as f:
                json.dump(info_data, f, ensure_ascii=False, indent=2)
            click.echo("✅ __info.json created")
        except OSError as e:
            click.echo(f"⚠️  Failed to create __info.json: {e}")

    def clean_previous_builds(self) -> None:
        """Remove previous .aseprite-extension files"""
        try:
            old_extensions = list(self.config.path.glob("*.aseprite-extension"))
            if old_extensions:
                click.echo("🧹 Cleaning previous builds...")
                for ext_file in old_extensions:
                    try:
                        ext_file.unlink()
                        click.echo(f"  🗑️  Removed: {ext_file.name}")
                    except OSError as e:
                        click.echo(f"  ⚠️  Failed to remove {ext_file.name}: {e}")
        except OSError as e:
            click.echo(f"⚠️  Error cleaning builds: {e}")


class ExtensionWatcher(FileSystemEventHandler):
    """File system event handler for live reload mode"""

    def __init__(self, builder: ExtensionPacker, debounce_seconds: float = 1.0):
        super().__init__()
        self.builder = builder
        self.last_build_time = 0.0
        self.debounce_seconds = debounce_seconds

    def on_modified(self, event: FileSystemEvent) -> None:
        try:
            if event.is_directory:
                return

            file_path = Path(event.src_path)
            if not self._should_trigger_rebuild(file_path):
                return

            current_time = time.time()
            if current_time - self.last_build_time < self.debounce_seconds:
                return

            self.last_build_time = current_time
            click.echo(f"\n📝 Detected change: {file_path.name}")
            self.builder.install_to_aseprite()

        except Exception as e:
            click.echo(f"⚠️  Error handling file change: {e}")

    def _should_trigger_rebuild(self, file_path: Path) -> bool:
        """Check if file change should trigger a rebuild"""
        return file_path.suffix == ".lua" or file_path.name in [
            "extension.json",
            "package.json",
        ]


class LiveReloadManager:
    """Manages live reload functionality"""

    def __init__(self, builder: ExtensionPacker, debounce: float = 1.0):
        self.builder = builder
        self.debounce = debounce

    def start(self) -> None:
        """Start live reload mode"""
        click.echo("🔄 Live reload mode started")
        click.echo(f"📁 Extension: {self.builder.config.path}")
        click.echo(f"   Debounce: {self.debounce}s")
        click.echo("   Watching: .lua, extension.json, package.json")
        click.echo("   Press Ctrl+C to exit\n")

        if not self.builder.install_to_aseprite():
            click.echo("❌ Initial installation failed, but continuing to watch...")

        event_handler = ExtensionWatcher(self.builder, self.debounce)
        observer = Observer()

        try:
            if self.builder.config.path.exists():
                observer.schedule(
                    event_handler, str(self.builder.config.path), recursive=True
                )

            observer.start()

            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                click.echo("\n🛑 Stopping live reload...")

        except Exception as e:
            click.echo(f"❌ Error setting up file watching: {e}")
        finally:
            observer.stop()
            observer.join()
            click.echo("✅ Live reload stopped")


@click.group(
    help="Aseprite extension packaging and live reloading tool",
    context_settings={"help_option_names": ["-h", "--help"]},
)
def cli() -> None:
    """Main CLI entry point"""
    pass


@cli.command(help="Pack extension into .aseprite-extension file")
@click.argument(
    "extension_path",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
)
@click.option("--clean", "-c", is_flag=True, help="Clean previous builds first")
@click.option("--install", "-i", is_flag=True, help="Install to Aseprite after build")
@click.option("--output", "-o", help="Custom output name (without extension)")
@click.option(
    "--output-dir",
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    help="Output directory (default: extension directory)",
)
def pack(
    extension_path: Path,
    clean: bool,
    install: bool,
    output: Optional[str],
    output_dir: Optional[Path],
) -> None:
    """Pack extension command"""
    try:
        config = ExtensionConfig.from_path(extension_path)
        packer = ExtensionPacker(config)

        if clean:
            packer.clean_previous_builds()

        packer.create_package(output_dir, output)

        if install:
            if not packer.install_to_aseprite():
                click.echo("❌ Installation failed")
                sys.exit(1)

    except (ValidationError, FileOperationError) as e:
        click.echo(f"❌ {e}")
        sys.exit(1)
    except Exception as e:
        click.echo(f"❌ Unexpected error: {e}")
        sys.exit(1)


@cli.command(help="Watch for changes and auto-reload extension")
@click.argument(
    "extension_path",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
)
@click.option(
    "--debounce",
    "-d",
    type=float,
    default=1.0,
    help="Debounce time in seconds (default: 1.0)",
)
@click.option(
    "--extensions-dir",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    help="Custom Aseprite extensions directory",
)
def live_reload(
    extension_path: Path,
    debounce: float,
    extensions_dir: Optional[Path],
) -> None:
    """Live reload command"""
    try:
        config = ExtensionConfig.from_path(extension_path)
        packer = ExtensionPacker(config, extensions_dir)
        manager = LiveReloadManager(packer, debounce)

        manager.start()

    except (ValidationError, FileOperationError) as e:
        click.echo(f"❌ {e}")
        sys.exit(1)
    except Exception as e:
        click.echo(f"❌ Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    cli()
