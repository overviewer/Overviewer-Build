import builder
import sys
import traceback
import os
import shutil
import hashlib
import hmac
import cPickle
import time

this_plat = builder.this_plat

try:
    import gearman
except ImportError:
    sys.path.append(r"c:\devel\python-gearman")
    import gearman

try:
    import boto
except ImportError:
    sys.path.append(r"c:\devel\boto")
    import boto

from boto.s3.connection import S3Connection
from boto.s3.key import Key

conn = S3Connection('1QWAVYJPN7K868CEDZ82')
bucket = conn.get_bucket("minecraft-overviewer")

gm_worker = gearman.GearmanWorker(["192.168.1.4:9092", "em32.net:9092"])

def signAndPickle(d):
    data = cPickle.dumps(d)
    h = hmac.new("thisa realyreally secreyKEY", data, hashlib.sha256)
    return h.digest() + data

def uploadLogs(b, result):
    b.close_logs()
    now = time.strftime("%Y_%m_%d_%H:%M:%S")
    err_log = "build_logs/%s.stderr.txt" % now
    k = bucket.new_key(err_log)
    k.set_contents_from_filename(b.stderr_log[1], headers={'Content-Type': 'text/plain'})
    k.change_storage_class("REDUCED_REDUNDANCY")
    k.make_public()
    result['build_log_stderr'] = "https://s3.amazonaws.com/minecraft-overviewer/%s" % err_log
    
    out_log = "build_logs/%s.stdout.txt" % now
    k = bucket.new_key(out_log)
    k.set_contents_from_filename(b.stdout_log[1], headers={'Content-Type': 'text/plain'})
    k.change_storage_class("REDUCED_REDUNDANCY")
    k.make_public()
    result['build_log_stdout'] = "https://s3.amazonaws.com/minecraft-overviewer/%s" % out_log

def build(worker, job):
    print "got a job!"
    worker.send_job_status(job, 1, 8)
    result = dict(status=None)

    if len(job.data) < 33:
        result['status'] = 'ERROR'
        print "ERROR:  job data is not valid.  too short"
        result['msg'] = "ERROR:  job data is not valid.  too short"
        return signAndPickle(result)

    received_h = job.data[0:32]
    # calc hmac of the resulting data
    data = job.data[32:]
    h = hmac.new("thisa realyreally secreyKEY", data, hashlib.sha256)
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


    defaults = dict(repo="git://github.com/agrif/Minecraft-Overviewer.git",
                    checkout="dtt-c-render",
                    python=sys.executable)

    defaults.update(depick)
    print defaults

    

    b = builder.WindowsBuilder(**defaults)
    worker.send_job_status(job, 2, 8)

    try:
        b.fetch(checkout=defaults['checkout'])
        worker.send_job_status(job, 3, 8)
    except:
        result['status'] = 'ERROR'
        result['msg'] = 'Error in either the clone or the checkout'
        uploadLogs(b, result) 
        return signAndPickle(result)


    desc = b.getDesc()
    zipname = "%s-%s.zip" % (this_plat, desc)
    print "zipname -->%s<--" % zipname

    k = bucket.get_key(zipname)
    if k:
        result['status'] = 'SUCCESS'
        result['built'] = False
        print "found a copy already!"
        result['url'] = "https://s3.amazonaws.com/minecraft-overviewer/" + zipname
        uploadLogs(b, result) 
        return signAndPickle(result)

    # before we take the time to build, first see if a copy of this
    # already exists on S3:
    
    try:
        b.build(phase="clean")
        worker.send_job_status(job, 4, 8)

        b.build(phase="build")
        worker.send_job_status(job, 5, 8)

        b.build(phase="py2exe")
        worker.send_job_status(job, 6, 8)
    except:
        print "something failed"
        result['status'] = 'ERROR'
        result['msg'] = "ERROR: build failed.  Check the build logs for info"
        uploadLogs(b, result) 
        return signAndPickle(result)
        
        



    archive= b.zip(root="dist", archive=zipname)
    worker.send_job_status(job, 7, 8)
    print "archive: -->%s<--" % archive
    try:
        print "trying to shcopy"
        print "exists:" , os.path.exists(archive)
        shutil.copy(archive, "c:\\devel\\")
        print "copy was OK"
    except:
        print "error in the copy!"
        traceback.print_exc()
    print "done!"

    try:
        k = bucket.new_key(zipname)
        k.set_contents_from_filename(archive)
        k.change_storage_class("REDUCED_REDUNDANCY")
        k.make_public()
        #url = k.generate_url(86400)
        result['status'] = 'SUCCESS'
        result['built'] = True
        result['url'] = "https://s3.amazonaws.com/minecraft-overviewer/" + zipname
        uploadLogs(b, result) 
        return signAndPickle(result)

    except:
        print "failed to upload to S3"
        traceback.print_exc()
        result['status'] = 'ERROR'
        result['msg'] = "ERROR: failed to upload to S3"
        return signAndPickle(result)

    print "\n\n--------\nBuild complete\n\n"
    return archive

if __name__ == "__main__":
    gm_worker.set_client_id("%s_worker" % this_plat)
    gm_worker.register_task("build_%s" % this_plat, build)

    while(1):
        print "Starting worker for %s" % this_plat
        try:
            gm_worker.work()
        except gearman.errors.ServerUnavailable:
            print "Server disconnected.  Trying again"

    sys.exit(0)



