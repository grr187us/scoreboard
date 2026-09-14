"""Capture a native window (or the whole screen) to PNG with ctypes only.

Development evidence helper for the real-runtime harnesses under
``.scratch/post-live-fixes``. No Pillow in the venv, so the PNG is encoded by
hand (zlib + struct). Windows only.
"""
from __future__ import annotations

import ctypes
import struct
import zlib
from ctypes import wintypes
from pathlib import Path

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

SRCCOPY = 0x00CC0020
CAPTUREBLT = 0x40000000
DIB_RGB_COLORS = 0
BI_RGB = 0
PW_RENDERFULLCONTENT = 0x00000002


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


def _png(width: int, height: int, bgra: bytes) -> bytes:
    raw = bytearray()
    stride = width * 4
    for y in range(height):
        row = bgra[y * stride:(y + 1) * stride]
        raw.append(0)
        # BGRA -> RGB
        raw.extend(bytes(b for px in (row[i:i + 4] for i in range(0, stride, 4)) for b in (px[2], px[1], px[0])))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(raw), 6))
            + chunk(b"IEND", b""))


def capture_rect(left: int, top: int, width: int, height: int, path: Path) -> Path:
    """Copy a screen rectangle (virtual-desktop pixels) to ``path`` as PNG."""

    user32.SetProcessDPIAware()
    screen = user32.GetDC(0)
    memory = gdi32.CreateCompatibleDC(screen)
    bitmap = gdi32.CreateCompatibleBitmap(screen, width, height)
    gdi32.SelectObject(memory, bitmap)
    gdi32.BitBlt(memory, 0, 0, width, height, screen, left, top, SRCCOPY | CAPTUREBLT)
    info = BITMAPINFO()
    info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    info.bmiHeader.biWidth = width
    info.bmiHeader.biHeight = -height
    info.bmiHeader.biPlanes = 1
    info.bmiHeader.biBitCount = 32
    info.bmiHeader.biCompression = BI_RGB
    buffer = ctypes.create_string_buffer(width * height * 4)
    gdi32.GetDIBits(memory, bitmap, 0, height, buffer, ctypes.byref(info), DIB_RGB_COLORS)
    gdi32.DeleteObject(bitmap)
    gdi32.DeleteDC(memory)
    user32.ReleaseDC(0, screen)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_png(width, height, buffer.raw))
    return path


def capture_hwnd(hwnd: int, path: Path) -> Path:
    """Capture a top-level window by its on-screen rectangle (brings it to front first)."""

    user32.SetProcessDPIAware()
    try:
        user32.SetForegroundWindow(hwnd)
    except Exception:  # noqa: BLE001
        pass
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return capture_rect(rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top, path)


def window_hwnd(window) -> int:
    """pywebview (WebView2 backend) window -> Win32 handle."""

    return int(window.native.Handle.ToInt32())
