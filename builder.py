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


class Builder(object):
    phases = []
    
    builders = {}
    @classmethod
    def register(cls, **kwargs):
        def sub_register(builder):
            for key in kwargs:
                def sub_constructor(*sub_args, **sub_kwargs):
                    b = builder(*sub_args, **sub_kwargs)
                    b.platform = key
                    return b
                if kwargs[key]:
                    cls.builders[key] = sub_constructor
        return sub_register
        
    def __init__(self, *args, **kwargs):
        self.logger = logging.getLogger("Builder")
        
        tempfile_options = {}
        if 'tempdir' in kwargs:
            tempfile_options['dir'] = kwargs['tempdir']
        
        self.remote_repo = kwargs.get("repo", "git://github.com/brownan/Minecraft-Overviewer.git")
        
        self.temp_area = tempfile.mkdtemp(prefix="mco_build_temp", **tempfile_options)
        self.logger.debug("making temp_area: %s", self.temp_area)
        self.original_dir = os.getcwd()
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
            os.chdir(self.original_dir)
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
    
    # helper for doing commands, and redirecting to our logs
    def popen(self, action, cmd):
        self.logger.info("running command [%s]" % action)
        os.write(self.stdout_log[0], "> [%s]: %s\n" % (action, cmd))
        os.write(self.stderr_log[0], "> [%s]: %s\n" % (action, cmd))
        p = subprocess.Popen(cmd, stdout=self.stdout_log[0], stderr=self.stderr_log[0])
        p.wait()
        if p.returncode != 0:
            self.logger.error("Error during [%s]" % action)
            raise Exception()
        
    def fetch(self, checkout=None):
        "Clones a remote repo into a local directory"

        self.popen("clone", [self.git,"clone", self.remote_repo, self.temp_area])        
        self.logger.info("Cloned.")

        if checkout:
            self.popen("checkout", [self.git, "checkout", checkout])

        return 0

    def getDesc(self):
        cmd = [self.git, "describe", "--tags"]
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        p.wait()
        return p.stdout.read().strip()
    
    # called for each phase in self.phases
    def build(self, phase="build"):
        self.popen("build " + phase, [self.python, "setup.py", phase])
    
    # returns the filename on the (eventual) server
    def filename(self):
        raise NotYetImplemented()
    
    # called after all the phases are done, returns a filename to upload
    def package(self):
        raise NotYetImplemented()
        
@Builder.register(win86_32 = platform.system() == 'Windows' and '32bit' in platform.architecture(),
                  win86_64 = platform.system() == 'Windows' and '64bit' in platform.architecture())
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
        
    def filename(self):
        desc = b.getDesc()
        zipname = "%s-%s.zip" % (self.platform, desc)
        return zipname
    
    def package(self):
        zipname = self.filename()
        return b.zip(root="dist", archive=zipname)
    
    def zip(self, root, archive):
        old_cwd = os.getcwd()
        print "old_cwd: ", old_cwd
        os.chdir(root)
        try:
            self.popen("zip", [self.zipper, "a", archive, "."])
            if not os.path.exists(os.path.join(root,archive)):
                print "something went wrong, the archive dosn'et exist"
                raise Exception("something went wrong.  the archive doesn't exist")
        finally:
            os.chdir(old_cwd)
        return os.path.abspath(os.path.join(root,archive))

class LinuxBuilder(Builder):
    pass

@Builder.register(osx_app = platform.system() == 'Darwin')
class OSXBuilder(Builder):
    phases = ['clean', 'py2app']
    def __init__(self, *args, **kwargs):
        Builder.__init__(self, *args, **kwargs)
        os.environ['PIL_INCLUDE_DIR'] = r"/home/agrif/devel/mc-overviewer"
        
    def filename(self):
        desc = self.getDesc()
        return "%s-%s.dmg" % (self.platform, desc)
    
    def package(self):
        dmgname = self.filename()
        self.popen("dmgcreate", ['hdiutil', 'create', dmgname, '-srcfolder', './dist/'])
        return dmgname
