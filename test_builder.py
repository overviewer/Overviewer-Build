import builder
import sys
import traceback

try:
    def_plat = builder.Builder.builders.keys()[0]
except:
    print "no supported builders..."
    sys.exit(1)

try:
    def_plat = sys.argv[1]
except:
    pass

defaults = {'repo' : 'git://github.com/overviewer/Minecraft-Overviewer.git',
            'checkout' : 'master'}

try:
    print "building on platform", def_plat
    b = builder.Builder.builders[def_plat](**defaults)
    print "builder thinks it's for", b.platform
    if 'checkout' in defaults:
        b.fetch(checkout=defaults['checkout'])
    else:
        b.fetch()
    for phase in b.phases:
        b.build(phase=phase)
        
    print "archive:", b.package()
except:
    print "Exception:"
    traceback.print_exc()
    print "STDOUT:"
    print open(b.stdout_log[1]).read()
    print "STDERR:"
    print open(b.stderr_log[1]).read()
