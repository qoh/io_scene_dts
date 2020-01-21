from struct import Struct, unpack_from, iter_unpack, calcsize
from io import IOBase
from ctypes import c_byte, c_short, c_int
from collections import namedtuple
from typing import List, Tuple, Set, Optional

DTS_VERSION_OLDEST = 19
DTS_VERSION_NEWEST = 28

StandardMeshType = 0
SkinMeshType = 1
DecalMeshType = 2
SortedMeshType = 3
NullMeshType = 4
MeshTypeMask = (
    StandardMeshType |
    SkinMeshType |
    DecalMeshType |
    SortedMeshType |
    NullMeshType)

Billboard = 1 << 31
HasDetailTexture = 1 << 30
BillboardZAxis = 1 << 29
UseEncodedNormals = 1 << 28
HasColor = 1 << 27
HasTVert2 = 1 << 26
MeshFlagMask = (
    Billboard |
    BillboardZAxis |
    HasDetailTexture |
    UseEncodedNormals |
    HasColor |
    HasTVert2)

PrimitiveTriangles = 0x00000000
PrimitiveStrip = 0x40000000
PrimitiveFan = 0x80000000
PrimitiveTypeMask = 0xC0000000
PrimitiveIndexed = 0x20000000
PrimitiveNoMaterial = 0x10000000
PrimitiveMaterialMask = 0x0FFFFFFF

Point2 = Tuple[float, float]
Point3 = Tuple[float, float, float]
Box = Tuple[Point3, Point3]

DtsQuat = namedtuple("DtsQuat", ("x", "y", "z", "w"))

def load_quat(data: Tuple[float, float, float, float]) -> DtsQuat:
    return DtsQuat(data[0] / 32767,
                   data[1] / 32767,
                   data[2] / 32767,
                   data[3] / 32767)

Node = namedtuple("Node", (
    "name_index",
    "parent_index",
    "first_object", # computed
    "first_child", # computed
    "next_sibling", # computed
))

Object = namedtuple("Object", (
    "name_index",
    "num_meshes",
    "start_mesh_index",
    "node_index",
    "next_sibling", # computed
    "first_decal", # deprecated
))

IflMaterial = namedtuple("IflMaterial", (
    "name_index",
    "slot",
    "first_frame", # computed
    "time", # computed
    "num_frames", # computed
))

Subshape = namedtuple("Subshape", (
    "first_node",
    "first_object",
    "first_decal",
    "num_nodes",
    "num_objects",
    "num_decals",
))

ObjectState = namedtuple("ObjectState", (
    "vis",
    "frame_index",
    "mat_frame_index",
))

Trigger = namedtuple("Trigger", ("state", "pos"))

Detail = namedtuple("Detail", (
    "name_index",
    "sub_shape_num",
    "object_detail_num",
    "size",
    "average_error", # *maybe* computed
    "max_error", # *maybe* computed
    "poly_count", # *maybe* computed
))

Primitive = namedtuple("Primitive", (
    "first_element",
    "num_elements",
    "type",
))

U32 = Struct("<I")
U8 = Struct("<B")

S32 = Struct("<i")
S16 = Struct("<h")
S8 = Struct("<b")

F32 = Struct("<f")

DtsPointData32 = Struct("<3f")
Point2fData = Struct("<2f")
DtsQuatData16 = Struct("<4h")

DtsVersionHeader = Struct("<hh")
DtsHeader = Struct("<III")

DtsBoundsData = Struct("<ff3f6f")

DtsNodeData = Struct("<5i")
DtsObjectData = Struct("<6i")
DtsIflMaterialData = Struct("<5i")
DtsObjectStateData = Struct("<fii")
DtsTriggerData = Struct("<If")
DtsDetailData = Struct("<iiifffi")

DtsDataMeshHeaderCommon = Struct("<iii6f3fi")
DtsDataMeshHeaderV27Ext = Struct("<iii")

