import builder
import sys

try:
    def_plat = builder.Builder.builders.keys()[0]
except:
    print "no supported builders..."
    sys.exit(1)

try:
    def_plat = sys.argv[1]
except:
    pass

b = builder.Builder.builders[def_plat]()

b.fetch()

for phase in b.phases:
    b.build(phase=phase)

print "archive:", b.package()
