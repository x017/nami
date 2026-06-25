#!/usr/bin/env python3
from setuptools import setup

setup(
    name="nami",
    version="0.1.0",
    description="MPD-like music player daemon + TUI client",
    author="x017",
    url="https://github.com/x017/nami",
    packages=["backend", "backend.database"],
    install_requires=[
        "mutagen",
        "urwid>=3.0",
        "tqdm",
        "Pillow",
        "tinydb",
        "python-vlc",
        "dasbus",
        "PyGObject",
    ],
    extras_require={
        "build": ["pyinstaller"],
    },
    entry_points={
        "console_scripts": [
            "nami=main:main",
            "nami-cli=client.client:main",
        ],
    },
    python_requires=">=3.12",
)