def read_struct(f: IOBase, st: Struct) -> Tuple:
    return st.unpack_from(f.read(st.size))

def write_struct(f: IOBase, st: Struct, *args):
    f.write(st.pack(*args))

class DtsMemReader:
    mem32: bytes
    mem16: bytes
    mem8: bytes

    pos32: int
    pos16: int
    pos8: int

    expect_guard32: c_int
    expect_guard16: c_short
    expect_guard8: c_byte

    def __init__(self,
                 mem32: bytes,
                 mem16: bytes,
                 mem8: int,
                 ):
        assert len(mem32) % S32.size == 0
        assert len(mem16) % S16.size == 0
        self.mem32 = mem32
        self.mem16 = mem16
        self.mem8 = mem8
        self.pos32 = 0
        self.pos16 = 0
        self.pos8 = 0
        self.expect_guard32 = c_int(0)
        self.expect_guard16 = c_short(0)
        self.expect_guard8 = c_byte(0)

    def get32(self):
        (value,) = S32.unpack_from(self.mem32, self.pos32)
        self.pos32 += S32.size
        return value

    def get16(self):
        (value,) = S16.unpack_from(self.mem16, self.pos16)
        self.pos16 += S16.size
        return value

    def get8(self):
        value = self.mem8[self.pos8]
        self.pos8 += 1
        return value

    def get8n(self, num: int):
        values = self.mem8[self.pos8:self.pos8 + num]
        self.pos8 += num
        return values

    def struct32(self, st: Struct):
        assert st.size % S32.size == 0
        values = st.unpack_from(self.mem32, self.pos32)
        self.pos32 += st.size
        return values

    def struct16(self, st: Struct):
        assert st.size % S16.size == 0
        values = st.unpack_from(self.mem16, self.pos16)
        self.pos16 += st.size
        return values

    def struct32n(self, st: Struct, num: int):
        assert st.size % S32.size == 0
        end = self.pos32 + num * st.size
        data = st.iter_unpack(self.mem32[self.pos32:end])
        self.pos32 = end
        return data

    def struct16n(self, st: Struct, num: int):
        assert st.size % S16.size == 0
        end = self.pos16 + num * st.size
        data = st.iter_unpack(self.mem16[self.pos16:end])
        self.pos16 = end
        return data

    def string(self):
        for i in range(self.pos8, len(self.mem8)):
            if not self.mem8[i]:
                value = self.mem8[self.pos8:i].decode("cp1252")
                self.pos8 = i + 1
                return value
        raise Exception("EOF reading string in DTS data")

    def check_guard32(self):
        save_guard32 = self.get32()
        assert save_guard32 == self.expect_guard32.value, f"guard32 expected {self.expect_guard32}, got {save_guard32}"
        self.expect_guard32.value += 1

    def check_guard16(self):
        save_guard16 = self.get16()
        assert save_guard16 == self.expect_guard16.value, f"guard16 expected {self.expect_guard16}, got {save_guard16}"
        self.expect_guard16.value += 1

    def check_guard8(self):
        save_guard8 = self.get8()
        assert save_guard8 == self.expect_guard8.value, f"guard8 expected {self.expect_guard8}, got {save_guard8}"
        self.expect_guard8.value += 1

    def check_guard(self):
        self.check_guard32()
        self.check_guard16()
        self.check_guard8()

