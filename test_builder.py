import builder

b=builder.WindowsBuilder(python=r"C:\Python26_x64\python.exe")
b.fetch(checkout="dtt-c-render")

b.build(phase="clean")
b.build(phase="build")
b.build(phase="py2exe")
