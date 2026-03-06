import ast
import os
import sys
from pathlib import Path


def extract_yaml_block(markdown_text: str) -> str:
    lines = markdown_text.splitlines()
    in_yaml_block = False
    yaml_lines = []

    for line in lines:
        stripped = line.strip()
        if not in_yaml_block and stripped == "```yaml":
            in_yaml_block = True
            continue
        if in_yaml_block and stripped == "```":
            return "\n".join(yaml_lines)
        if in_yaml_block:
            yaml_lines.append(line.rstrip("\n"))

    raise ValueError("No ```yaml fenced block found in the config file.")


def parse_scalar(value: str):
    value = value.strip()
    if value == "":
        return ""
    if value in ("true", "false"):
        return value == "true"
    if value in ("null", "none"):
        return None
    if value == "[]":
        return []
    if value == "{}":
        return {}
    if (value.startswith("'") and value.endswith("'")) or (
        value.startswith('"') and value.endswith('"')
    ):
        return ast.literal_eval(value)
    try:
        return int(value)
    except ValueError:
        return value


def preprocess_yaml_lines(yaml_text: str):
    processed = []
    for raw_line in yaml_text.splitlines():
        if not raw_line.strip():
            continue
        if raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        processed.append((indent, raw_line.strip()))
    return processed


def parse_yaml_block(yaml_text: str):
    lines = preprocess_yaml_lines(yaml_text)

    def parse_block(index: int, indent: int):
        container = None

        while index < len(lines):
            current_indent, text = lines[index]
            if current_indent < indent:
                break
            if current_indent > indent:
                raise ValueError(f"Unexpected indentation near: {text}")

            if text.startswith("- "):
                if container is None:
                    container = []
                elif not isinstance(container, list):
                    raise ValueError(f"Mixed YAML container types near: {text}")
                container.append(parse_scalar(text[2:].strip()))
                index += 1
                continue

            key, separator, raw_value = text.partition(":")
            if separator != ":":
                raise ValueError(f"Invalid YAML line: {text}")

            if container is None:
                container = {}
            elif not isinstance(container, dict):
                raise ValueError(f"Mixed YAML container types near: {text}")

            key = key.strip()
            raw_value = raw_value.strip()
            index += 1

            if raw_value == "":
                value, index = parse_block(index, indent + 2)
            else:
                value = parse_scalar(raw_value)

            container[key] = value

        if container is None:
            container = {}
        return container, index

    parsed, next_index = parse_block(0, 0)
    if next_index != len(lines):
        raise ValueError("YAML parsing did not consume the full block.")
    return parsed


def load_build_config(config_path: Path):
    markdown_text = config_path.read_text(encoding="utf-8")
    yaml_text = extract_yaml_block(markdown_text)
    config = parse_yaml_block(yaml_text)
    if "pyinstaller" not in config or not isinstance(config["pyinstaller"], dict):
        raise ValueError("The YAML block must contain a top-level 'pyinstaller' mapping.")
    return config["pyinstaller"]


def normalize_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def parse_version_tuple(value):
    if value is None:
        return (0, 0, 0, 0)

    text = str(value).strip()
    if not text:
        return (0, 0, 0, 0)

    parts = [part.strip() for part in text.split(".") if part.strip()]
    numbers = []
    for part in parts[:4]:
        try:
            numbers.append(int(part))
        except ValueError as exc:
            raise ValueError(f"Invalid numeric version segment: {part!r}") from exc

    while len(numbers) < 4:
        numbers.append(0)

    return tuple(numbers[:4])


def format_version_string(version_tuple):
    return ".".join(str(part) for part in version_tuple)


def build_version_file_text(version_info_config: dict):
    file_version_tuple = parse_version_tuple(version_info_config.get("file_version"))
    product_version_tuple = parse_version_tuple(version_info_config.get("product_version"))

    string_values = {
        "CompanyName": str(version_info_config.get("company_name", "")),
        "FileDescription": str(version_info_config.get("file_description", "")),
        "FileVersion": format_version_string(file_version_tuple),
        "InternalName": str(version_info_config.get("internal_name", "")),
        "OriginalFilename": str(version_info_config.get("original_filename", "")),
        "ProductName": str(version_info_config.get("product_name", "")),
        "ProductVersion": str(version_info_config.get("product_version", "")),
    }

    return "\n".join(
        [
            "# UTF-8",
            "#",
            "# Auto-generated by build_pyinstaller.py",
            "VSVersionInfo(",
            "  ffi=FixedFileInfo(",
            f"    filevers={file_version_tuple},",
            f"    prodvers={product_version_tuple},",
            "    mask=0x3f,",
            "    flags=0x0,",
            "    OS=0x40004,",
            "    fileType=0x1,",
            "    subtype=0x0,",
            "    date=(0, 0)",
            "    ),",
            "  kids=[",
            "    StringFileInfo(",
            "      [",
            "      StringTable(",
            "        '040904B0',",
            "        ["
            + ",\n        ".join(
                f"StringStruct({key!r}, {value!r})"
                for key, value in string_values.items()
            )
            + "])",
            "      ]), ",
            "    VarFileInfo([VarStruct('Translation', [1033, 1200])])",
            "  ]",
            ")",
        ]
    )