class DtsStreamWriter:
    buf32: bytearray
    buf16: bytearray
    buf8: bytearray

    guard32: c_int
    guard16: c_short
    guard8: c_byte

    def __init__(self):
        self.buf32 = bytearray()
        self.buf16 = bytearray()
        self.buf8 = bytearray()

        self.guard32 = c_int(0)
        self.guard16 = c_short(0)
        self.guard8 = c_byte(0)

    def finish(self, f: IOBase) -> bytearray:
        assert len(self.buf32) % 4 == 0
        assert len(self.buf16) % 2 == 0
        while len(self.buf16) % 4 != 0:
            self.buf16.append(0)
        while len(self.buf8) % 4 != 0:
            self.buf16.append(0)

        num32 = len(self.buf32) // 4
        num16 = len(self.buf16) // 4
        num8 = len(self.buf8) // 4

        end32 = num32
        end16 = end32 + num16
        end8 = end16 + num8

        start16 = end32
        start8 = end16

        write_struct(f, DtsHeader, end8, start16, start8)

        f.write(self.buf32)
        f.write(self.buf16)
        f.write(self.buf8)

    def guard(self):
        self.struct32(S32, self.guard32.value)
        self.struct16(S16, self.guard16.value)
        self.struct8(S8, self.guard8.value)
        self.guard32.value += 1
        self.guard16.value += 1
        self.guard8.value += 1

    def struct32(self, st: Struct, *values):
        assert len(st.size) % 4 == 0
        offset = len(self.buf32)
        self.buf32.extend(0 for _ in range(st.size))
        st.pack_into(self.buf32, offset, *values)

    def struct16(self, st: Struct, *values):
        assert len(st.size) % 2 == 0
        offset = len(self.buf16)
        self.buf16.extend(0 for _ in range(st.size))
        st.pack_into(self.buf16, offset, *values)

    def struct8(self, st: Struct, *values):
        offset = len(self.buf8)
        self.buf16.extend(0 for _ in range(st.size))
        st.pack_into(self.buf8, offset, *values)

class Mesh:
    type: int
    num_frames: int
    num_mat_frames: int
    parent_mesh: int
    bounds: Box
    center: Point3
    radius: float
    vert_offset: int
    m_num_verts: int
    vert_size: int
    verts: List[Point3]
    tverts: List[Point2]
    normals: List[Point3]
    encoded_normals: Optional[List[int]]
    primitives: List[Primitive]
    indices: List[int]
    verts_per_frame: int
    flags: int

class Sequence:
    name_index: int
    flags: int
    num_keyframes: int
    duration: float
    priority: int
    first_ground_frame: int
    num_ground_frames: int
    base_rotation: int
    base_translation: int
    base_scale: int
    base_object_state: int
    base_decal_state: int # Deprecated
    first_trigger: int
    num_triggers: int
    tool_begin: float
    rotation_matters: Set[int]
    translation_matters: Set[int]
    scale_matters: Set[int]
    # Deprecated: decal_matters
    # Deprecated: ifl_mat_matters
    vis_matters: Set[int]
    frame_matters: Set[int]
    mat_frame_matters: Set[int]

class Material:
    name: str
    flags: int
    reflectance_map: int
    bump_map: int
    detail_map: int
    detail_scale: float
    reflectance: float

class Shape:
    smallest_visible_size: float
    smallest_visible_dl: int
    radius: float
    tube_radius: float
    center: Point3
    bounds: Box
    nodes: List[Node]
    objects: List[Object]
    ifl_materials: List[IflMaterial]
    subshapes: List[Subshape]
    default_translations: List[Point3]
    default_rotations: List[DtsQuat]
    node_translations: List[Point3]
    node_rotations: List[DtsQuat]
    node_uniform_scales: List[float]
    node_aligned_scales: List[Point3]
    node_arbitrary_scale_factors: List[float]
    node_arbitrary_scale_rots: List[DtsQuat]
    ground_translations: List[Point3]
    ground_rotations: List[DtsQuat]
    object_states: List[ObjectState]
    triggers: List[Trigger]
    details: List[Detail]
    meshes: List[Mesh]
    names: List[str]
    sequences: List[Sequence]
    materials: List[Material]

def write_dts(f: IOBase,
              shape: Shape,
              version: int,
              exporter_version: int = 0):
    if version != 24:
        raise Exception(f"Writing DTS version {version} not supported")

    write_struct(f, DtsVersionHeader, version, exporter_version)

    w = DtsStreamWriter()
    write_dts_data(w, shape, version)
    w.finish(f)

    write_dts_sequences(f, shape, version)
    write_dts_materials(f, shape, version)

