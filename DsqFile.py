from .DtsTypes import Sequence, Trigger, Vector, Quaternion
from struct import pack, unpack, calcsize
from ctypes import c_byte, c_short, c_int

def read(fd, fmt):
    return unpack(fmt, fd.read(calcsize(fmt)))

def write(fd, fmt, *values):
    fd.write(pack(fmt, *values))

def write_quat(fd, q):
    write(fd, "4h",
        c_short(int(q.x *  32767)).value,
        c_short(int(q.y *  32767)).value,
        c_short(int(q.z *  32767)).value,
        c_short(int(q.w * -32767)).value)

def write_vec(fd, v):
    write(fd, "3f", v.x, v.y, v.z)

def read_quat(fd):
    x, y, z, w = read(fd, "4h")
    return Quaternion((
        w / -32767,
        x /  32767,
        y /  32767,
        z /  32767))

def read_vec(fd):
    return Vector(read(fd, "3f"))

class DsqFile:
    def __init__(self):
        self.nodes = []
        self.rotations = []
        self.translations = []
        self.uniform_scales = []
        self.aligned_scales = []
        self.arbitrary_scale_rots = []
        self.arbitrary_scale_factors = []
        self.ground_translations = []
        self.ground_rotations = []
        self.sequences = []
        self.triggers = []

    def write_dump(self, fd):
        def p(s):
            fd.write(s + "\n")

        p("# rotations: {}".format(len(self.rotations)))
        p("# translations: {}".format(len(self.translations)))
        p("# uniform_scales: {}".format(len(self.uniform_scales)))
        p("# aligned_scales: {}".format(len(self.aligned_scales)))
        p("# arbitrary_scale_rots: {}".format(len(self.arbitrary_scale_rots)))
        p("# arbitrary_scale_factors: {}".format(len(self.arbitrary_scale_factors)))
        p("# ground_translations: {}".format(len(self.ground_translations)))
        p("# ground_rotations: {}".format(len(self.ground_rotations)))

        p("Nodes ({}):".format(len(self.nodes)))
        for i, name in enumerate(self.nodes):
            p("  {}: {}".format(i, name))

        p("Sequences ({}):".format(len(self.sequences)))
        for i, seq in enumerate(self.sequences):
            p("  {}: {}".format(i, seq.name))
            p("    numKeyframes = {}".format(seq.numKeyframes))
            p("    duration = {}".format(seq.duration))
            p("    rotationMatters = {}".format("".join(map(str, map(int, seq.rotationMatters)))))
            p("    translationMatters = {}".format("".join(map(str, map(int, seq.translationMatters)))))
            p("    scaleMatters = {}".format("".join(map(str, map(int, seq.scaleMatters)))))

    def write_name(self, fd, name):
        write(fd, "<i", len(name))
        fd.write(name.encode("cp1252"))

    def write(self, fd, version=24):
        write(fd, "<i", version)

        write(fd, "<i", len(self.nodes))
        for node_name in self.nodes:
            self.write_name(fd, node_name)

        # don't pretend to support object export
        # not even TGE does
        write(fd, "<i", 0)

        write(fd, "<i", 0) # old_shape_num_objects

        # write all the node states for keyframes
        write(fd, "<i", len(self.rotations))
        for quat in self.rotations:
            write_quat(fd, quat)
        write(fd, "<i", len(self.translations))
        for vec in self.translations:
            write_vec(fd, vec)

        write(fd, "<i", len(self.uniform_scales))
        for scale in self.uniform_scales:
            write(fd, "<f", scale)
        write(fd, "<i", len(self.aligned_scales))
        for vec in self.aligned_scales:
            write_vec(fd, vec)

        assert len(self.arbitrary_scale_rots) == len(self.arbitrary_scale_factors)
        write(fd, "<i", len(self.arbitrary_scale_rots))
        for quat in self.arbitrary_scale_rots:
            write_quat(fd, quat)
        for vec in self.arbitrary_scale_factors:
            write_vec(fd, vec)

        assert len(self.ground_translations) == len(self.ground_rotations)
        write(fd, "<i", len(self.ground_translations))
        for vec in self.ground_translations:
            write_vec(fd, vec)
        for quat in self.ground_rotations:
            write_quat(fd, quat)

        # also legacy
        write(fd, "<i", 0)

        # actually write sequences
        write(fd, "<i", len(self.sequences))
        for seq in self.sequences:
            assert isinstance(seq.name, str)
            self.write_name(fd, seq.name)
            seq.write(fd, False) # don't write name index

        # now for triggers, apparently
        write(fd, "<i", len(self.triggers))
        for trigger in self.triggers:
            write(fd, "<i", trigger.state) # just a guess
            write(fd, "<f", trigger.pos)

    def read_name(self, fd):
        (size,) = read(fd, "<i")
        return fd.read(size).decode("cp1252")

    def read(self, fd):
        (version,) = read(fd, "<i")
        assert version <= 24, "dsq >v24 not supported yet"

        (num_nodes,) = read(fd, "<i")
        self.nodes = [self.read_name(fd) for i in range(num_nodes)]

        # Legacy data
        read(fd, "<i") # sz
        old_shape_num_objects = read(fd, "<i")

        if version < 17:
            assert false, "TODO: read keyframes from version < 17"

        if version > 21:
            self.rotations = [read_quat(fd) for i in range(read(fd, "<i")[0])]
            self.translations = [read_vec(fd) for i in range(read(fd, "<i")[0])]
            self.uniform_scales = [read(fd, "<f") for i in range(read(fd, "<i")[0])]
            self.aligned_scales = [read_vec(fd) for i in range(read(fd, "<i")[0])]
            (sz,) = read(fd, "<i")
            self.arbitrary_scale_rots = [read_quat(fd) for i in range(sz)]
            self.arbitrary_scale_factors = [read_vec(fd) for i in range(sz)]
            (sz,) = read(fd, "<i")
            self.ground_translations = [read_vec(fd) for i in range(sz)]
            self.ground_rotations = [read_quat(fd) for i in range(sz)]
        else:
            (sz,) = read(fd, "<i")
            self.rotations = [None] * sz
            self.translations = [None] * sz
            for i in range(sz):
                self.rotations[i] = read_quat(fd)
                self.translations[i] = read_vec(fd)

        # also legacy
        read(fd, "<i")

        # now read sequences
        (num_seqs,) = read(fd, "<i")
        self.sequences = [None] * num_seqs
        for i in range(num_seqs):
            name = self.read_name(fd)
            self.sequences[i] = Sequence.read(fd, False)
            self.sequences[i].name = name

        # and finally, triggers
        if version > 8:
            (num_sjws,) = read(fd, "<i")
            self.triggers = [None] * num_sjws
            for i in range(num_sjws):
                self.triggers[i] = Trigger(0, 0)
                self.triggers[i].state = read(fd, "<i")
                self.triggers[i].pos = read(fd, "<f")
