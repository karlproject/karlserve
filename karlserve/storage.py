import cgi
import os
from cStringIO import StringIO
import urlparse

from repoze.zodbconn.datatypes import byte_size
from repoze.zodbconn.datatypes import FALSETYPES
from repoze.zodbconn.datatypes import TRUETYPES

from relstorage.options import Options
from relstorage.storage import RelStorage
from relstorage.adapters.postgresql import PostgreSQLAdapter

from ZEO.ClientStorage import ClientStorage
from ZODB.FileStorage.FileStorage import FileStorage
from ZODB.blob import BlobStorage
import ZConfig


def storage_from_config(options, prefix=None):
    def w_prefix(name):
        if prefix is not None:
            return '%s.%s' % (prefix, name)
        return name

    uri = options.get(w_prefix('zodb_uri'))
    if uri is not None:
        return _storage_from_uri(uri)

    dsn = options.get(w_prefix('dsn'))
    if dsn is not None:
        return _storage_from_dsn(dsn, options, w_prefix)

    return None


def _storage_from_dsn(dsn, options, w_prefix):
    options = Options(**{
        'blob_dir': options[w_prefix('blob_cache')],
        'shared_blob_dir': False,
        'keep_history': options.get(w_prefix('keep_history'), False),
    })
    adapter = PostgreSQLAdapter(dsn, options=options)
    storage = RelStorage(adapter, options=options)

    return storage


##############################################################################
#
# Adapted from repoze.zodbconn.resolvers.  Could not use repoze.zodbconn
# because it returns databases and we need the raw storages.
#
# Might(?) be useful to have repoze.zodbconn support getting storages.
#


def _storage_from_uri(uri):
    parsed = urlparse.urlparse(uri)
    resolver = _RESOLVERS.get(parsed.scheme)
    if resolver is None:
        raise ValueError("Unresolvable database URI: %s" % uri)
    return resolver(uri)


def _interpret_int_args(argnames, kw):
    newkw = {}

    # boolean values are also treated as integers
    for name in argnames:
        value = kw.get(name)
        if value is not None:
            value = value.lower()
            if value in FALSETYPES:
                value = 0
            if value in TRUETYPES:
                value = 1
            value = int(value)
            newkw[name] = value

    return newkw

def _interpret_string_args(argnames, kw):
    newkw = {}
    # strings
    for name in argnames:
        value = kw.get(name)
        if value is not None:
            newkw[name] = value
    return newkw

def _interpret_bytesize_args(argnames, kw):
    newkw = {}

    # suffix multiplied
    for name in argnames:
        value = kw.get(name)
        if value is not None:
            newkw[name] = byte_size(value)

    return newkw


class _Resolver(object):
    def interpret_kwargs(self, kw):
        new = {}
        newkw = _interpret_int_args(self._int_args, kw)
        new.update(newkw)
        newkw = _interpret_string_args(self._string_args, kw)
        new.update(newkw)
        newkw = _interpret_bytesize_args(self._bytesize_args, kw)
        new.update(newkw)
        return new


class _FileStorageURIResolver(_Resolver):
    _int_args = ('create', 'read_only', 'demostorage', 'connection_cache_size',
                 'connection_pool_size')
    _string_args = ('blobstorage_dir', 'blobstorage_layout', 'database_name')
    _bytesize_args = ('quota',)
    def __call__(self, uri):
        # we can't use urlparse.urlsplit here due to Windows filenames
        prefix, rest = uri.split('file://', 1)
        result = rest.split('?', 1)
        if len(result) == 1:
            path = result[0]
            query = ''
        else:
            path, query = result
        path = os.path.normpath(path)
        kw = dict(cgi.parse_qsl(query))
        kw = self.interpret_kwargs(kw)
        args = (path,)

        blobstorage_dir = None
        blobstorage_layout = 'automatic'
        if 'blobstorage_dir' in kw:
            blobstorage_dir = kw.pop('blobstorage_dir')
        if 'blobstorage_layout' in kw:
            blobstorage_layout = kw.pop('blobstorage_layout')

        if blobstorage_dir:
            filestorage = FileStorage(*args, **kw)
            return BlobStorage(blobstorage_dir, filestorage,
                               layout=blobstorage_layout)

        else:
            return FileStorage(*args, **kw)


class _ClientStorageURIResolver(_Resolver):
    _int_args = ('debug', 'min_disconnect_poll', 'max_disconnect_poll',
                 'wait_for_server_on_startup', 'wait', 'wait_timeout',
                 'read_only', 'read_only_fallback', 'shared_blob_dir',
                 'demostorage', 'connection_cache_size',
                 'connection_pool_size')
    _string_args = ('storage', 'name', 'client', 'var', 'username',
                    'password', 'realm', 'blob_dir', 'database_name')
    _bytesize_args = ('cache_size', )

    def __call__(self, uri):
        # urlparse doesnt understand zeo URLs so force to something that doesn't break
        uri = uri.replace('zeo://', 'http://', 1)
        (scheme, netloc, path, query, frag) = urlparse.urlsplit(uri)
        if netloc:
            # TCP URL
            if ':' in netloc:
                host, port = netloc.split(':')
                port = int(port)
            else:
                host = netloc
                port = 9991
            args = ((host, port),)
        else:
            # Unix domain socket URL
            path = os.path.normpath(path)
            args = (path,)
        kw = dict(cgi.parse_qsl(query))
        kw = self.interpret_kwargs(kw)
        return ClientStorage(*args, **kw)


class _ZConfigURIResolver(object):

    schema_xml_template = """
    <schema>
        <import package="ZODB"/>
        <multisection type="ZODB.storage" attribute="databases" />
    </schema>
    """

    def __call__(self, uri):
        (scheme, netloc, path, query, frag) = urlparse.urlsplit(uri)
         # urlparse doesnt understand file URLs and stuffs everything into path
        (scheme, netloc, path, query, frag) = urlparse.urlsplit('http:' + path)
        path = os.path.normpath(path)
        schema_xml = self.schema_xml_template
        schema = ZConfig.loadSchemaFile(StringIO(schema_xml))
        config, handler = ZConfig.loadConfig(schema, path)
        for factory in config.databases:
            if not frag:
                # use the first defined in the file
                break
            elif frag == factory.name:
                # match found
                break
        else:
            raise KeyError("No database named %s found" % frag)
        return factory.open()


_RESOLVERS = {
    'zeo': _ClientStorageURIResolver(),
    'file': _FileStorageURIResolver(),
    'zconfig': _ZConfigURIResolver(),
}