def resolve_version_file(project_root: Path, config: dict):
    version_file = config.get("version_file")
    if version_file:
        version_path = project_root / str(version_file)
        if not version_path.exists():
            raise FileNotFoundError(f"Version file not found: {version_path}")
        return version_path

    version_info_config = config.get("version_info")
    if not isinstance(version_info_config, dict) or not version_info_config:
        return None

    generated_dir = project_root / str(config.get("work_path", r"build\pyinstaller"))
    generated_dir.mkdir(parents=True, exist_ok=True)
    version_path = generated_dir / "generated_version_info.txt"
    version_path.write_text(build_version_file_text(version_info_config), encoding="utf-8")
    return version_path


def build_mapping_args(project_root: Path, mapping: dict, switch_name: str):
    args = []
    for dest, files in mapping.items():
        for rel_path in normalize_list(files):
            source_path = project_root / str(rel_path)
            if not source_path.exists():
                raise FileNotFoundError(f"Missing file for {switch_name}: {source_path}")
            args.extend([switch_name, f"{source_path}{os.pathsep}{dest}"])
    return args


def build_runtime_icon_args(project_root: Path, config: dict):
    icon = config.get("icon")
    if not icon:
        return []

    icon_path = project_root / str(icon)
    if not icon_path.exists():
        raise FileNotFoundError(f"Icon file not found: {icon_path}")

    return ["--add-data", f"{icon_path}{os.pathsep}img"]


def build_pyinstaller_args(project_root: Path, config: dict):
    entry_script = project_root / str(config["entry_script"])
    if not entry_script.exists():
        raise FileNotFoundError(f"Entry script not found: {entry_script}")

    args = [str(entry_script)]
    args.extend(["--name", str(config.get("name", entry_script.stem))])
    args.extend(["--distpath", str(project_root / str(config.get("dist_path", r"dist\pyinstaller")))])
    args.extend(["--workpath", str(project_root / str(config.get("work_path", r"build\pyinstaller")))])
    args.extend(["--specpath", str(project_root / str(config.get("spec_path", r"build\pyinstaller-spec")))])
    args.extend(["--contents-directory", str(config.get("contents_directory", "."))])

    if bool(config.get("noconfirm", True)):
        args.append("--noconfirm")
    if bool(config.get("clean", True)):
        args.append("--clean")
    if bool(config.get("onefile", True)):
        args.append("--onefile")
    else:
        args.append("--onedir")

    mode = str(config.get("mode", "console")).lower()
    if mode == "windowed":
        args.append("--windowed")
    elif mode == "console":
        args.append("--console")
    else:
        raise ValueError("mode must be either 'console' or 'windowed'.")

    icon = config.get("icon")
    if icon:
        icon_path = project_root / str(icon)
        if not icon_path.exists():
            raise FileNotFoundError(f"Icon file not found: {icon_path}")
        args.extend(["--icon", str(icon_path)])

    version_path = resolve_version_file(project_root, config)
    if version_path is not None:
        args.extend(["--version-file", str(version_path)])

    splash = config.get("splash")
    if splash:
        splash_path = project_root / str(splash)
        if not splash_path.exists():
            raise FileNotFoundError(f"Splash image not found: {splash_path}")
        args.extend(["--splash", str(splash_path)])

    for item in normalize_list(config.get("hidden_imports", [])):
        args.extend(["--hidden-import", str(item)])
    for item in normalize_list(config.get("collect_all", [])):
        args.extend(["--collect-all", str(item)])
    for item in normalize_list(config.get("collect_submodules", [])):
        args.extend(["--collect-submodules", str(item)])
    for item in normalize_list(config.get("collect_data", [])):
        args.extend(["--collect-data", str(item)])
    for item in normalize_list(config.get("collect_binaries", [])):
        args.extend(["--collect-binaries", str(item)])
    for item in normalize_list(config.get("additional_hooks_dir", [])):
        hook_dir = project_root / str(item)
        args.extend(["--additional-hooks-dir", str(hook_dir)])
    for item in normalize_list(config.get("excludes", [])):
        args.extend(["--exclude-module", str(item)])

    args.extend(build_mapping_args(project_root, config.get("add_data", {}), "--add-data"))
    args.extend(build_mapping_args(project_root, config.get("add_binary", {}), "--add-binary"))
    args.extend(build_runtime_icon_args(project_root, config))

    return args


def main():
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent
    config_path = (
        Path(sys.argv[1]).resolve()
        if len(sys.argv) > 1
        else script_dir / "makefile.md"
    )

    config = load_build_config(config_path)

    try:
        import PyInstaller.__main__
    except ImportError as exc:
        raise SystemExit(
            "PyInstaller is not installed in this Python environment. "
            "Install it first, then rerun build_pyinstaller.bat."
        ) from exc

    args = build_pyinstaller_args(project_root, config)
    name = str(config.get("name", "application"))

    print(f"Using config: {config_path}")
    print(f"Building {name} with PyInstaller...")
    PyInstaller.__main__.run(args)
    print("PyInstaller build complete.")


if __name__ == "__main__":
    main()
