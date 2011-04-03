import builder
import sys
import traceback
import os
import shutil

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

gm_worker = gearman.GearmanWorker(["192.168.1.4:9092"])

def build(worker, job):
    print "got a job!"

    worker.send_job_status(job, 1, 7)

    b = builder.WindowsBuilder()
    worker.send_job_status(job, 2, 7)

    b.fetch(checkout="dtt-c-render")
    worker.send_job_status(job, 3, 7)

    desc = b.getDesc()
    zipname = "win86_32-%s.zip" % desc
    print "zipname -->%s<--" % zipname

    k = bucket.get_key(zipname)
    if k:
        print "found a copy already!"
        return "https://s3.amazonaws.com/minecraft-overviewer/" + zipname

    # before we take the time to build, first see if a copy of this
    # already exists on S3:
    

    b.build(phase="clean")
    worker.send_job_status(job, 4, 7)

    b.build(phase="build")
    worker.send_job_status(job, 5, 7)

    b.build(phase="py2exe")
    worker.send_job_status(job, 6, 7)


    archive= b.zip(root="dist", archive=zipname)
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

    return archive

gm_worker.set_client_id("win86_32_worker")
gm_worker.register_task("build_win86_32", build)

gm_worker.work()

sys.exit(0)



