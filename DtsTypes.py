from collections import namedtuple
from struct import pack, unpack
from enum import Enum

Point3D = namedtuple("Point3D", "x y z")
Point2D = namedtuple("Point2D", "x y")
Point = Point3D
Box = namedtuple("Box", "min max")
Quaternion = namedtuple("Quaternion", "x y z w")

class Node(object):
	def __init__(self, name, parent, firstObject=-1, child=-1, sibling=-1):
		self.name = name
		self.parent = parent
		self.firstObject = firstObject
		self.child = child
		self.sibling = sibling

	def write(self, stream):
		stream.write32(
			self.name, self.parent,
			self.firstObject, self.child, self.sibling)

	@classmethod
	def read(cls, stream):
		return cls(
			stream.read32(), stream.read32(),
			stream.read32(), stream.read32(), stream.read32())

class Object(object):
	def __init__(self, name, numMeshes, firstMesh, node, sibling=-1, firstDecal=-1):
		self.name = name
		self.numMeshes = numMeshes
		self.firstMesh = firstMesh
		self.node = node
		self.sibling = sibling
		self.firstDecal = firstDecal

	def write(self, stream):
		stream.write32(
			self.name, self.numMeshes, self.firstMesh,
			self.node, self.sibling, self.firstDecal)

	@classmethod
	def read(cls, stream):
		return cls(
			stream.read32(), stream.read32(), stream.read32(),
			stream.read32(), stream.read32(), stream.read32())

class IflMaterial(object):
	def __init__(self, name, slot, firstFrame, time, numFrames):
		self.name = name
		self.slot = slot
		self.firstFrame = firstFrame
		self.time = time
		self.numFrames = numFrames

	def write(self, stream):
		self.write32(
			self.name, self.slot, self.firstFrame,
			self.time, self.numFrames)

	@classmethod
	def read(cls, stream):
		return cls(
			stream.read32(), stream.read32(),
			stream.read32(), stream.read32(), stream.read32())

class Subshape(object):
	def __init__(self, firstNode, firstObject, firstDecal, numNodes, numObjects, numDecals):
		self.firstNode = firstNode
		self.firstObject = firstObject
		self.firstDecal = firstDecal
		self.numNodes = numNodes
		self.numObjects = numObjects
		self.numDecals = numDecals

class ObjectState(object):
	def __init__(self, vis, frame, matFrame):
		self.vis = vis
		self.frame = frame
		self.matFrame = matFrame

	def write(self, stream):
		stream.write32(self.vis, self.frame, self.matFrame)

	@classmethod
	def read(cls, stream):
		return cls(stream.read32(), stream.read32(), stream.read32())

class Trigger(object):
	def __init__(self, state, pos):
		self.state = state
		self.pos = pos

	def write(self, stream):
		stream.write32(self.state)
		stream.write_float(self.pos)

	@classmethod
	def read(cls, stream):
		return cls(stream.read32(), stream.read_float())

class DetailLevel(object):
	def __init__(self, name, subshape, objectDetail, size, avgError, maxError, polyCount):
		self.name = name
		self.subshape = subshape
		self.objectDetail = objectDetail
		self.size = size
		self.avgError = avgError
		self.maxError = maxError
		self.polyCount = polyCount

	def write(self, stream):
		stream.write32(self.name, self.subshape, self.objectDetail)
		stream.write_float(self.size, self.avgError, self.maxError)
		stream.write32(self.polyCount)

	@classmethod
	def read(cls, stream):
		return cls(
			stream.read32(), stream.read32(), stream.read32(),
			stream.read_float(), stream.read_float(), stream.read_float(),
			stream.read32())

