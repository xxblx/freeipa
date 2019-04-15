from __future__ import absolute_import

import os

import pytest

from ipapython.certdb import NSSDatabase, TRUSTED_PEER_TRUST_FLAGS
from ipaplatform.osinfo import osinfo

CERTNICK = 'testcert'

if osinfo.id == 'fedora':
    if osinfo.version_number >= (28,):
        NSS_DEFAULT = 'sql'
    else:
        NSS_DEFAULT = 'dbm'
else:
    NSS_DEFAULT = None


def create_selfsigned(nssdb):
    # create self-signed cert + key
    noisefile = os.path.join(nssdb.secdir, 'noise')
    with open(noisefile, 'wb') as f:
        f.write(os.urandom(64))
    try:
        nssdb.run_certutil([
            '-S', '-x',
            '-z', noisefile,
            '-k', 'rsa', '-g', '2048', '-Z', 'SHA256',
            '-t', 'CTu,Cu,Cu',
            '-s', 'CN=testcert',
            '-n', CERTNICK,
            '-m', '365',
        ])
    finally:
        os.unlink(noisefile)


def test_dbm_tmp():
    with NSSDatabase(dbtype='dbm') as nssdb:
        assert nssdb.dbtype == 'dbm'

        for filename in nssdb.filenames:
            assert not os.path.isfile(filename)
        assert not nssdb.exists()

        nssdb.create_db()
        for filename in nssdb.filenames:
            assert os.path.isfile(filename)
            assert os.path.dirname(filename) == nssdb.secdir
        assert nssdb.exists()

        assert os.path.basename(nssdb.certdb) == 'cert8.db'
        assert nssdb.certdb in nssdb.filenames
        assert os.path.basename(nssdb.keydb) == 'key3.db'
        assert os.path.basename(nssdb.secmod) == 'secmod.db'


def test_sql_tmp():
    with NSSDatabase(dbtype='sql') as nssdb:
        assert nssdb.dbtype == 'sql'

        for filename in nssdb.filenames:
            assert not os.path.isfile(filename)
        assert not nssdb.exists()

        nssdb.create_db()
        for filename in nssdb.filenames:
            assert os.path.isfile(filename)
            assert os.path.dirname(filename) == nssdb.secdir
        assert nssdb.exists()

        assert os.path.basename(nssdb.certdb) == 'cert9.db'
        assert nssdb.certdb in nssdb.filenames
        assert os.path.basename(nssdb.keydb) == 'key4.db'
        assert os.path.basename(nssdb.secmod) == 'pkcs11.txt'


def test_convert_db():
    with NSSDatabase(dbtype='dbm') as nssdb:
        assert nssdb.dbtype == 'dbm'

        nssdb.create_db()
        assert nssdb.exists()

        create_selfsigned(nssdb)

        oldcerts = nssdb.list_certs()
        assert len(oldcerts) == 1
        oldkeys = nssdb.list_keys()
        assert len(oldkeys) == 1

        nssdb.convert_db()
        assert nssdb.exists()

        assert nssdb.dbtype == 'sql'
        newcerts = nssdb.list_certs()
        assert len(newcerts) == 1
        assert newcerts == oldcerts
        newkeys = nssdb.list_keys()
        assert len(newkeys) == 1
        assert newkeys == oldkeys

        for filename in nssdb.filenames:
            assert os.path.isfile(filename)
            assert os.path.dirname(filename) == nssdb.secdir

        assert os.path.basename(nssdb.certdb) == 'cert9.db'
        assert nssdb.certdb in nssdb.filenames
        assert os.path.basename(nssdb.keydb) == 'key4.db'
        assert os.path.basename(nssdb.secmod) == 'pkcs11.txt'


def test_convert_db_nokey():
    with NSSDatabase(dbtype='dbm') as nssdb:
        assert nssdb.dbtype == 'dbm'
        nssdb.create_db()

        create_selfsigned(nssdb)

        assert len(nssdb.list_certs()) == 1
        assert len(nssdb.list_keys()) == 1
        # remove key, readd cert
        cert = nssdb.get_cert(CERTNICK)
        nssdb.run_certutil(['-F', '-n', CERTNICK])
        nssdb.add_cert(cert, CERTNICK, TRUSTED_PEER_TRUST_FLAGS)
        assert len(nssdb.list_keys()) == 0
        oldcerts = nssdb.list_certs()
        assert len(oldcerts) == 1

        nssdb.convert_db()
        assert nssdb.dbtype == 'sql'
        newcerts = nssdb.list_certs()
        assert len(newcerts) == 1
        assert newcerts == oldcerts
        assert nssdb.get_cert(CERTNICK) == cert
        newkeys = nssdb.list_keys()
        assert newkeys == ()

        for filename in nssdb.filenames:
            assert os.path.isfile(filename)
            assert os.path.dirname(filename) == nssdb.secdir

        old = os.path.join(nssdb.secdir, 'cert8.db')
        assert not os.path.isfile(old)
        assert os.path.isfile(old + '.migrated')

        assert os.path.basename(nssdb.certdb) == 'cert9.db'
        assert nssdb.certdb in nssdb.filenames
        assert os.path.basename(nssdb.keydb) == 'key4.db'
        assert os.path.basename(nssdb.secmod) == 'pkcs11.txt'


def test_auto_db():
    with NSSDatabase() as nssdb:
        assert nssdb.dbtype == 'auto'
        assert nssdb.filenames is None
        assert not nssdb.exists()
        with pytest.raises(RuntimeError):
            nssdb.list_certs()

        nssdb.create_db()
        assert nssdb.dbtype in ('dbm', 'sql')
        if NSS_DEFAULT is not None:
            assert nssdb.dbtype == NSS_DEFAULT
        assert nssdb.filenames is not None
        assert nssdb.exists()
        nssdb.list_certs()


def test_cert_key_delete():
    with NSSDatabase() as nssdb:
        nssdb.create_db()

        create_selfsigned(nssdb)
        assert len(nssdb.list_certs()) == 1
        assert len(nssdb.list_keys()) == 1

        nssdb.delete_cert(CERTNICK)
        assert len(nssdb.list_certs()) == 0
        assert len(nssdb.list_keys()) == 0


def test_cert_detele():
    with NSSDatabase() as nssdb:
        nssdb.create_db()

        create_selfsigned(nssdb)
        assert len(nssdb.list_certs()) == 1
        assert len(nssdb.list_keys()) == 1

        # save cert, remove cert and key
        cert = nssdb.get_cert(CERTNICK)
        nssdb.delete_cert(CERTNICK)
        assert len(nssdb.list_certs()) == 0
        assert len(nssdb.list_keys()) == 0

        # re-add cert without key
        nssdb.add_cert(cert, CERTNICK, TRUSTED_PEER_TRUST_FLAGS)
        assert len(nssdb.list_certs()) == 1
        assert len(nssdb.list_keys()) == 0

        # remove cert
        nssdb.delete_cert(CERTNICK, delete_key=False)
        assert len(nssdb.list_certs()) == 0
        assert len(nssdb.list_keys()) == 0
