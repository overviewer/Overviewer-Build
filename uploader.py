try:
    import boto
except ImportError:
    sys.path.append(r"c:\devel\boto")
    import boto

from boto.s3.connection import S3Connection
from boto.s3.key import Key

class Uploader:
    def check_exists(self, path):
        """Returns true if the given file already exists."""
        raise NotImplementedError()
    def upload(self, path, srcfile):
        """Upload the file located at srcfile to path, and return the
        access URL."""
        raise NotImplementedError()

class S3Uploader(Uploader):
    def __init__(self):
        self.conn = S3Connection('1QWAVYJPN7K868CEDZ82')
        self.bucket = conn.get_bucket("minecraft-overviewer")

    def check_exists(self, path):
        k = self.bucket.get_key(path)
        if k:
            return True
        return False
    
    def upload(self, path, srcfile):
        k = bucket.new_key(path)
        options = {}
        if path.endswith(".txt"):
            options['headers'] = {'Content-Type': 'text/plain'}
        k.set_contents_from_filename(srcfile, **options)
        k.change_storage_class("REDUCED_REDUNDANCY")
        k.make_public()
        
        return "https://s3.amazonaws.com/minecraft-overviewer/%s" % path
