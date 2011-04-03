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

def build(worker, job):
    print "got a job!"
    worker.send_job_status(job, 1, 8)
    if len(job.data) < 33:
        print "ERROR:  job data is not valid.  too short"
        return "ERROR:  job data is not valid.  too short"

    received_h = job.data[0:32]
    # calc hmac of the resulting data
    data = job.data[32:]
    h = hmac.new("thisa realyreally secreyKEY", data, hashlib.sha256)
    if (h.digest() != received_h):
        print "ERROR:  job data is not valid.  bad signature"
        return "ERROR:  job data is not valid.  bad signature"

    print "Data is valid, doing to depickle"
    try:
        depick = cPickle.loads(data)

    except:
        return "ERROR: can't depickle"

    if type(depick) != dict:
        return "ERROR: type should be dictionary"


    defaults = dict(repo="git://github.com/agrif/Minecraft-Overviewer.git",
                    checkout="dtt-c-render",
                    python=sys.executable)

    defaults.update(depick)
    print defaults

    return "OK!"
        
    

    b = builder.WindowsBuilder(**defaults)
    worker.send_job_status(job, 2, 8)

    b.fetch(checkout="dtt-c-render")
    worker.send_job_status(job, 3, 8)

    desc = b.getDesc()
    zipname = "%s-%s.zip" % (this_plat, desc)
    print "zipname -->%s<--" % zipname

    k = bucket.get_key(zipname)
    if k:
        print "found a copy already!"
        return "https://s3.amazonaws.com/minecraft-overviewer/" + zipname

    # before we take the time to build, first see if a copy of this
    # already exists on S3:
    

    b.build(phase="clean")
    worker.send_job_status(job, 4, 8)

    b.build(phase="build")
    worker.send_job_status(job, 5, 8)

    b.build(phase="py2exe")
    worker.send_job_status(job, 6, 8)


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
        return "https://s3.amazonaws.com/minecraft-overviewer/" + zipname

    except:
        print "failed to upload to S3"
        traceback.print_exc()
        return "Error: Failed to upload to S3"

    return archive

gm_worker.set_client_id("%s_worker" % this_plat)
gm_worker.register_task("build_%s" % this_plat, build)

print "Starting worker for %s" % this_plat
gm_worker.work()

sys.exit(0)



