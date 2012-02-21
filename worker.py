#!/usr/bin/env python

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
import logging

try:
    import gearman
except ImportError:
    sys.path.append(r"c:\devel\python-gearman")
    import gearman

logger = logging.getLogger("Worker")
logger.setLevel(logging.DEBUG)
logging_handler = logging.StreamHandler()
logger.addHandler(logging_handler)

formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logging_handler.setFormatter(formatter)

try:
    import worker_config
except ImportError, e:
    logger.exception('Error importing worker config file')
    sys.exit(1)

#upload = uploader.S3Uploader()
upload = uploader.OverviewerOrgUploader()
gm_worker = gearman.GearmanWorker(worker_config.gearman_hosts)

def package_hook(platform, repo, checkout, commit, version, url):
    hook = worker_config.package_hook_url
    data = urllib.urlencode({
        'platform': platform,
        'repo': repo,
        'checkout': checkout,
        'commit': commit,
        'version': version,
        'url': url,
    })
    key = urllib.urlencode({'key': worker_config.secret_key})

    try:
        f = urllib2.urlopen(hook + '?' + key, data)
        f.read()
        f.close()
    except Exception, e:
        logger.exception('could not do POST hook')
        pass # couldn't contact the server, ack!

def signAndPickle(d):
    data = cPickle.dumps(d)
    h = hmac.new(worker_config.secret_key, data, hashlib.sha256)
    return h.digest() + data

def uploadLogs(b, result):
    b.close_logs()
    now = time.strftime("%Y_%m_%d_%H:%M:%S")

    err_log = "build_logs/%s.stderr.txt" % now
    result['build_log_stderr'] = upload.upload(err_log, b.stderr_log[1])

    out_log = "build_logs/%s.stdout.txt" % now
    result['build_log_stdout'] = upload.upload(out_log, b.stdout_log[1])

def build(worker, job):
    logger.info('Received job!')
    result = dict(status=None)

    if len(job.data) < 33:
        status = 'ERROR'
        msg = 'Job data is not valid: too short'
        result['status'] = status
        result['msg'] = '%s: %s' % (status, msg)
        logger.error(msg)
        return signAndPickle(result)

    received_h = job.data[0:32]
    # calc hmac of the resulting data
    data = job.data[32:]
    h = hmac.new(worker_config.secret_key, data, hashlib.sha256)
    if (h.digest() != received_h):
        status = 'ERROR'
        msg = 'Job data is not valid: bad signature'
        result['status'] = status
        logger.error(msg)
        result['msg'] = '%s: %s' % (status, msg)
        return signAndPickle(result)

    logger.info('Data is valid, depickling')
    try:
        depick = cPickle.loads(data)
    except:
        status = 'ERROR'
        msg = 'Can\'t depickle'
        result['status'] = status
        result['msg'] = '%s: %s' % (status, msg)
        logger.error(msg)
        return signAndPickle(result)

    if type(depick) != dict:
        status = 'ERROR'
        msg = 'Input must be a dictionary'
        result['status'] = status
        result['msg'] = '%s: %s' % (status, msg)
        logger.error(msg)
        return signAndPickle(result)


    defaults = depick
    logger.debug(defaults)

    platform = job.task.split("_", 1)[1]
    b = builder.Builder.builders[platform](**defaults)
    num_phases = len(b.phases)
    worker.send_job_status(job, 1, 4 + num_phases)

    logger.info('Job is for %s with %d phases', platform, num_phases)

    try:
        if 'checkout' in defaults:
            b.fetch(checkout=defaults['checkout'])
        else:
            b.fetch()
        worker.send_job_status(job, 2, 4 + num_phases)
    except:
        result['status'] = 'ERROR'
        result['msg'] = 'Error in either the clone or the checkout'
        logger.exception('Error in either the clone or checkout')
        uploadLogs(b, result)
        return signAndPickle(result)

    zipname = b.filename()
    logger.debug('zipname: %s' % zipname)

    # before we take the time to build, first see if a copy of this
    # already exists on S3:
    if upload.check_exists(zipname):
        result['status'] = 'SUCCESS'
        result['built'] = False
        logger.info('zipname already exists on upload target')
        result['url'] = upload.get_url(zipname)
        uploadLogs(b, result)
        return signAndPickle(result)

    try:
        for i, phase in enumerate(b.phases):
            b.build(phase=phase)
            worker.send_job_status(job, 3 + i, 4 + num_phases)

        b.post_build()
    except:
        logger.exception('build failed')
        result['status'] = 'ERROR'
        result['msg'] = "ERROR: build failed.  Check the build logs for info"
        uploadLogs(b, result)
        return signAndPickle(result)


    archive = b.package()
    worker.send_job_status(job, 3 + num_phases, 4 + num_phases)
    logger.debug('archive: %s' % archive)
    logger.info('Build done!')

    # upload
    try:
        url = upload.upload(zipname, archive)
        result['status'] = 'SUCCESS'
        result['built'] = True
        result['url'] = url
        uploadLogs(b, result)

        package_hook(platform, defaults.get('repo', ''),
            defaults.get('checkout', 'master'), b.getCommit(),
            b.getVersion(), url)

        return signAndPickle(result)

    except:
        logger.exception('Failed to upload to S3')
        result['status'] = 'ERROR'
        result['msg'] = "ERROR: failed to upload to S3"
        return signAndPickle(result)

if __name__ == "__main__":
    import uuid

    if not builder.Builder.builders:
        logger.error('No supported builders found, exiting')
        sys.exit(1)

    client_id = uuid.uuid1()
    logger.info('Worker identified as: %s', client_id)
    gm_worker.set_client_id(client_id)
    for platform in builder.Builder.builders:
        logger.info('Registering builder: %s' % platform)
        gm_worker.register_task("build_%s" % platform, build)

    while(1):
        logger.info('Starting worker')
        try:
            gm_worker.work()
        except gearman.errors.ServerUnavailable:
            logger.warning('Server disconnected. Trying again')
            time.sleep(1)

    sys.exit(0)