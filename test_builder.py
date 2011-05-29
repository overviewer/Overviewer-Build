import builder

b=builder.WindowsBuilder()
b.fetch()

for phase in b.phases:
    b.build(phase=phase)
