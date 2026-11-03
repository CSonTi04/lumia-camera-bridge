"""Install a private, agent-only CLI profile for a local Debian user."""
import argparse
import json
import os
from pathlib import Path
import pwd
import shlex


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--user', required=True)
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise SystemExit('Run with sudo on the Pi.')
    user = pwd.getpwnam(args.user)
    if user.pw_uid == 0:
        raise SystemExit('Choose the ordinary agent user, not root.')
    source = json.loads(Path('/etc/lumia-agent/config.json').read_text())
    agent_token = source['agent_token']
    if not isinstance(agent_token, str) or len(agent_token) < 24:
        raise SystemExit('Invalid bridge agent credential.')
    home = Path(user.pw_dir)
    config_dir = home / '.config' / 'lumia-agent'
    bin_dir = home / '.local' / 'bin'
    for directory in (home / '.config', config_dir, home / '.local', bin_dir):
        if directory.is_symlink():
            raise SystemExit('Refusing a symlink in the client installation path.')
        if not directory.exists():
            directory.mkdir(mode=0o700)
            os.chown(directory, user.pw_uid, user.pw_gid)
    os.chmod(config_dir, 0o700)
    os.chown(config_dir, user.pw_uid, user.pw_gid)
    profile = config_dir / 'agent-config.json'
    wrapper = bin_dir / 'lumia-camera'
    command = '#!/bin/sh\nexec /opt/lumia-agent/.venv/bin/python /opt/lumia-agent/bridge/lumia_cli.py --url http://127.0.0.1:8765 --config ' + shlex.quote(str(profile)) + ' "$@"\n'
    if wrapper.exists() and wrapper.read_text() != command:
        raise SystemExit('Refusing to replace an unrelated lumia-camera command.')
    for target, content, mode in (
        (profile, json.dumps({'agent_token': agent_token}) + '\n', 0o600),
        (wrapper, command, 0o755),
    ):
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, mode)
        with os.fdopen(fd, 'w') as output:
            os.fchmod(output.fileno(), mode)
            os.fchown(output.fileno(), user.pw_uid, user.pw_gid)
            output.write(content)
    print(json.dumps({'command': str(wrapper), 'private_profile': str(profile), 'profile_mode': '0600', 'device_token_copied': False}))


if __name__ == '__main__':
    main()
