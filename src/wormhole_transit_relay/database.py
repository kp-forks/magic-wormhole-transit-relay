import os
import sqlite3
import tempfile
from pkg_resources import resource_string
from twisted.python import log

class DBError(Exception):
    pass

def get_schema(version):
    schema_bytes = resource_string("wormhole_transit_relay",
                                   "db-schemas/v%d.sql" % version)
    return schema_bytes.decode("utf-8")

## def get_upgrader(new_version):
##     schema_bytes = resource_string("wormhole_transit_relay",
##                                    "db-schemas/upgrade-to-v%d.sql" % new_version)
##     return schema_bytes.decode("utf-8")

TARGET_VERSION = 1

def dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d

def _initialize_db_schema(db, target_version):
    """Creates the application schema in the given database.
    """
    log.msg(f"populating new database with schema v{target_version}")
    schema = get_schema(target_version)
    db.executescript(schema)
    db.execute("INSERT INTO version (version) VALUES (?)",
               (target_version,))
    db.commit()

def _initialize_db_connection(db):
    """Sets up the db connection object with a row factory and with necessary
    foreign key settings.
    """
    db.row_factory = dict_factory
    db.execute("PRAGMA foreign_keys = ON")
    problems = db.execute("PRAGMA foreign_key_check").fetchall()
    if problems:
        raise DBError(f"failed foreign key check: {problems}")

def _open_db_connection(dbfile):
    """Open a new connection to the SQLite3 database at the given path.
    """
    try:
        db = sqlite3.connect(dbfile)
        _initialize_db_connection(db)
    except (OSError, sqlite3.OperationalError, sqlite3.DatabaseError) as e:
        # this indicates that the file is not a compatible database format.
        # Perhaps it was created with an old version, or it might be junk.
        raise DBError(f"Unable to create/open db file {dbfile}: {e}")
    return db

def _get_temporary_dbfile(dbfile):
    """Get a temporary filename near the given path.
    """
    fd, name = tempfile.mkstemp(
        prefix=os.path.basename(dbfile) + ".",
        dir=os.path.dirname(dbfile)
    )
    os.close(fd)
    return name

def _atomic_create_and_initialize_db(dbfile, target_version):
    """Create and return a new database, initialized with the application
    schema.

    If anything goes wrong, nothing is left at the ``dbfile`` path.
    """
    temp_dbfile = _get_temporary_dbfile(dbfile)
    db = _open_db_connection(temp_dbfile)
    _initialize_db_schema(db, target_version)
    db.close()
    os.rename(temp_dbfile, dbfile)
    return _open_db_connection(dbfile)

def get_db(dbfile, target_version=TARGET_VERSION):
    """Open or create the given db file. The parent directory must exist.
    Returns the db connection object, or raises DBError.
    """
    if dbfile == ":memory:":
        db = _open_db_connection(dbfile)
        _initialize_db_schema(db, target_version)
    elif os.path.exists(dbfile):
        db = _open_db_connection(dbfile)
    else:
        db = _atomic_create_and_initialize_db(dbfile, target_version)

    version = db.execute("SELECT version FROM version").fetchone()["version"]

    ## while version < target_version:
    ##     log.msg(" need to upgrade from %s to %s" % (version, target_version))
    ##     try:
    ##         upgrader = get_upgrader(version+1)
    ##     except ValueError: # ResourceError??
    ##         log.msg(" unable to upgrade %s to %s" % (version, version+1))
    ##         raise DBError("Unable to upgrade %s to version %s, left at %s"
    ##                       % (dbfile, version+1, version))
    ##     log.msg(" executing upgrader v%s->v%s" % (version, version+1))
    ##     db.executescript(upgrader)
    ##     db.commit()
    ##     version = version+1

    if version != target_version:
        raise DBError(f"Unable to handle db version {version}")

    return db

class DBDoesntExist(Exception):
    pass

def open_existing_db(dbfile):
    assert dbfile != ":memory:"
    if not os.path.exists(dbfile):
        raise DBDoesntExist()
    return _open_db_connection(dbfile)

class DBAlreadyExists(Exception):
    pass

def create_db(dbfile):
    """Create the given db file. Refuse to touch a pre-existing file.

    This is meant for use by migration tools, to create the output target"""

    if dbfile == ":memory:":
        db = _open_db_connection(dbfile)
        _initialize_db_schema(db, TARGET_VERSION)
    elif os.path.exists(dbfile):
        raise DBAlreadyExists()
    else:
        db = _atomic_create_and_initialize_db(dbfile, TARGET_VERSION)
    return db

def dump_db(db):
    # to let _iterdump work, we need to restore the original row factory
    orig = db.row_factory
    try:
        db.row_factory = sqlite3.Row
        return "".join(db.iterdump())
    finally:
        db.row_factory = orig
