#!/usr/bin/env python3
"""Install codex-accounts into ~/.local/bin without changing your shell settings."""
import os
import argparse
import json
from pathlib import Path
import shutil
import sys
import tempfile

source = Path(__file__).resolve().with_name('codex-accounts')
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--bin-dir', type=Path, default=Path.home() / '.local/bin', help='Installation directory (default: ~/.local/bin)')
args = parser.parse_args()
bin_dir = args.bin_dir.expanduser().resolve()
destination = bin_dir / 'codex-accounts'
if destination.exists() and 'Local ChatGPT account selection for Codex CLI' not in destination.read_text():
    sys.exit('Refusing to overwrite an unrelated file: ' + str(destination))
if not shutil.which('codex'):
    sys.exit('Install Codex CLI first; codex was not found on PATH.')
bin_dir.mkdir(parents=True, exist_ok=True)
fd, temp = tempfile.mkstemp(dir=bin_dir)
os.close(fd)
try:
    shutil.copyfile(source, temp)
    os.chmod(temp, 0o755)
    os.replace(temp, destination)
finally:
    if os.path.exists(temp):
        os.unlink(temp)
marker = destination.with_name('.' + destination.name + '.install.json')
fd, temporary = tempfile.mkstemp(dir=bin_dir)
try:
    with os.fdopen(fd, 'w') as stream:
        json.dump({'repository': 'JoRo-Code/codex-account-switcher'}, stream)
    os.replace(temporary, marker)
finally:
    if os.path.exists(temporary): os.unlink(temporary)
print('Installed:', destination)
print('Future updates: codex-accounts update (automatic checks are also enabled at launch).')
if str(bin_dir) not in os.environ.get('PATH', '').split(os.pathsep):
    print('Add this line to your shell configuration:')
    import shlex
    print('export PATH=' + shlex.quote(str(bin_dir)) + ':"$PATH"')
print('Next: codex-accounts add personal')
