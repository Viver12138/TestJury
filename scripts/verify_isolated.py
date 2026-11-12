"""Run the full suite in a fresh database, never against the application schema."""
from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import asyncpg

ROOT = Path(__file__).resolve().parents[1]


async def main():
    base = os.environ.get('VERIFY_ADMIN_DATABASE_URL', 'postgresql://testjury:testjury@127.0.0.1:55432/testjury')
    name = 'testjury_verify_' + uuid.uuid4().hex[:12]
    connection = await asyncpg.connect(base)
    await connection.execute(f'CREATE DATABASE "{name}"')
    parts = urlsplit(base)
    dsn = urlunsplit((parts.scheme, parts.netloc, '/' + name, parts.query, parts.fragment))
    env = dict(os.environ, TEST_DATABASE_URL=dsn, PYTHONIOENCODING='utf-8', PYTHONPATH=str(ROOT))
    directory = ROOT / 'evidence/M2/delegated_verification' / name
    directory.mkdir(parents=True, exist_ok=True)
    try:
        process = await asyncio.create_subprocess_exec(
            sys.executable, '-m', 'pytest', *(sys.argv[1:] or ['tests']), '-q',
            '--junitxml=' + str(directory / 'tests.xml'), cwd=ROOT, env=env,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        output, _ = await process.communicate()
        text = output.decode('utf-8', errors='replace').replace('\r\n', '\n').replace('\r', '\n')
        text = '\n'.join(line.rstrip() for line in text.splitlines()).rstrip() + '\n'
        (directory / 'tests.txt').write_text(text, encoding='utf-8', newline='\n')
        print(text, flush=True)
        return process.returncode
    finally:
        await connection.execute(f'DROP DATABASE "{name}" WITH (FORCE)')
        await connection.close()
        (directory / 'isolation.json').write_text(json.dumps({
            'temporary_database': name, 'temporary_database_removed': True,
            'application_database_modified': False}, indent=2) + '\n', encoding='utf-8', newline='\n')


if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
