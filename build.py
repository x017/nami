#!/usr/bin/env python3
"""Build nami binary with PyInstaller, bundling VLC libraries."""

import os, shutil, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).parent


def find(pkg, lib):
    """Find a shared library path via pkg-config or `find`."""
    try:
        out = subprocess.run(
            ["pkg-config", "--variable=libdir", pkg],
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode == 0:
            path = Path(out.stdout.strip()) / lib
            if path.exists():
                return str(path)
    except FileNotFoundError:
        pass
    # fallback: search common dirs
    for base in ("/usr/lib/x86_64-linux-gnu", "/usr/lib", "/usr/local/lib"):
        p = Path(base) / lib
        if p.exists():
            return str(p)
    return None


def find_plugins():
    """Find VLC plugins directory."""
    try:
        out = subprocess.run(
            ["pkg-config", "--variable=pluginsdir", "vlc"],
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode == 0:
            path = out.stdout.strip()
            if os.path.isdir(path):
                return path
    except FileNotFoundError:
        pass
    for base in ("/usr/lib/x86_64-linux-gnu/vlc/plugins",
                 "/usr/lib/vlc/plugins",
                 "/usr/local/lib/vlc/plugins"):
        if os.path.isdir(base):
            return base
    return None


def main():
    libvlc = find("vlc", "libvlc.so")
    libvlccore = find("vlc", "libvlccore.so")
    plugins = find_plugins()

    if not libvlc:
        print("ERROR: libvlc.so not found. Install VLC development files.")
        sys.exit(1)
    if not plugins:
        print("ERROR: VLC plugins directory not found.")
        sys.exit(1)

    print(f"libvlc:      {libvlc}")
    print(f"libvlccore:  {libvlccore or '(bundled with libvlc)'}")
    print(f"plugins:     {plugins}")

    cmd = [
        "pyinstaller", "--onefile",
        "--add-binary", f"{libvlc}:.",
    ]
    if libvlccore:
        cmd += ["--add-binary", f"{libvlccore}:."]
    cmd += ["--add-data", f"{plugins}:vlc_plugins"]
    cmd += [
        "--hidden-import", "vlc",
        "--hidden-import", "mutagen",
        "--hidden-import", "PIL",
        "--hidden-import", "PIL._tkinter_finder",
        "--name", "nami",
        str(ROOT / "main.py"),
    ]

    print(f"\nRunning: {' '.join(cmd)}\n")
    subprocess.run(cmd, check=True)
    print(f"\nBinary at: {ROOT / 'dist' / 'nami'}")
    print("Run with:  ./dist/nami")


if __name__ == "__main__":
    main()