def read_dts(f: IOBase) -> Shape:
    version, exporter_version = read_struct(f, DtsVersionHeader)

    if version < DTS_VERSION_OLDEST or version > DTS_VERSION_NEWEST:
        raise Exception(f"Reading DTS version {version} not supported")

    (size_mem_buffer, start_u16, start_u8) = read_struct(f, DtsHeader)

    size_mem_buffer_bytes = S32.size * size_mem_buffer
    buffer = f.read(size_mem_buffer_bytes)

    mem32 = buffer[:S32.size * start_u16]
    mem16 = buffer[S32.size * start_u16:S32.size * start_u8]
    mem8 = buffer[S32.size * start_u8:]

    r = DtsMemReader(mem32, mem16, mem8)

    shape = Shape()

    read_dts_data(r, version, shape)
    read_dts_sequences(f, version, shape)
    read_dts_materials(f, version, shape)

    return shape

def write_dts_data(w: DtsStreamWriter, shape: Shape, version: int):
    raise NotImplementedError()

def write_dts_sequences(f: IOBase, shape: Shape, version: int):
    raise NotImplementedError()

def write_dts_materials(f: IOBase, shape: Shape, version: int):
    raise NotImplementedError()

def read_dts_data(r: DtsMemReader, version: int, shape: Shape):
    (
        num_nodes,
        num_objects,
        num_decals,
        num_subshapes,
        num_ifl_materials,
    ) = (
        r.get32(),
        r.get32(),
        r.get32(),
        r.get32(),
        r.get32(),
    )

    if version < 22:
        num_node_rots = r.get32() - num_nodes
        num_node_trans = num_node_rots
        num_node_uniform_scales = 0
        num_node_aligned_scales = 0
        num_node_arbitrary_scales = 0
    else:
        (
            num_node_rots,
            num_node_trans,
            num_node_uniform_scales,
            num_node_aligned_scales,
            num_node_arbitrary_scales,
        ) = (
            r.get32(),
            r.get32(),
            r.get32(),
            r.get32(),
            r.get32(),
        )

    if version > 23:
        num_ground_frames = r.get32()
    else:
        num_ground_frames = 0

    (
        num_object_states,
        num_decal_states,
        num_triggers,
        num_details,
        num_meshes,
    ) = (
        r.get32(),
        r.get32(),
        r.get32(),
        r.get32(),
        r.get32(),
    )

    if version < 23:
        num_skins = r.get32()
    else:
        num_skins = 0

    num_names = r.get32()

    shape.smallest_visible_size = r.get32() # TODO: Mystery value cast to F32?
    shape.smallest_visible_dl = r.get32()

    r.check_guard()

    # Bounds
    (
        radius,
        tube_radius,
        center_x,
        center_y,
        center_z,
        bounds_min_x,
        bounds_min_y,
        bounds_min_z,
        bounds_max_x,
        bounds_max_y,
        bounds_max_z,
    ) = r.struct32(DtsBoundsData)

    shape.radius = radius
    shape.tube_radius = tube_radius
    shape.center = (center_x, center_y, center_z)
    shape.bounds = (
        (bounds_min_x, bounds_min_y, bounds_min_z),
        (bounds_max_x, bounds_max_y, bounds_max_z))

    r.check_guard()

    # Nodes
    shape.nodes = list(map(Node._make, r.struct32n(DtsNodeData, num_nodes)))
    r.check_guard()

    # Objects
    # TODO: There's some weirdness with versions < 23 and skins around here
    shape.objects = list(map(Object._make, r.struct32n(DtsObjectData, num_objects)))
    r.check_guard()

    # Deprecated: Decals
    r.struct32(Struct(f"<{5 * num_decals}i")) # :thinking:
    r.check_guard()

    # IFL materials
    shape.ifl_materials = list(map(IflMaterial._make,
                             r.struct32n(DtsIflMaterialData, num_ifl_materials)))
    r.check_guard()

    # Subshapes
    subshapes_first_node = [r.get32() for _ in range(num_subshapes)]
    subshapes_first_object = [r.get32() for _ in range(num_subshapes)]
    subshapes_first_decal = [r.get32() for _ in range(num_subshapes)]
    r.check_guard()
    subshapes_num_nodes = [r.get32() for _ in range(num_subshapes)]
    subshapes_num_objects = [r.get32() for _ in range(num_subshapes)]
    subshapes_num_decals = [r.get32() for _ in range(num_subshapes)]
    r.check_guard()
    shape.subshapes = [Subshape(
        subshapes_first_node[i],
        subshapes_first_object[i],
        subshapes_first_decal[i],
        subshapes_num_nodes[i],
        subshapes_num_objects[i],
        subshapes_num_decals[i],
    ) for i in range(num_subshapes)]

    # Default translations and rotations
    shape.default_translations = [None] * num_nodes
    shape.default_rotations = [None] * num_nodes

    for i in range(num_nodes):
        shape.default_rotations[i] = load_quat(r.struct16(DtsQuatData16))
        shape.default_translations[i] = r.struct32(DtsPointData32)

    # Node sequence data stored in the shape
    shape.node_translations = list(r.struct32n(DtsPointData32, num_node_trans))
    shape.node_rotations = list(map(load_quat, r.struct16n(DtsQuatData16, num_node_rots)))

    if version > 21:
        shape.node_uniform_scales = list(map(lambda s: s[0], r.struct32n(F32, num_node_uniform_scales)))
        shape.node_aligned_scales = list(r.struct32n(DtsPointData32, num_node_aligned_scales))
        shape.node_arbitrary_scale_factors = list(r.struct32n(DtsPointData32, num_node_arbitrary_scales))
        shape.node_arbitrary_scale_rots = list(map(load_quat, r.struct16n(DtsQuatData16, num_node_arbitrary_scales)))
        r.check_guard()
    else:
        assert num_node_uniform_scales == 0
        assert num_node_aligned_scales == 0
        assert num_node_arbitrary_scales == 0
        shape.node_uniform_scales = []
        shape.node_aligned_scales = []
        shape.node_arbitrary_scale_factors = []
        shape.node_arbitrary_scale_rots = []

    if version > 23:
        shape.ground_translations = list(r.struct32n(DtsPointData32, num_ground_frames))
        shape.ground_rotations = list(map(load_quat, r.struct16n(DtsQuatData16, num_ground_frames)))
        r.check_guard()
    else:
        assert num_ground_frames == 0
        shape.ground_translations = []
        shape.ground_rotations = []

    r.check_guard() # TODO: This shouldn't be here! Why is it here?!

    # Object states
    shape.object_states = list(map(ObjectState._make,
                             r.struct32n(DtsObjectStateData, num_object_states)))
    r.check_guard()

    # Deprecated: Decal states
    r.struct32(Struct(f"<{num_decal_states}i")) # :thinking:
    r.check_guard()

    # Triggers
    shape.triggers = list(map(Trigger._make, r.struct32n(DtsTriggerData, num_triggers)))
    r.check_guard()

    # Detail levels
    shape.details = list(map(Detail._make, r.struct32n(DtsDetailData, num_details)))
    r.check_guard()

    if version >= 27:
        raise Exception("Unimplemented DTS version 27+ shape vertex data reading")

    # Meshes
    shape.meshes = [read_dts_mesh(r, version) for _ in range(num_meshes)]
    r.check_guard()

    # Names
    shape.names = [r.string() for _ in range(num_names)]
    r.check_guard()

    if version < 23:
        raise Exception("NYI: <v23 skin data reading")

        r.check_guard()

        r.check_guard()

