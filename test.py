from DsqFile import DsqFile

dsq = DsqFile()

with open("/home/ns/download/BlocklandPortable/base/data/shapes/player/m_new_test.dsq", "rb") as fd:
    dsq.read(fd)

with open("./dump.txt", "w") as fd:
    dsq.write_dump(fd)
