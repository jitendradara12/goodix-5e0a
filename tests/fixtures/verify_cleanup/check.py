#!/usr/bin/env python3
"""Offline ticket 91 checks. PATH contains only mocks and allowlisted local tools."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
MOCK = r'''
import json, os, signal, sys
from pathlib import Path
name = Path(sys.argv[0]).name
args = sys.argv[1:]
log = Path(os.environ['EVENTS'])
events = [json.loads(s) for s in log.read_text().splitlines()] if log.exists() else []
with log.open('a') as f:
    f.write(json.dumps([name, *args]) + '\n')
case = os.environ['CASE']
if name == 'sudo':
    if args == ['-v']:
        sys.exit(7 if case == 'auth-fail' else 0)
    assert args[0] == '-n', 'interactive sudo outside setup'
    assert args[1] == 'systemctl', args
    op = args[2]
    if op == 'unset-environment':
        print('mock cleanup diagnostic')
        sys.exit(1 if 'expiry' in case else 0)
    if op == 'restart':
        sys.exit(23 if case == 'restart-fail' else 0)
    assert op == 'set-environment', args
    sys.exit(19 if case == 'set-fail' else 0)
if name == 'systemctl':
    assert args[0] == 'show', args
    if 'ExecStart' in args:
        print('ExecStart=/mock/fprintd' + ('' if case == 'absent' else ' --no-timeout'))
    else:
        print('MainPID=1234\nActiveState=active\nExecMainStartTimestamp=now')
elif name == 'timeout':
    assert args == ['--signal=INT', '--kill-after=5s', '60s', 'fprintd-verify', '-f', 'right-index-finger'], args
    count = sum(e[0] == 'timeout' for e in events)
    print('mock client evidence', flush=True)
    if case.startswith('int') or case == 'term' or case == 'hup':
        sig = signal.SIGINT if case.startswith('int') else (signal.SIGTERM if case == 'term' else signal.SIGHUP)
        os.kill(os.getppid(), sig)
        sys.exit(0)
    if case.startswith('timeout') or (case == 'second-timeout' and count == 1):
        sys.exit(124)
    if case == 'killed': sys.exit(137)
    if case == 'client-error': sys.exit(42)
    if case == 'garbage': sys.exit(0)
    print('Verify result: verify-' + ('no-match' if case == 'no-match' else 'match') + ' (done)')
    sys.exit(1 if case == 'no-match' else 0)
elif name == 'journalctl':
    assert '--since' in args and '--until' in args and '--no-pager' in args, args
    print('mock unfiltered journal evidence')
    if 'journal-fail' in case:
        print('mock permission denied', file=sys.stderr)
        sys.exit(9)
elif name == 'sleep':
    assert args[0] in ('5', '90', '310'), args
elif name == 'fprintd-verify':
    raise AssertionError('timeout must never launch a real client in this fixture')
else:
    raise AssertionError(name)
'''


def main():
    cases = {
        'match': (0, 0), 'no-match': (0, 0), 'garbage': (1, 1),
        'timeout': (124, 124), 'second-timeout': (124, 124),
        'killed': (137, 137), 'client-error': (42, 42),
        'expiry': (0, 1), 'timeout-expiry': (124, 124),
        'journal-fail': (0, 1), 'timeout-journal-fail': (124, 124),
        'timeout-expiry-journal-fail': (124, 124),
        'int': (130, 130), 'int-expiry': (130, 130),
        'term': (143, 143), 'hup': (129, 129),
        'auth-fail': (7, 7), 'restart-fail': (23, 23), 'set-fail': (19, 19),
    }
    runs = 0
    with tempfile.TemporaryDirectory(prefix='verify-cleanup-') as tmp:
        sandbox = Path(tmp)
        bin_dir = sandbox / 'bin'
        bin_dir.mkdir()
        # No inherited PATH fallback: accidental new commands cannot reach hardware.
        for tool in ('bash', 'date', 'dirname', 'mktemp', 'cat', 'grep', 'sed', 'tee'):
            (bin_dir / tool).symlink_to(shutil.which(tool))
        for tool in ('sudo', 'systemctl', 'timeout', 'journalctl', 'sleep', 'fprintd-verify'):
            p = bin_dir / tool
            p.write_text('#!' + sys.executable + '\n' + MOCK)
            p.chmod(0o755)
        for script, gap in (('87', None), ('88', '90'), ('88', '310')):
            scenarios = dict(cases)
            if script == '88': scenarios['absent'] = (1, 1)
            for case, (test_rc, final_rc) in scenarios.items():
                home = sandbox / f'{script}-{gap}-{case}'
                home.mkdir()
                events_path = home / 'events.jsonl'
                env = dict(HOME=str(home), PATH=str(bin_dir), CASE=case,
                           EVENTS=str(events_path), LC_ALL='C')
                cmd = [str(bin_dir / 'bash'), str(ROOT / f'scripts/verify-ticket{script}.sh')]
                if gap: cmd.append(gap)
                # Exercise sourcing from another cwd and by basename in scripts/.
                cwd = home
                if case == 'no-match':
                    cmd[1] = Path(cmd[1]).name
                    cwd = ROOT / 'scripts'
                result = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=15)
                tag = f'ticket{script} gap={gap} {case}'
                assert result.returncode == final_rc, (tag, result.returncode, result.stdout, result.stderr)
                dirs = list(home.glob('goodix-*'))
                assert len(dirs) == 1, (tag, dirs)
                out = dirs[0]
                status = dict(line.split('=', 1) for line in (out / 'status.txt').read_text().splitlines())
                assert status['test_exit'] == str(test_rc), (tag, status)
                assert status['exit'] == str(final_rc), (tag, status)
                assert 'mock unfiltered journal evidence' in (out / 'journal.txt').read_text(), tag
                assert str(out) in result.stdout, tag
                events = [json.loads(line) for line in events_path.read_text().splitlines()]
                sudo = [e[1:] for e in events if e[0] == 'sudo']
                assert all(a == ['-v'] or a[0] == '-n' for a in sudo), (tag, sudo)
                claims = [e for e in events if e[0] == 'timeout']
                cleanup = ['sudo', '-n', 'systemctl', 'unset-environment', 'G_MESSAGES_DEBUG']
                journal = next(e for e in events if e[0] == 'journalctl')
                if case in ('auth-fail', 'absent'):
                    assert cleanup not in events and not claims, (tag, events)
                    assert status['cleanup_attempted'] == '0', tag
                else:
                    assert events.index(journal) < events.index(cleanup), (tag, events)
                    assert status['cleanup_attempted'] == '1', tag
                    assert (out / 'cleanup.txt').read_text() == 'mock cleanup diagnostic\n', tag
                    if 'expiry' in case:
                        assert status['cleanup_exit'] == '1', tag
                        assert 'WARNING: debug environment cleanup failed' in result.stderr, tag
                        assert '\nsudo systemctl unset-environment G_MESSAGES_DEBUG\n' in result.stderr, tag
                        assert 'Debug manager environment unset' not in result.stdout, tag
                    else:
                        assert status['cleanup_exit'] == '0', tag
                        assert 'running daemon not restarted' in result.stdout, tag
                if 'journal-fail' in case:
                    assert status['journal_exit'] == '9', tag
                    assert 'permission denied' in (out / 'journal-error.txt').read_text(), tag
                    assert 'WARNING: journal capture failed' in result.stderr, tag
                    assert 'journalctl -u fprintd --since' in result.stderr, tag
                else:
                    assert status['journal_exit'] == '0', tag
                if claims:
                    restart = ['sudo', '-n', 'systemctl', 'restart', 'fprintd']
                    assert events.index(['sudo', '-v']) < events.index(restart) < events.index(claims[0]), tag
                    assert not any(e[0] == 'sudo' for e in events[events.index(claims[0]):events.index(journal)]), tag
                    # Saved bounds exclude setup and freeze before cleanup authentication.
                    start = journal[journal.index('--since') + 1]
                    end = journal[journal.index('--until') + 1]
                    phases = (out / 'phases.txt').read_text().splitlines()
                    assert start <= phases[0].split(' ', 1)[0] <= end, (tag, start, end, phases)
                    assert len(list(out.glob('*first.txt'))) == 1, tag
                    if case in ('match', 'no-match', 'expiry', 'journal-fail', 'second-timeout'):
                        assert len(claims) == 2, tag
                    else:
                        assert len(claims) == 1, tag
                print('PASS:', tag)
                runs += 1
    print(f'{runs} fully mocked runs passed; no hardware or privilege commands executed.')


if __name__ == '__main__':
    main()
