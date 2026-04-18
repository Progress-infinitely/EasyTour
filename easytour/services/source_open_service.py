from __future__ import annotations

import os
import subprocess
import sys
import webbrowser
from pathlib import Path
from urllib.parse import unquote, urlparse


def _launch_local_path(target_path: Path) -> None:
    normalized_path = str(target_path)
    if os.name == 'nt':
        os.startfile(normalized_path)  # type: ignore[attr-defined]
        return
    if sys.platform == 'darwin':
        subprocess.Popen(['open', normalized_path])
        return
    subprocess.Popen(['xdg-open', normalized_path])


def open_source_target(source_target: str) -> dict[str, str]:
    normalized_target = str(source_target or '').strip()
    if not normalized_target:
        raise FileNotFoundError('source target is empty')

    parsed = urlparse(normalized_target)
    if parsed.scheme in {'http', 'https'}:
        webbrowser.open(normalized_target, new=2)
        return {'target_type': 'url'}

    if parsed.scheme == 'file':
        normalized_target = unquote(parsed.path or '')
        if parsed.netloc:
            normalized_target = f'//{parsed.netloc}{normalized_target}'

    local_path = Path(normalized_target).expanduser()
    if not local_path.exists():
        raise FileNotFoundError(f'source file not found: {local_path}')

    _launch_local_path(local_path)
    return {'target_type': 'file'}
