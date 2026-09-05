# PyInstaller one-folder build (W-003).
#
# One folder, not one file, and deliberately so: a one-folder build can be
# inspected on the operator's laptop when something goes wrong, starts without
# unpacking to a temporary directory first, and keeps the bundled pages visible
# as ordinary files. One-file packaging is deferred until recovery, startup
# time, and asset handling are proven in the field.
#
# Build it through tools/build_package.py rather than calling PyInstaller
# directly; that script cleans stale output and verifies the result.

from pathlib import Path

SPEC_DIRECTORY = Path(SPECPATH).resolve()
ROOT = SPEC_DIRECTORY.parent
SOURCE = ROOT / "src"
VIEWS = SOURCE / "scoreboard" / "views"
STATE = SOURCE / "scoreboard" / "domain" / "state.py"


def read_app_version() -> str:
    """The version the running code reports, read from its single definition.

    Parsed rather than imported: a spec file runs inside PyInstaller's own
    process, and importing the application there would pull its dependencies
    into the build environment for no reason. Repeating the literal here would
    be worse -- a build could then be stamped with a version the application
    does not report (W-006).
    """

    for line in STATE.read_text(encoding="utf-8").splitlines():
        if line.startswith("APP_VERSION"):
            return line.split('"')[1]
    raise SystemExit(f"APP_VERSION not found in {STATE}")


APP_VERSION = read_app_version()
VERSION_TUPLE = tuple(int(part) for part in APP_VERSION.split(".")[:3]) + (0,)

# The Windows file-version resource, so the packaged executable reports the
# same version in its Properties dialog that the diagnostics log records.
VERSION_INFO = SPEC_DIRECTORY / "version_info.txt"
VERSION_INFO.write_text(
    f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={VERSION_TUPLE}, prodvers={VERSION_TUPLE},
    mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable('040904B0', [
        StringStruct('FileDescription', 'High school football LED scoreboard'),
        StringStruct('FileVersion', '{APP_VERSION}'),
        StringStruct('InternalName', 'Scoreboard'),
        StringStruct('OriginalFilename', 'Scoreboard.exe'),
        StringStruct('ProductName', 'Scoreboard'),
        StringStruct('ProductVersion', '{APP_VERSION}')
      ])
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
""",
    encoding="utf-8",
)

# Every page file, carried with the same scoreboard/views shape the source uses
# so host.app._views_directory() finds it in both layouts.
view_files = [
    (str(path), str(Path("scoreboard/views") / path.relative_to(VIEWS).parent))
    for path in VIEWS.rglob("*")
    if path.is_file()
]
if not view_files:
    raise SystemExit(f"no view files found under {VIEWS}")

analysis = Analysis(
    [str(SOURCE / "scoreboard" / "__main__.py")],
    pathex=[str(SOURCE)],
    binaries=[],
    datas=view_files,
    # pywebview chooses its Windows backend at runtime, so the Edge Chromium
    # platform module is never seen by static analysis.
    hiddenimports=[
        "webview.platforms.edgechromium",
        "clr_loader",
        "pythonnet",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Nothing that exists only to build or test the application belongs in the
    # package the operator runs.
    excludes=[
        "PyInstaller",
        "setuptools",
        "pip",
        "tkinter",
        "pydoc_data",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(analysis.pure)

executable = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="Scoreboard",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    # No console. The operator launches this from a shortcut, and every fatal
    # message reaches them through host.preflight.report instead (W-004).
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=str(VERSION_INFO),
)

COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Scoreboard",
)
