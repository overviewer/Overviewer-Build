import sys
import os
import os.path
import threading
import time
import atexit
import cPickle as pickle
import hashlib
import hmac
import tempfile
import shutil
import urllib2

import gearman
from ghub_upload import ghub_upload

# import credentials from elsewhere
from credentials import UPLOAD_USERNAME, UPLOAD_PASSWORD, GEARMAN_SERVER, GEARMAN_KEY

REPO = "overviewer"
BRANCH = "master"

REPO_FORMAT = "git://github.com/{0}/Minecraft-Overviewer.git"
TARGETS = {
    'win32' : 'build_win86_32',
    'win64' : 'build_win86_64',
    'deb32' : 'build_deb86_32',
    'deb64' : 'build_deb86_64',
}

class Uploader(object):
    def handles_target(self, target, repo, branch):
        raise NotImplementedError()
    def handle(self, path, info):
        raise NotImplementedError()
    def finalize(self):
        pass

class GithubUploader(Uploader):
    def handles_target(self, target, repo, branch):
        return target.startswith('win') and repo == 'overviewer'
    def handle(self, path, info):
        bitness = info['func'].split('_', 1)[1]
        description = 'Minecraft Overviewer %s for Windows (%s-bit)' % (info['version'], bitness)
        newname = "overviewer-%s-win%s.zip" % (info['version'], bitness)
        
        url = ghub_upload(path, dest=newname, description=description, username=UPLOAD_USERNAME, password=UPLOAD_PASSWORD, user=info['repo'], repo='Minecraft-Overviewer')
        
        if not url:
            raise Exception('upload of %s failed!' % (info['name'],))

class DebianUploader(Uploader):
    repository = "/var/www/org/overviewer/htdocs/debian"
    packages = "/var/www/org/overviewer/htdocs/debian/packages"
    def __init__(self):
        self.used = False
    def handles_target(self, target, repo, branch):
        return target.startswith('deb') and repo == 'overviewer'
    def handle(self, path, info):
        self.used = True
        shutil.copy(path, self.packages)
    def finalize(self):
        if self.used:
            os.system("make -C %s" % (self.repository,))
        self.used = False

UPLOADERS = [GithubUploader(), DebianUploader()]

# callback takes success, url, stdout, stderr as arguments
# function returns True on successful submission, False on error
def submit_job(gm_client, gm_lock, target, repo, branch, callback):
    orig_checkout = repo + '/' + branch
    
    data = dict(checkout=branch)
    data['repo'] = REPO_FORMAT.format(repo)
    data = pickle.dumps(data)
    h = hmac.new(GEARMAN_KEY, data, hashlib.sha256)
    data = h.digest() + data
    
    func = TARGETS[target]
    
    # watcher thread
    class WatcherThread(threading.Thread):
        def __init__(self, job):
            super(WatcherThread, self).__init__()
            self.job = job
            self.submitted = time.time()
        def run(self):
            while 1:
                time.sleep(1)
                with gm_lock:
                    gm_client.get_job_status(self.job)
                if self.job.complete:
                    # finished job
                    try:
                        res = self.job.result
                        digest = res[:32]
                        dat = pickle.loads(res[32:])
                        if dat['status'] == 'ERROR':
                            callback(False, None, dat['build_log_stdout'], dat['build_log_stderr'])
                            return
                        else:
                            callback(True, dat['url'], dat['build_log_stdout'], dat['build_log_stderr'])
                            return
                    except Exception:
                        callback(False, None, None, None)
                        return
                elif time.time() > self.submitted + 120 and not self.job.status['running']:
                    # stale job
                    callback(False, None, None, None)
                    return
    
    # workaround for gearman failing *every other time*
    for _ in range(2):
        try:
            j = gm_client.submit_job(func, data, background=False, wait_until_complete=False)
            WatcherThread(j).start()
            return True
        except (KeyError, gearman.client.ExceededConnectionAttempts):
            continue
    
    return False

if __name__ == "__main__":
    repo = REPO
    branch = BRANCH
    
    results = {}
    results_lock = threading.RLock()
    
    gm_client = gearman.GearmanClient([GEARMAN_SERVER])
    gm_lock = threading.RLock()
    
    print "[*] building %s/%s" % (repo, branch)
    
    for target in TARGETS:
        def do_submit(sub_target):
            def callback(success, url, stdout, stderr):
                with results_lock:
                    if not success:
                        results[sub_target] = None
                        print "build %s failed:\n\tstdout: %s\n\tstderr: %s" % (sub_target, stdout, stderr)
                        sys.exit(1)
                    else:
                        results[sub_target] = url
                        print "build %s finished" % (sub_target)
            submit_success = submit_job(gm_client, gm_lock, sub_target, repo, branch, callback)
            if not submit_success:
                print "build %s failed to submit" % (sub_target,)
                sys.exit(1)
        do_submit(target)
    print "[*] jobs submitted, awaiting results..."
    
    while 1:
        with results_lock:
            if len(results) == len(TARGETS):
                break
        time.sleep(1)
    
    if not all(results.values()):
        print "[!] some builds did not complete successfully."
        sys.exit(1)
    print "[*] all builds completed, fetching built packages..."
    
    tempdir = tempfile.mkdtemp(prefix='overviewer_builds', suffix=repo+'.'+branch)
    @atexit.register
    def cleanup():
        for uploader in UPLOADERS:
            uploader.finalize()
        if os.path.exists(tempdir):
            shutil.rmtree(tempdir)
    
    files = {}
    
    for target, url in results.iteritems():
        print "fetching %s..." % (target,)
        basename = url.rsplit('/', 1)[1]
        dest = os.path.join(tempdir, basename)
        
        destfile = open(dest, 'wb')
        srcfile = urllib2.urlopen(url)
        shutil.copyfileobj(srcfile, destfile)
        destfile.close()
        srcfile.close()
        
        info = {
            'target' : target,
            'name' : basename,
            'repo' : repo,
            'branch' : branch,
        }
        info_part = os.path.splitext(basename)[0]
        func, describe = info_part.split('-', 1)
        info['func'] = func
        
        try:
            # try a tag-num-gcommit unpack
            tag, commitcount, commit = describe.rsplit('-', 2)
            commitcount = int(commitcount)
            if not commit[0] == 'g':
                raise ValueError('invalid git describe --tags commit')
            commit = commit[1:]
            int(commit, 16)
            info['tag'] = tag
            info['commit'] = commit
            info['commitcount'] = commitcount
            info['version'] = '.'.join(tag[1:].split('.')[:2]) + '.' + str(commitcount)
        except (IndexError, ValueError):
            info['tag'] = describe
            info['commit'] = describe
            info['commitcount'] = 0
            info['version'] = '.'.join(describe[1:].split('.')[:2]) + '.0'
        
        files[dest] = info
    
    print "[*] packages fetched, uploading..."
    
    for fname, finfo in files.iteritems():
        for uploader in UPLOADERS:
            if not uploader.handles_target(finfo['target'], repo, branch):
                continue
            print "uploading %s..." % (finfo['target'],)
            uploader.handle(fname, finfo)
    
    print "[*] done."
    cleanup()