class Primitive(object):
	Triangles = 0x00000000
	Strip = 0x40000000
	Fan = 0x80000000
	TypeMask = 0xC0000000
	Indexed = 0x20000000
	NoMaterial = 0x10000000
	MaterialMask = 0x0FFFFFFF

	def __init__(self, firstElement, numElements, type):
		self.firstElement = firstElement
		self.numElements = numElements
		self.type = type

	def write(self, stream):
		stream.write16(self.firstElement, self.numElements)
		stream.write32(self.type)

	@classmethod
	def read(cls, stream):
		return cls(stream.read16(), stream.read16(), stream.read32())

class MeshType(Enum):
	Standard = 0
	Skin = 1
	Decal = 2
	Sorted = 3
	Null = 4

class Mesh(object):
	def __init__(self, type=MeshType.Standard):
		self.bounds = Box(Point(0, 0, 0), Point(0, 0, 0))
		self.center = Point(0, 0, 0)
		self.radius = 0
		self.numFrames = 1
		self.matFrames = 1
		self.vertsPerFrame = 0
		self.parent = -1
		self.flags = 0
		self.type = type
		self.verts = []
		self.tverts = []
		self.normals = []
		self.enormals = []
		self.primitives = []
		self.indices = []
		self.mindices = []

	def write(self, stream):
		stream.write32(self.type.value)

		if self.type is MeshType.Null:
			return

		stream.guard()
		stream.write32(self.numFrames, self.matFrames, self.parent)
		stream.write_box(self.bounds)
		stream.write_point(self.center)
		strema.write_float(self.radius)

		# Geometry data
		stream.write32(len(self.verts))
		for vert in self.verts:
			stream.write_point(vert)
		stream.write32(len(self.tverts))
		for tvert in self.tverts:
			stream.write_point2d(tvert)

		assert len(self.normals) == len(self.verts)
		assert len(self.enormals) == len(self.verts)
		for normal in self.normals:
			stream.write_point(vert)
		for enormal in self.enormals:
			stream.write8(enormal)

		# Primitives and other stuff
		stream.write32(len(self.primitives))
		for prim in self.primitives:
			prim.write(stream)

		#if stream.dtsVersion >= 25:
		stream.write32(len(self.indices))
		stream.write16(*self.indices)
		stream.write32(len(self.mindices))
		stream.write16(*self.mindices)
		stream.write32(self.vertsPerFrame, self.flags)
		stream.guard()

	@classmethod
	def read(cls, stream):
		type = MeshType(stream.read32())
		mesh = cls(type)

		if type is MeshType.Null:
			return mesh

		stream.guard()

		mesh.numFrames = stream.read32()
		mesh.matFrames = stream.read32()
		mesh.parent = stream.read32()
		mesh.bounds = stream.read_box()
		mesh.center = stream.read_point()
		mesh.radius = stream.read_float()

		# Geometry data
		n_vert = stream.read32()
		mesh.verts = [stream.read_point() for i in range(n_vert)]
		n_tvert = stream.read32()
		mesh.tverts = [stream.read_point2d() for i in range(n_tvert)]
		mesh.normals = [stream.read_point() for i in range(n_vert)]
		mesh.enormals = [stream.read8() for i in range(n_vert)]

		# Primitives and other stuff
		mesh.primitives = [Primitive.read(stream) for i in range(stream.read32())]
		if stream.dtsVersion >= 25:
			mesh.indices = [stream.read16() for i in range(stream.read32())]
		else:
			mesh.indices = [stream.read16() for i in range(stream.read32())]
		mesh.mindices = [stream.read16() for i in range(stream.read32())]
		mesh.vertsPerFrame = stream.read32()
		mesh.flags = stream.read32()
		stream.guard()

		return mesh

class Material(object):
	def __init__(self, name="", flags=0,
		reflectanceMap=-1, bumpMap=-1, detailMap=-1,
		detailScale=1.0, reflectance=0.0):
		self.name = name
		self.flags = flags
		self.reflectanceMap = reflectanceMap
		self.bumpMap = bumpMap
		self.detailMap = detailMap
		self.detailScale = detailScale
		self.reflectance = reflectance
