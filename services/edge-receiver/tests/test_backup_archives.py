"""Reject path escapes before an external physical backup is extracted."""
from io import BytesIO
import tarfile
import pytest

from edge_receiver import backup_preflight


@pytest.mark.parametrize('name,kind',[('/outside','file'),('../outside','file'),('base/../../outside','file'),
    ('safe-link','symlink'),('hard-link','hardlink'),('device','device')])
def test_backup_archive_rejects_escape_links_and_devices(tmp_path,name,kind):
    path=tmp_path/'base.tar'
    with tarfile.open(path,'w') as archive:
        member=tarfile.TarInfo(name);member.size=1
        if kind=='symlink':member.type=tarfile.SYMTYPE;member.linkname='/outside';member.size=0
        elif kind=='hardlink':member.type=tarfile.LNKTYPE;member.linkname='../outside';member.size=0
        elif kind=='device':member.type=tarfile.CHRTYPE;member.size=0
        archive.addfile(member,BytesIO(b'x') if member.size else None)
    with pytest.raises(ValueError):backup_preflight.inspect_archive(path)
    assert not (tmp_path/'outside').exists(), 'archive validation extracted unsafe content'


def test_backup_archive_validates_regular_files_without_extracting(tmp_path):
    path=tmp_path/'base.tar'
    with tarfile.open(path,'w') as archive:
        member=tarfile.TarInfo('base/1/1259');member.size=3;archive.addfile(member,BytesIO(b'abc'))
    result=backup_preflight.inspect_archive(path)
    assert result['members']==1 and not (tmp_path/'base').exists(), 'archive inspector extracted content'


def test_small_pax_sparse_archive_cannot_claim_terabytes_of_expanded_data(tmp_path):
    path=tmp_path/'sparse.tar'
    with tarfile.open(path,'w',format=tarfile.PAX_FORMAT) as archive:
        member=tarfile.TarInfo('sparse-data');member.size=1
        member.pax_headers={'GNU.sparse.size':str(1<<40),'GNU.sparse.map':'0,1'}
        archive.addfile(member,BytesIO(b'x'))
    assert path.stat().st_size<16384, 'sparse regression fixture is unexpectedly large'
    with pytest.raises(ValueError):backup_preflight.inspect_archive(path)


def test_gnu_sparse_type_is_not_accepted_as_an_ordinary_file(tmp_path):
    path=tmp_path/'gnu-sparse.tar'
    with path.open('wb') as stream:
        member=tarfile.TarInfo('sparse-data');member.type=tarfile.GNUTYPE_SPARSE;member.size=0
        stream.write(member.tobuf(format=tarfile.GNU_FORMAT));stream.write(b'\0'*1024)
    with pytest.raises(ValueError):backup_preflight.inspect_archive(path)


def test_tar_member_claim_cannot_seek_beyond_physical_archive(tmp_path):
    path=tmp_path/'truncated.tar'
    with path.open('wb') as stream:
        member=tarfile.TarInfo('too-large');member.size=1<<40;stream.write(member.tobuf());stream.write(b'\0'*1024)
    with pytest.raises(ValueError):backup_preflight.inspect_archive(path)
