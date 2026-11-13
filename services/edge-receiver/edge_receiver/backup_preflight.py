"""Operator gate: verify expected external cluster identity before recovery."""
import argparse
import json
import os
from pathlib import Path,PurePosixPath
import re
import stat
import subprocess
import tarfile


def inspect_archive(path,*,max_bytes=8*1024**3,max_members=100000):
    """Validate layout only; cluster and checksum checks follow extraction."""
    if type(max_bytes) is not int or max_bytes<=0 or type(max_members) is not int or max_members<=0:
        raise ValueError('positive archive bounds required')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    count=0;expanded=0
    try:
        with os.fdopen(fd,'rb') as stream:
            metadata=os.fstat(stream.fileno())
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_size>max_bytes:raise ValueError('bounded regular archive required')
            # Parse only fixed 512-byte headers. Reject extension/sparse types
            # before tarfile can allocate their attacker-declared PAX payload.
            while True:
                header=stream.read(512)
                if len(header)!=512:raise ValueError('truncated backup archive')
                if header==b'\0'*512:
                    if stream.read(512)!=b'\0'*512:raise ValueError('invalid archive terminator')
                    break
                member=tarfile.TarInfo.frombuf(header,'utf-8','surrogateescape')
                count+=1;name=PurePosixPath(member.name);expanded+=member.size
                if (count>max_members or name.is_absolute() or '..' in name.parts or '\\' in member.name
                        or member.type not in (tarfile.REGTYPE,tarfile.AREGTYPE,tarfile.DIRTYPE)
                        or member.size<0 or member.size>max_bytes or expanded>max_bytes
                        or (member.isdir() and member.size!=0)):
                    raise ValueError('unsafe or oversized backup archive entry')
                end=stream.tell()+((member.size+511)//512)*512
                if end>metadata.st_size:raise ValueError('archive member exceeds physical input')
                stream.seek(end)
    except tarfile.TarError as exc:raise ValueError('invalid backup archive') from exc
    return dict(members=count,expanded_bytes=expanded,layout_verified=True)


def verify_backup(directory,expected_system_id,*,runner=subprocess.run):
    if (not isinstance(expected_system_id,str) or not re.fullmatch('[1-9][0-9]{0,19}',expected_system_id)
            or int(expected_system_id)>2**64-1):
        raise ValueError('external expected cluster identity required')
    path=Path(directory)
    if not path.is_dir() or path.is_symlink():raise ValueError('extracted backup directory required')
    environment=dict(os.environ,LC_ALL='C')
    control=runner(['pg_controldata',str(path)],text=True,capture_output=True,timeout=30,env=environment)
    matches=re.findall(r'^Database system identifier:\s*([0-9]+)\s*$',control.stdout,re.MULTILINE)
    if control.returncode or control.stderr.strip() or matches!=[expected_system_id]:
        raise ValueError('backup cluster identity mismatch or invalid control file')
    checked=runner(['pg_verifybackup',str(path)],text=True,capture_output=True,timeout=60,env=environment)
    if checked.returncode:raise ValueError('backup verification failed')
    return dict(system_identifier=expected_system_id,verified=True)


def recovery_settings(timeline,target_name):
    """Pin an externally approved branch; never infer it from archive contents."""
    if (not isinstance(timeline,str) or not re.fullmatch('[1-9][0-9]{0,9}',timeline)
            or int(timeline)>2**32-1):
        raise ValueError('explicit positive decimal recovery timeline required')
    if not isinstance(target_name,str) or not re.fullmatch('[A-Za-z0-9_][A-Za-z0-9_.-]{0,62}',target_name):
        raise ValueError('bounded recovery target name required')
    return dict(recovery_target_timeline=timeline,recovery_target_name=target_name,recovery_target_action='promote')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    target=parser.add_mutually_exclusive_group(required=True)
    target.add_argument('--directory',type=Path)
    target.add_argument('--check-archive',type=Path)
    parser.add_argument('--expected-system-id')
    parser.add_argument('--expected-timeline')
    parser.add_argument('--target-name')
    parser.add_argument('--max-archive-bytes',type=int,default=8*1024**3)
    parser.add_argument('--max-archive-members',type=int,default=100000)
    args=parser.parse_args()
    try:
        if args.check_archive:
            result=inspect_archive(args.check_archive,max_bytes=args.max_archive_bytes,max_members=args.max_archive_members)
        else:
            settings=recovery_settings(args.expected_timeline,args.target_name)
            result=verify_backup(args.directory,args.expected_system_id)
            result['recovery_settings']=settings
        print(json.dumps(result))
    except (OSError,ValueError,subprocess.TimeoutExpired) as exc:
        print(json.dumps(dict(verified=False,error_kind=type(exc).__name__)))
        raise SystemExit(1) from None


if __name__=='__main__':main()
