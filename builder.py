import subprocess
import tempfile
import os
import shutil
import logging
import traceback
import time
import stat
import platform

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


def findExe(exe, path=None):
    if path and type(path) == str:
        path = path.split(os.pathsep)
    if not path:
        path = os.environ['PATH'].split(os.pathsep)
    l = map(lambda x: os.path.join(x, exe), path)
    return filter(os.path.exists, l)

def forceDeleter(func, path, excinfo):
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


class Zipper(object):
    "Zips up stuff"
    pass

logger = logging.getLogger("Builder")
logger.setLevel(logging.DEBUG)
logging_handler = logging.StreamHandler()
logger.addHandler(logging_handler)

formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logging_handler.setFormatter(formatter)

class Builder(object):
    def __init__(self, *args, **kwargs):
        self.logger = logging.getLogger("Builder")

        self.remote_repo = kwargs.get("repo", "git://github.com/agrif/Minecraft-Overviewer.git")
        self.temp_area = tempfile.mkdtemp(dir="c:\\temp", prefix="mco_build_temp")
        os.chdir(self.temp_area)
   
        self.python = kwargs.get("python", r"C:\python26\python.exe") 
        self.zipper = kwargs.get("zip", "zip")
    
        self.logger.debug("making temp_area: %s", self.temp_area)
    def __del__(self):
        try:
            self.logger.debug("deleting temp_area: %s", self.temp_area)
            os.chdir("\\")
            print os.getcwd()
            shutil.rmtree(self.temp_area, onerror=forceDeleter)
        except:
            print "Failed to delete temp-area:"
            traceback.print_exc()
            time.sleep(4)
            try:
                shutil.rmtree(self.temp_area)
            except:
                print "Failed again!!!"
        
        
    def fetch(self, checkout=None):
        "Clones a remote repo into a local directory"
        cmd = ["git","clone", self.remote_repo, self.temp_area]
        p = subprocess.Popen(cmd)
        p.wait()
        if p.returncode != 0:
            self.logger.error("Error fetching")
            raise Exception()
        
        self.logger.info("Cloned.")

        if checkout:
            cmd = ["git", "checkout", checkout]
            p = subprocess.Popen(cmd)
            p.wait()
            if p.returncode != 0:
                self.logger.error("Failed to checkout %s", checkout)
                raise Exception()

        return 0

    def getDesc(self):
        cmd = ["git", "describe", "--tags"]
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        p.wait()
        return p.stdout.read().strip()
        
    def build(self):
        raise NotYetImplemented()

    def zip(self, root, archive):
        old_cwd = os.getcwd()
        print "old_cwd: ", old_cwd
        os.chdir(root)
        cmd = [self.zipper, "a", archive, "."]
        p = subprocess.Popen(cmd)
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

        
        

class WindowsBuilder(Builder):
    def __init__(self, *args, **kwargs):
        #self.logger = logging.getLogger("Builder.WindowsBuilder")        
        Builder.__init__(self, *args, **kwargs)

        self.zipper = r"C:\Program Files\7-Zip\7z.exe"

        self._checkBuildTools()

        os.environ['PIL_INCLUDE_DIR'] = r"C:\devel\PIL-1.1.7\libImaging"

    def _checkBuildTools(self):
        "Makes sure that all of the build tools are ready to go"
        if not findExe(exe="cl.exe"):
            raise Exception("Don't know where cl.exe is")

        if not findExe(exe="link.exe"):
            raise Exception("Don't know where link.exe is")
        
        #if not findExe(exe="7z.exe"):
        #    os.environ['PATH'] += os.pathsep + self.zipper
        #    raise Exception("Don't know where 7z is")
    

    def build(self, phase="build"):
        cmd = [self.python, "setup.py", phase]
        p = subprocess.Popen(cmd)
        p.wait()
        if p.returncode != 0:
            self.logger.error("Failed to build phase %s", phase)
            raise Exception()

class LinuxBuilder(Builder):
    pass

class OSXBuilder(Builder):
    pass




