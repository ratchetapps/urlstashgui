# PyInstaller Build Config

This file is the build source for `build_pyinstaller.py`.
Edit the YAML block below, then run `build_pyinstaller.bat`.

```yaml
pyinstaller:
  entry_script: main.py
  name: urlstashgui
  mode: windowed
  onefile: true
  clean: true
  noconfirm: true
  contents_directory: .
  dist_path: dist\pyinstaller
  work_path: build\pyinstaller
  spec_path: build\pyinstaller-spec
  icon: img\urlstashgui.ico

  version_file: null
  splash: null

  version_info:
    company_name: ""
    file_description: Add URLs to scenes in Stash
    file_version: 2.0.1.0
    internal_name: urlstashgui
    original_filename: urlstashgui.exe
    product_name: urlstashgui
    product_version: 2.0.1

  hidden_imports: []
  collect_all: []
  collect_submodules: []
  collect_data: []
  collect_binaries: []
  additional_hooks_dir: []
  excludes: []

  add_data: {}
  add_binary: {}
```

## Notes

- `mode`: use `console` to keep the console window, or `windowed` to hide it.
- `onefile: true` builds a single executable. Set it to `false` for a one-folder build.
- `version_info` is used to generate the Windows file-properties metadata shown in Explorer.
- `add_data` and `add_binary` map destination folders inside the built app to source files in the repo.
- This build flow expects `PyInstaller` to be installed in the current Python environment.

## Build

Run:

```bat
build_pyinstaller.bat
```

Optional custom config path:

```bat
build_pyinstaller.bat other-build-config.md
```
