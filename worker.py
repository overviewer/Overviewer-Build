import builder
import uploader
import sys
import traceback
import os
import os.path
import shutil
import hashlib
import hmac
import cPickle
import time
import subprocess
import urllib
import urllib2

try:
    import gearman
except ImportError:
    sys.path.append(r"c:\devel\python-gearman")
    import gearman

secret_key = None
if 'SECRET_KEY' in os.environ:
    secret_key = os.environ['SECRET_KEY'].strip()
else:
    secret_key_path = os.path.split(sys.argv[0])[0]
    secret_key_path = os.path.join(secret_key_path, 'secret_key.txt')
    try:
        with open(secret_key_path) as f:
            secret_key = f.readline().strip()
    except:
        print "You must create the file `%s'" % (secret_key_path,)
        print "and fill it with the build system password on the top line."
        print "(or put it in the SECRET_KEY environment variable.)"
        sys.exit(1)

#upload = uploader.S3Uploader()
upload = uploader.OverviewerOrgUploader()
gm_worker = gearman.GearmanWorker(["192.168.1.4:9092", "em32.net:9092"])

def package_hook(target, commit, version, url):
    hook = "http://overviewer.org/hooks/package"
    data = urllib.urlencode({'target':target, 'commit':commit, 'version':version, 'url':url})
    key = urllib.urlencode({'key':secret_key})
    
    try:
        f = urllib2.urlopen(hook + '?' + key, data)
        f.read()
        f.close()
    except Exception, e:
        print "could not do POST hook:", e
        pass # couldn't contact the server, ack!

def signAndPickle(d):
    data = cPickle.dumps(d)
    h = hmac.new(secret_key, data, hashlib.sha256)
    return h.digest() + data

def uploadLogs(b, result):
    b.close_logs()
    now = time.strftime("%Y_%m_%d_%H:%M:%S")

    err_log = "build_logs/%s.stderr.txt" % now
    result['build_log_stderr'] = upload.upload(err_log, b.stderr_log[1])
    
    out_log = "build_logs/%s.stdout.txt" % now
    result['build_log_stdout'] = upload.upload(out_log, b.stdout_log[1])

def build(worker, job):
    print "got a job!"
    result = dict(status=None)

    if len(job.data) < 33:
        result['status'] = 'ERROR'
        print "ERROR:  job data is not valid.  too short"
        result['msg'] = "ERROR:  job data is not valid.  too short"
        return signAndPickle(result)

    received_h = job.data[0:32]
    # calc hmac of the resulting data
    data = job.data[32:]
    h = hmac.new(secret_key, data, hashlib.sha256)
    if (h.digest() != received_h):
        result['status'] = 'ERROR'
        print "ERROR:  job data is not valid.  bad signature"
        result['msg'] = "ERROR:  job data is not valid.  bad signature"
        return signAndPickle(result)

    print "Data is valid, doing to depickle"
    try:
        depick = cPickle.loads(data)

    except: 
        result['status'] = 'ERROR'
        result['msg'] = "ERROR: can't depickle"
        print "ERROR: can't depickle"
        return signAndPickle(result)

    if type(depick) != dict:
        result['status'] = 'ERROR'
        result['msg'] = "ERROR: input must be a dictionary"
        print "ERROR: input must be a dictionary"
        return signAndPickle(result)


    defaults = depick
    print defaults

    platform = job.task.split("_", 1)[1]
    b = builder.Builder.builders[platform](**defaults)
    num_phases = len(b.phases)
    worker.send_job_status(job, 1, 4 + num_phases)

    try:
        if 'checkout' in defaults:
            b.fetch(checkout=defaults['checkout'])
        else:
            b.fetch()
        worker.send_job_status(job, 2, 4 + num_phases)
    except:
        result['status'] = 'ERROR'
        result['msg'] = 'Error in either the clone or the checkout'
        uploadLogs(b, result) 
        return signAndPickle(result)

    zipname = b.filename()
    print "zipname -->%s<--" % zipname
    
    # before we take the time to build, first see if a copy of this
    # already exists on S3:
    if upload.check_exists(zipname):
        result['status'] = 'SUCCESS'
        result['built'] = False
        print "found a copy already!"
        result['url'] = upload.get_url(zipname)
        uploadLogs(b, result) 
        return signAndPickle(result)

    try:
        for i, phase in enumerate(b.phases):
            b.build(phase=phase)
            worker.send_job_status(job, 3 + i, 4 + num_phases)

        b.post_build()
    except:
        print "something failed"
        result['status'] = 'ERROR'
        result['msg'] = "ERROR: build failed.  Check the build logs for info"
        uploadLogs(b, result) 
        return signAndPickle(result)


    archive = b.package()
    worker.send_job_status(job, 3 + num_phases, 4 + num_phases)
    print "archive: -->%s<--" % archive
    print "done!"

    # upload
    try:
        url = upload.upload(zipname, archive)
        result['status'] = 'SUCCESS'
        result['built'] = True
        result['url'] = url
        uploadLogs(b, result) 
        
        package_hook(platform, b.getCommit(), b.getVersion(), url)
        
        return signAndPickle(result)

    except:
        print "failed to upload to S3"
        traceback.print_exc()
        result['status'] = 'ERROR'
        result['msg'] = "ERROR: failed to upload to S3"
        return signAndPickle(result)

if __name__ == "__main__":
    if not builder.Builder.builders:
        print "no supported builders found, exiting..."
        sys.exit(1)
    
    this_plat = builder.Builder.builders.keys()[0]
    gm_worker.set_client_id("%s_worker" % this_plat)
    for platform in builder.Builder.builders:
        gm_worker.register_task("build_%s" % platform, build)

    while(1):
        print "Starting worker for %s" % this_plat
        try:
            gm_worker.work()
        except gearman.errors.ServerUnavailable:
            print "Server disconnected.  Trying again"

    sys.exit(0)



