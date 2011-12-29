from hesperus.plugin import CommandPlugin, PollPlugin
from hesperus.core import ET, ConfigurationError
from hesperus.shorturl import short_url as _short_url
import gearman
import cPickle as pickle
import hashlib
import hmac
from time import time
import traceback
import tempfile
import shutil
import os.path
import os
import urllib2
import string
import random
from fnmatch import fnmatch

class BuildPlugin(CommandPlugin, PollPlugin):
    poll_interval = 2.0
    
    @CommandPlugin.config_types(server=str, key=str, jobs=ET.Element, repo_format=str, default_repo=str)
    def __init__(self, core, server='localhost:9092', key='secret', jobs=None, repo_format="{0}", default_repo=""):
        super(BuildPlugin, self).__init__(core)
        
        self.server = server
        self.key = key
        self.job_timeout = time()
        self.repo_format = repo_format
        self.default_repo = default_repo
        
        self.jobs = {}
        if not jobs:
            return
        for el in jobs:
            name = el.get('name', None)
            short = el.get('short', name)
            if not name:
                raise ConfigurationError('job must have name')
            self.jobs[short] = (name, el.text)
        
        self.gm_client = gearman.GearmanClient([self.server])
        self.running_jobs = []
        self.upload_job = None
    
    def poll(self):
        completed_jobs = []
        for job_tuple in self.running_jobs:
            job, _, start, _ = job_tuple
            self.gm_client.get_job_status(job)
            if time() > start + 120.0 and not job.status['running']:
                # stale job
                completed_jobs.append(job_tuple)
            elif job.complete:
                # finished job
                completed_jobs.append(job_tuple)
            yield
        
        for job_tuple in completed_jobs:
            self.running_jobs.remove(job_tuple)
            job, info, start, callback = job_tuple
            if job.complete:
                # completed job
                self.job_timeout = time()
                try:
                    res = job.result
                    digest = res[:32]
                    dat = pickle.loads(res[32:])
                    if dat['status'] == 'ERROR':
                        self.log_warning("job (%s) %s failed" % info)
                        self.log_warning(dat['build_log_stdout'], dat['build_log_stderr'])
                        callback(False, None, dat['build_log_stdout'], dat['build_log_stderr'])
                    else:
                        self.log_message("job (%s) %s completed: %s" % (info[0], info[1], dat['url'],))
                        callback(True, dat['url'], dat['build_log_stdout'], dat['build_log_stderr'])
                except Exception, e:
                    traceback.print_exc(e)
                    self.log_warning("job (%s) %s failed" % info)
                    callback(False, None, None, None)
            else:
                # stale job
                self.log_warning("job (%s) %s timed out" % info)
                self.log_debug(repr(job.result))
                callback(False, None, None, None)
            yield
    
    # callback takes success, url, stdout, stderr as arguments
    # function returns True on successful submission, False on error
    def submit_job(self, target, repo, branch, callback):
        orig_checkout = repo + '/' + branch
        
        data = dict(checkout=branch)
        data['repo'] = self.repo_format.format(repo)
        data = pickle.dumps(data)
        h = hmac.new(self.key, data, hashlib.sha256)
        data = h.digest() + data
        
        func = self.jobs[target][0]
        
        # workaround for gearman failing *every other time*
        for _ in range(2):
            try:
                j = self.gm_client.submit_job(func, data, background=False, wait_until_complete=False)
                self.running_jobs.append((j, (target, orig_checkout), time(), callback))
                self.job_timeout = time()
                self.log_message("submitted job (%s) %s" % (target, orig_checkout))
                return True
            except (KeyError, gearman.client.ExceededConnectionAttempts):
                continue
        
        self.log_warning("job (%s) %s did not submit" % (target, orig_checkout))
        return False
    
    @CommandPlugin.register_command(r"build(?:\s+help)?")
    def list_command(self, chans, name, match, direct, reply):
        reply("Usage: build <target> [repo[/commit]], where target is one of...")
        for short in self.jobs:
            reply("%s -- %s" % (short, self.jobs[short][1]))
            
    @CommandPlugin.register_command(r"build\s+([.a-zA-Z0-9_-]+)(?:\s+([.a-zA-Z0-9_-]+)(?:/([.a-zA-Z0-9_-]+))?)?")
    def build_command(self, chans, name, match, direct, reply):
        short = match.group(1)
        repo = match.group(2)
        if repo is None:
            repo = self.default_repo
        branch = match.group(3)
        if branch is None:
            branch = "master"
        orig_checkout = repo + '/' + branch
        
        if not short in self.jobs:
            reply("invalid build target: %s" % (short,))
            return
        
        def callback(success, url, stdout, stderr):
            prefix = "job (%s) %s" % (short, orig_checkout)
            if success:
                return reply("%s completed: %s" % (prefix, _short_url(url)))
            if stdout and stderr:
                return reply("%s failed: stdout %s stderr %s" % (prefix, _short_url(stdout), _short_url(stderr)))
            return reply("%s failed :(" % (prefix,))
        
        if self.submit_job(short, repo, branch, callback):
            # success!
            reply("job (%s) %s started..." % (short, orig_checkout))
            return
        
        reply("job (%s) did not submit :/" % (orig_checkout,))
