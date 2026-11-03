"""Extract Microsoft's MSI/CAB payloads without running an installer (Windows)."""
import argparse
import ctypes
from ctypes import wintypes
from pathlib import Path
import shutil
import subprocess


def rows(path, sql, columns):
    msi = ctypes.WinDLL('msi')
    msi.MsiOpenDatabaseW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.POINTER(wintypes.UINT)]
    msi.MsiDatabaseOpenViewW.argtypes = [wintypes.UINT, wintypes.LPCWSTR, ctypes.POINTER(wintypes.UINT)]
    msi.MsiRecordGetStringW.argtypes = [wintypes.UINT, wintypes.UINT, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    db, view, record = wintypes.UINT(), wintypes.UINT(), wintypes.UINT()
    def check(code):
        if code:
            raise OSError('MSI API error: %s' % code)
    check(msi.MsiOpenDatabaseW(str(path), None, ctypes.byref(db)))
    try:
        check(msi.MsiDatabaseOpenViewW(db, sql, ctypes.byref(view)))
        check(msi.MsiViewExecute(view, 0))
        while True:
            code = msi.MsiViewFetch(view, ctypes.byref(record))
            if code == 259:
                break
            check(code)
            values = []
            try:
                for col in range(1, columns + 1):
                    buf, size = ctypes.create_unicode_buffer(8192), wintypes.DWORD(8192)
                    check(msi.MsiRecordGetStringW(record, col, buf, ctypes.byref(size)))
                    values.append(buf.value)
                yield values
            finally:
                msi.MsiCloseHandle(record)
    finally:
        if view.value:
            msi.MsiCloseHandle(view)
        msi.MsiCloseHandle(db)


def extract(payloads, destination, sevenzip):
    destination.mkdir(parents=True, exist_ok=True)
    for package in sorted(payloads.rglob('*.msi')):
        directories = {key: (parent, name) for key, parent, name in rows(package, 'SELECT `Directory`, `Directory_Parent`, `DefaultDir` FROM `Directory`', 3)}
        components = dict(rows(package, 'SELECT `Component`, `Directory_` FROM `Component`', 2))
        def relative(key):
            parent, name = directories[key]
            name = name.split(':')[0].split('|')[-1]
            base = relative(parent) if parent else Path()
            return base / name if name not in ('.', 'SourceDir', '') else base
        raw = destination / '_cab' / package.parent.name
        raw.mkdir(parents=True, exist_ok=True)
        for cabinet in package.parent.glob('*.cab'):
            subprocess.run([sevenzip, 'x', str(cabinet), '-o' + str(raw), '-y'], check=True, stdout=subprocess.DEVNULL)
        count = 0
        for key, component, filename in rows(package, 'SELECT `File`, `Component_`, `FileName` FROM `File`', 3):
            source = raw / key
            if source.exists():
                target = destination / relative(components[component]) / filename.split('|')[-1]
                if not target.resolve().is_relative_to(destination.resolve()):
                    raise ValueError('Unsafe MSI path')
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
                count += 1
        print(package.name, count, 'files extracted')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('payloads', type=Path)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--sevenzip', default=r'C:\Program Files\7-Zip\7z.exe')
    args = parser.parse_args()
    extract(args.payloads, args.destination, args.sevenzip)