def read_dts_mesh(r: DtsMemReader, version: int):
    mesh_type = r.get32()

    if mesh_type == StandardMeshType:
        mesh = read_dts_mesh_standard(r, version)
    elif mesh_type == NullMeshType:
        mesh = None
    else:
        raise Exception(f"Unsupported mesh type {mesh_type}")

    if mesh is not None:
        mesh.type = mesh_type

    return mesh

def read_dts_mesh_standard(r: DtsMemReader, version: int):
    mesh = Mesh()

    r.check_guard()

    (
        num_frames,
        num_mat_frames,
        parent_mesh,
        bounds_min_x,
        bounds_min_y,
        bounds_min_z,
        bounds_max_x,
        bounds_max_y,
        bounds_max_z,
        center_x,
        center_y,
        center_z,
        radius,
    ) = r.struct32(DtsDataMeshHeaderCommon)

    bounds = (
        (bounds_min_x, bounds_min_y, bounds_min_z),
        (bounds_max_x, bounds_max_y, bounds_max_z))
    center = (center_x, center_y, center_z)

    if version >= 27:
        (
            vert_offset,
            m_num_verts,
            vert_size,
        ) = r.struct32(DtsDataMeshHeaderV27Ext)
    else:
        (
            vert_offset,
            m_num_verts,
            vert_size,
        ) = (0, 0, 0)

    num_verts = r.get32()
    verts = list(r.struct32n(DtsPointData32, num_verts))
    num_tverts = r.get32()
    tverts = list(r.struct32n(Point2fData, num_tverts))

    if version > 25:
        num_tverts2 = r.get32()
        raise Exception("NYI: Read >v25 tverts2/colors")
        # read mTverts2

        num_vcolors = r.get32()
        # read mColors

    normals = list(r.struct32n(DtsPointData32, num_verts))

    if version > 21:
        encoded_normals = r.get8n(num_verts)
    else:
        encoded_normals = None

    if version > 25:
        # Mesh primitives (start, num_elements) are stored as 32-bit values
        raise Exception("NYI: Read >v25 mesh primitives")
    else:
        # Mesh primitives (start, num_elements) are stored as 16-bit values
        primitives = [read_dts_mesh_primitive(r, version) for _ in range(r.get32())]
        indices = [r.get16() for _ in range(r.get32())]
        # read
        pass

    # Deprecated: Merge indices
    _merge_indices = [r.get16() for _ in range(r.get32())]

    verts_per_frame = r.get32()
    flags = r.get32()

    if False: # if mEncodedNorms.size()
        flags |= UseEncodedNormals

    if version < 27:
        # if (mColors.size() > 0) setFlags(HasColor)
        # if (mTverts2.size() > 0) setFlags(HasTVert2)
        # mNumVerts = mVerts.size()
        pass

    r.check_guard()

    mesh.num_frames = num_frames
    mesh.num_mat_frames = num_mat_frames
    mesh.parent_mesh = parent_mesh
    mesh.bounds = bounds
    mesh.center = center
    mesh.radius = radius
    mesh.vert_offset = vert_offset
    mesh.m_num_verts = m_num_verts
    mesh.vert_size = vert_size
    mesh.verts = verts
    mesh.tverts = tverts
    mesh.normals = normals
    mesh.encoded_normals = encoded_normals
    mesh.primitives = primitives
    mesh.indices = indices
    mesh.verts_per_frame = verts_per_frame
    mesh.flags = flags

    return mesh

