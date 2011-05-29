import subprocess
import tempfile
import os
import sys
import shutil
import logging
import traceback
import time
import stat
import platform


logger = logging.getLogger("Builder")
logger.setLevel(logging.DEBUG)
logging_handler = logging.StreamHandler()
logger.addHandler(logging_handler)

formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logging_handler.setFormatter(formatter)


if platform.system() == 'Windows':
    if "32bit" in platform.architecture():
        this_plat = "win86_32"
    elif "64bit" in platform.architecture():
        this_plat = "win86_64"
    else:
        raise Exception("what kind of platform is this!")
elif platform.system() == "Linux":
    if "32bit" in platform.architecture():
        this_plat = "lnx86_32"
    elif "64bit" in platform.architecture():
        this_plat = "lnx86_64"
    else:
        raise Exception("what kind of platform is this!")
else:
    raise Exception("Sorry, no support yet")


class Builder(object):
    phases = []
    
    def __init__(self, *args, **kwargs):
        self.logger = logging.getLogger("Builder")
        
        tempfile_options = {}
        if 'tempdir' in kwargs:
            tempfile_options['dir'] = kwargs['tempdir']
        
        self.remote_repo = kwargs.get("repo", "git://github.com/brownan/Minecraft-Overviewer.git")
        
        self.logger.debug("making temp_area: %s", self.temp_area)
        self.temp_area = tempfile.mkdtemp(prefix="mco_build_temp", **tempfile_options)
        os.chdir(self.temp_area)
   
        self.git = kwargs.get("git", "git")
        self.python = kwargs.get("python", sys.executable)

        self.stderr_log = tempfile.mkstemp(prefix="mco_log_", **tempfile_options)
        self.stdout_log = tempfile.mkstemp(prefix="mco_log_", **tempfile_options)

    def forceDeleter(self, func, path, excinfo):
        os.chmod(path, stat.S_IWRITE)
        if os.path.isdir(path):
            try:
                shutil.rmtree(path)
            except:
                print "can't delete ", path
        elif os.path.isfile(path):
            try:
                os.unlink(path)
            except:
                print "can't delete ", path
    
    def __del__(self):
        #os.close(self.stderr_log[0])
        #os.close(self.stdout_log[0])
        try:
            self.logger.debug("deleting temp_area: %s", self.temp_area)
            os.chdir(os.path.split(sys.argv[0])[0])
            print os.getcwd()
            shutil.rmtree(self.temp_area, onerror=self.forceDeleter)
        except:
            print "Failed to delete temp-area:"
            traceback.print_exc()
            time.sleep(4)
            try:
                shutil.rmtree(self.temp_area)
            except:
                print "Failed again!!!"

    def close_logs(self):
        os.close(self.stderr_log[0])
        os.close(self.stdout_log[0])        
        
    def fetch(self, checkout=None):
        "Clones a remote repo into a local directory"
        cmd = [self.git,"clone", self.remote_repo, self.temp_area]
        os.write(self.stdout_log[0], "> [clone]: %s\n" % cmd)
        os.write(self.stderr_log[0], "> [clone]: %s\n" % cmd)
        print cmd
        p = subprocess.Popen(cmd, stdout=self.stdout_log[0], stderr=self.stderr_log[0])
        p.wait()
        if p.returncode != 0:
            self.logger.error("Error fetching")
            raise Exception()
        
        self.logger.info("Cloned.")

        if checkout:
            cmd = [self.git, "checkout", checkout]
            os.write(self.stdout_log[0], "> [checkout]: %s\n" % cmd)
            os.write(self.stderr_log[0], "> [checkout]: %s\n" % cmd)
            print cmd
            p = subprocess.Popen(cmd, stdout=self.stdout_log[0], stderr=self.stderr_log[0])
            p.wait()
            if p.returncode != 0:
                self.logger.error("Failed to checkout %s", checkout)
                raise Exception()

        return 0

    def getDesc(self):
        cmd = [self.git, "describe", "--tags"]
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        p.wait()
        return p.stdout.read().strip()
        
    def build(self, phase="build"):
        raise NotYetImplemented()
    
    def package(self):
        raise NotYetImplemented()
        

class WindowsBuilder(Builder):
    phases = ["clean", "build", "py2exe"]
    
    def __init__(self, *args, **kwargs):
        #self.logger = logging.getLogger("Builder.WindowsBuilder")
        kwargs['tempdir'] = "C:\\temp\\"
        kwargs['git'] = "git.cmd"
        Builder.__init__(self, *args, **kwargs)

        self.zipper = r"C:\Program Files\7-Zip\7z.exe"

        self._checkBuildTools()

        os.environ['PIL_INCLUDE_DIR'] = r"C:\devel\PIL-1.1.7\libImaging"
        os.environ['DISTUTILS_USE_SDK'] = "1"
        os.environ['MSSdk'] = "1"
        
    def findExe(self, exe, path=None):
        if path and type(path) == str:
            path = path.split(os.pathsep)
        if not path:
            path = os.environ['PATH'].split(os.pathsep)
        l = map(lambda x: os.path.join(x, exe), path)
        return filter(os.path.exists, l)

    def _checkBuildTools(self):
        "Makes sure that all of the build tools are ready to go"
        if not self.findExe(exe="cl.exe"):
            raise Exception("Don't know where cl.exe is")

        if not self.findExe(exe="link.exe"):
            raise Exception("Don't know where link.exe is")
        
        #if not self.findExe(exe="7z.exe"):
        #    os.environ['PATH'] += os.pathsep + self.zipper
        #    raise Exception("Don't know where 7z is")
    

    def build(self, phase="build"):
        cmd = [self.python, "setup.py", phase]
        os.write(self.stdout_log[0], "> [build]: %s\n" % cmd)
        os.write(self.stderr_log[0], "> [build]: %s\n" % cmd)
        p = subprocess.Popen(cmd, stdout=self.stdout_log[0], stderr=self.stderr_log[0])
        p.wait()
        if p.returncode != 0:
            self.logger.error("Failed to build phase %s", phase)
            raise Exception()

    def zip(self, root, archive):
        old_cwd = os.getcwd()
        print "old_cwd: ", old_cwd
        os.chdir(root)
        cmd = [self.zipper, "a", archive, "."]
        os.write(self.stdout_log[0], "> [zip]: %s\n" % cmd)
        os.write(self.stderr_log[0], "> [zip]: %s\n" % cmd)
        p = subprocess.Popen(cmd, stdout=self.stdout_log[0], stderr=self.stderr_log[0])
        p.wait()
        print "returncode: ", p.returncode
        os.chdir(old_cwd)
        if p.returncode != 0:
            print "failed to zip"
            raise Exception("failed to zip")
        if not os.path.exists(os.path.join(root,archive)):
            print "something went wrong, the archive dosn'et exist"
            raise Exception("something went wrong.  the archive doesn't exist")
        return os.path.abspath(os.path.join(root,archive))

class LinuxBuilder(Builder):
    pass

class OSXBuilder(Builder):
    pass