def read_dts_mesh_primitive(r: DtsMemReader, version: int):
    return Primitive(
        r.get16(),
        r.get16(),
        r.get32())

def read_dts_sequences(f: IOBase, version: int, shape: Shape):
    (num_sequences,) = read_struct(f, S32)
    shape.sequences = [read_dts_sequence(f, version, True) for _ in range(num_sequences)]

def read_dts_sequence(f: IOBase, version: int, read_name_index: bool):
    seq = Sequence()

    if read_name_index:
        (seq.name_index,) = read_struct(f, S32)
    else:
        seq.name_index = -1

    if version > 21:
        (seq.flags,) = read_struct(f, U32)
    else:
        seq.flags = 0

    (seq.num_keyframes,) = read_struct(f, S32)
    (seq.duration,) = read_struct(f, F32)

    if version < 22:
        # TODO: Verify that U8 is the correct type for `Stream::read(&bool)`.
        if read_struct(f, U8)[0]:
            seq.flags |= SeqBlend
        if read_struct(f, U8)[0]:
            seq.flags |= SeqCyclic
        if read_struct(f, U8)[0]:
            seq.flags |= SeqMakePath

    (seq.priority,) = read_struct(f, S32)
    (seq.first_ground_frame,) = read_struct(f, S32)
    (seq.num_ground_frames,) = read_struct(f, S32)

    if version > 21:
        (seq.base_rotation,) = read_struct(f, S32)
        (seq.base_translation,) = read_struct(f, S32)
        (seq.base_scale,) = read_struct(f, S32)
        (seq.base_object_state,) = read_struct(f, S32)
        (seq.base_decal_state,) = read_struct(f, S32)
    else:
        (seq.base_rotation,) = read_struct(f, S32)
        seq.base_translation = seq.base_rotation
        seq.base_scale = -1
        (seq.base_object_state,) = read_struct(f, S32)
        (seq.base_decal_state,) = read_struct(f, S32)

    (seq.first_trigger,) = read_struct(f, S32)
    (seq.num_triggers,) = read_struct(f, S32)
    (seq.tool_begin,) = read_struct(f, F32)
    seq.rotation_matters = read_int_set(f)
    if version < 22:
        seq.translation_matters = seq.rotation_matters
        seq.scale_matters = set()
    else:
        seq.translation_matters = read_int_set(f)
        seq.scale_matters = read_int_set(f)

    read_int_set(f) # Deprecated: Decals
    read_int_set(f) # Deprecated: IFL materials

    seq.vis_matters = read_int_set(f)
    seq.frame_matters = read_int_set(f)
    seq.mat_frame_matters = read_int_set(f)

    return seq

def read_int_set(f: IOBase) -> Set[int]:
    read_struct(f, S32) # Deprecated: Cardinality of ints (now usually 0)
    (words,) = read_struct(f, S32) # Number of words representing ints
    ints = set()

    for i, (word,) in enumerate(S32.iter_unpack(f.read(words * S32.size))):
        for j in range(32):
            if (word & (1 << j)) != 0:
                ints.add((i << 5) | j)

    return ints

def read_dts_materials(f: IOBase, version: int, shape: Shape):
    (material_type,) = read_struct(f, S8)
    assert material_type == 1

    (num_materials,) = read_struct(f, S32)

    shape.materials = [Material() for _ in range(num_materials)]

    if version >= 26:
        name_length_struct = S32
    else:
        name_length_struct = U8

    for material in shape.materials:
        (length,) = read_struct(f, name_length_struct)
        material.name = f.read(length).decode("cp1252")
    for material in shape.materials:
        (material.flags,) = read_struct(f, U32)
    for material in shape.materials:
        (material.reflectance_map,) = read_struct(f, S32)
    for material in shape.materials:
        (material.bump_map,) = read_struct(f, S32)
    for material in shape.materials:
        (material.detail_map,) = read_struct(f, S32)

    if version == 25:
        f.read(4 * num_materials) # TODO: question mark

    for material in shape.materials:
        (material.detail_scale,) = read_struct(f, F32)
    for material in shape.materials:
        (material.reflectance,) = read_struct(f, F32)

if __name__ == "__main__":
    import sys
    file = sys.argv[1]
    with open(file, "rb") as f:
        shape = read_dts(f)
