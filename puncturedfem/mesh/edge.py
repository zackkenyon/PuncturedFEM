import numpy as np
from .bounding_box import get_bounding_box
from .quad import quad
from .vert import vert

class NotParameterizedError(Exception):
	"""Exception raised if edges are not parameterized"""
	def __init__(self, cant_do='calling this method'):
		super().__init__()
		self.message = 'Must parameterize edges before ' + cant_do

class edge:
	"""Oriented edge in the plane"""

	anchor: vert
	endpnt: vert
	pos_cell_idx: int
	neg_cell_idx: int
	curve_type: str
	curve_opts: dict
	quad_type: str
	id: any
	is_on_mesh_boundary: bool
	is_loop: bool
	is_parameterized: bool
	num_pts: int
	x: np.ndarray
	unit_tangent: np.ndarray
	unit_normal: np.ndarray
	dx_norm: np.ndarray
	curvature: np.ndarray

	def __init__(self,
	      anchor: vert,
		  endpnt: vert,
		  pos_cell_idx: int=-1,
		  neg_cell_idx: int=-1,
		  curve_type: str='line',
		  quad_type: str='kress',
		  id=None,
		  **curve_opts) -> None:
		self.curve_type = curve_type
		self.quad_type = quad_type
		self.curve_opts = curve_opts
		self.set_id(id)
		self.set_verts(anchor, endpnt)
		self.set_cells(pos_cell_idx, neg_cell_idx)
		self.is_parameterized = False

	def __str__(self) -> str:
		# TODO
		msg = ''
		msg += f'id:         {self.id}\n'
		msg += f'curve_type: {self.curve_type}\n'
		msg += f'quad_type:  {self.quad_type}\n'
		msg += f'num_pts:    {self.num_pts}\n'
		return msg

	### MESH TOPOLOGY ##########################################################

	def set_id(self, id: any) -> None:
		if id is None:
			return
		if not isinstance(id, int):
			raise TypeError('id must be an integer')
		if id < 0:
			raise ValueError('id must be nonnegative')
		self.id = id

	def set_verts(self, anchor: int, endpnt: int) -> None:
		self.anchor = anchor
		self.endpnt = endpnt
		self.is_loop = self.anchor == self.endpnt

	def set_cells(self, pos_cell_idx: int, neg_cell_idx: int) -> None:
		# TODO this warning should only happen in planar_mesh
		# if pos_cell_idx < 0 and neg_cell_idx < 0:
		# 	raise ValueError(
		# 		'Edge must be boundary of at least one cell'
		# 	)
		self.pos_cell_idx = pos_cell_idx
		self.neg_cell_idx = neg_cell_idx
		self.is_on_mesh_boundary = \
			self.pos_cell_idx < 0 or self.neg_cell_idx < 0

	### PARAMETERIZATON ########################################################

	def parameterize(self, quad_dict: dict) -> None:

		q = quad_dict[self.quad_type]

		# 2 * n + 1 points sampled per edge
		self.num_pts = 2 * q.n + 1

		# retrieve function handles of parameterization and derivatives
		gamma = __import__(
            f'puncturedfem.mesh.edgelib.{self.curve_type}',
            fromlist=f'mesh.edgelib.{self.curve_type}'
        )

		# points on the boundary
		self.x = gamma._x(q.t, **self.curve_opts)

		# unweighted square norm of derivative
		dx = gamma._dx(q.t, **self.curve_opts)
		dx2 = dx[0,:] ** 2 + dx[1,:] ** 2

		# norm of derivative (with chainrule)
		self.dx_norm = np.sqrt(dx2) * q.wgt

		# unit tangent vector
		self.unit_tangent = dx / np.sqrt(dx2)

		# outward unit normal vector
		self.unit_normal = np.zeros((2, self.num_pts))
		self.unit_normal[0, :] = self.unit_tangent[1, :]
		self.unit_normal[1, :] = - self.unit_tangent[0, :]

		# signed curvature
		ddx = gamma._ddx(q.t, **self.curve_opts)
		self.curvature = (
			ddx[0, :] * self.unit_normal[0, :] +
			ddx[1, :] * self.unit_normal[1, :] ) / dx2

		# toggle parameterization flag
		self.is_parameterized = True

		# set endpoints
		if self.is_loop:
			self.translate(a=self.anchor)
		else:
			self.join_points(a=self.anchor, b=self.endpnt)

		# store parameterization type
		self.quad_type = q.type

	def deparameterize(self) -> None:
		self.num_pts = None
		self.x = None
		self.unit_tangent = None
		self.unit_normal = None
		self.dx_norm = None
		self.curvature = None
		self.is_parameterized = False

	def get_sampled_points(self) -> tuple[np.ndarray, np.ndarray]:
		return self.x[0, :], self.x[1, :]

	def get_bounding_box(self) -> tuple[float, float, float, float]:
		return get_bounding_box(x=self.x[0, :], y=self.x[1, :])

	### TRANSFORMATIONS ########################################################

	def reverse_orientation(self) -> None:
		"""
		Reverse the orientation of this edge using the reparameterization
		x(2 pi - t). The chain rule flips the sign of some derivative-based
		quanitites.
		"""

		# check if edge is parameterized
		if not self.is_parameterized:
			raise NotParameterizedError('reversing orientation')

		# vector quantities
		self.x = np.fliplr(self.x)
		self.unit_tangent = - np.fliplr(self.unit_tangent)
		self.unit_normal = - np.fliplr(self.unit_normal)

		# scalar quantities
		self.dx_norm = np.flip(self.dx_norm)
		self.curvature = - np.flip(self.curvature)

	def join_points(self, a: vert, b: vert) -> None:
		"""Join the points a to b with this edge."""

		# check if edge is parameterized
		if not self.is_parameterized:
			raise NotParameterizedError('joining points')

		# tolerance for floating point comparisons
		TOL = 1e-12

		# check that specified endpoints are distinct
		ab_norm = np.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2)
		if ab_norm < TOL:
			raise Exception('a and b must be distinct points')

		# check that endpoints of edge are distinct
		x = self.x[:, 0]
		y = self.x[:, self.num_pts-1]
		xy_norm = np.sqrt((x[0] - y[0]) ** 2 + (x[1] - y[1]) ** 2)
		if xy_norm < TOL:
			raise Exception('edge must have distinct endpoints')

		# anchor starting point to origin
		self.translate(vert(x=-x[0], y=-x[1]))

		# rotate
		theta = - np.arctan2(y[1] - x[1], y[0] - x[0])
		theta += np.arctan2(b.y - a.y, b.x - a.x)
		theta *= 180 / np.pi
		self.rotate(theta)

		# rescale
		alpha = ab_norm / xy_norm
		self.dialate(alpha)

		# anchor at point a
		self.translate(a)

		# set vertices
		self.set_verts(a, b)

	def translate(self, a: vert) -> None:
		"""Translate by a vector a"""

		# check if edge is parameterized
		if not self.is_parameterized:
			raise NotParameterizedError('translating')

		self.x[0,:] += a.x
		self.x[1,:] += a.y

	def dialate(self, alpha: float) -> None:
		"""Dialate by a scalar alpha"""

		# check if edge is parameterized
		if not self.is_parameterized:
			raise NotParameterizedError('dialating')

		# tolerance for floating point comparisons
		TOL = 1e-12

		if np.abs(alpha) < TOL:
			raise Exception('Dialation factor alpha must be nonzero')

		self.x *= alpha
		self.dx_norm *= np.abs(alpha)
		self.curvature *= 1 / alpha

	def rotate(self, theta: float) -> None:
		"""Rotate counterclockwise by theta (degrees)"""

		# check if edge is parameterized
		if not self.is_parameterized:
			raise NotParameterizedError('rotating')

		if theta % 360 == 0:
			return None

		c = np.cos(theta * np.pi / 180)
		s = np.sin(theta * np.pi / 180)
		R = np.array([ [c, -s], [s, c] ])

		self.apply_orthogonal_transformation(R)

	def reflect_across_x_axis(self) -> None:
		"""Reflect across the horizontal axis"""

		# check if edge is parameterized
		if not self.is_parameterized:
			raise NotParameterizedError('reflecting across x axis')

		A = np.array([ [1, 0], [0, -1] ])
		self.apply_orthogonal_transformation(A)

	def reflect_across_y_axis(self) -> None:
		"""Reflect across the vertical axis"""
		if not self.is_parameterized:
			raise NotParameterizedError('reflecting across y axis')

		A = np.array([ [-1, 0], [0, 1] ])
		self.apply_orthogonal_transformation(A)

	def apply_orthogonal_transformation(self, A) -> None:
		"""
		Transforms 2-dimensional space with the linear map
			x \mapsto A * x
		where A is a 2 by 2 orthogonal matrix, i.e. A^T * A = I

		It is important that A is orthogonal, since the first derivative norm
		as well as the curvature are invariant under such a transformation.
		"""

		# check if edge is parameterized
		if not self.is_parameterized:
			raise NotParameterizedError('applying orthogonal transformation')

		# tolerance for floating point comparisons
		TOL = 1e-12

		# safety checks
		msg = 'A must be a 2 by 2 orthogonal matrix'
		if np.shape(A) != (2,2):
			raise Exception(msg)
		if np.linalg.norm(np.transpose(A) @ A - np.eye(2)) > TOL:
			raise Exception(msg)

		# apply transformation to vector quantities
		self.x = A @ self.x
		self.unit_tangent = A @ self.unit_tangent
		self.unit_normal[0, :] = self.unit_tangent[1, :]
		self.unit_normal[1, :] = - self.unit_tangent[0, :]

		# determine if the sign of curvature has flipped
		a = A[0,0]
		b = A[0,1]
		c = A[1,0]
		d = A[1,1]
		if np.abs(b - c) < TOL and np.abs(a + d) < TOL:
			self.curvature *= -1

	### FUNCTION EVALUATION ####################################################

	def evaluate_function(self, fun: callable, ignore_endpoint=False):
		"""Return fun(x) for each sampled point on edge"""
		if not self.is_parameterized:
			raise NotParameterizedError('evaluating function')
		if ignore_endpoint:
			k = 1
		else:
			k = 0
		y = np.zeros((self.num_pts - k,))
		for i in range(self.num_pts - k):
			y[i] = fun(self.x[:, i])
		return y

	def multiply_by_dx_norm(self, vals, ignore_endpoint=True):
		"""
		Returns f multiplied against the norm of the derivative of
		the curve parameterization
		"""
		if not self.is_parameterized:
			raise NotParameterizedError('multiplying by dx_norm')
		msg = 'vals must be same length as boundary'
		if ignore_endpoint:
			if len(vals) != self.num_pts - 1:
				raise Exception(msg)
			return vals * self.dx_norm[:-1]
		else:
			if len(vals) != self.num_pts:
				raise Exception(msg)
			return vals * self.dx_norm

	def dot_with_tangent(self, v1, v2, ignore_endpoint=True):
		"""Returns the dot product (v1, v2) * unit_tangent"""
		if not self.is_parameterized:
			raise NotParameterizedError('dotting with tangent')
		if ignore_endpoint:
			k = 1
		else:
			k = 0
		if len(v1) != self.num_pts - k or len(v2) != self.num_pts - k:
			raise Exception('vals must be same length as boundary')
		return v1 * self.unit_tangent[0, :-k] + v2 * self.unit_tangent[1, :-k]

	def dot_with_normal(self, v1, v2, ignore_endpoint=True):
		"""Returns the dot product (v1, v2) * unit_normal"""
		if not self.is_parameterized:
			raise NotParameterizedError('dotting with normal')
		if ignore_endpoint:
			k = 1
		else:
			k = 0
		if len(v1) != self.num_pts - k or len(v2) != self.num_pts - k:
			raise Exception('vals must be same length as boundary')
		return v1 * self.unit_normal[0, :-k] + v2 * self.unit_normal[1, :-k]

	### INTEGRATION ############################################################

	def integrate_over_edge(self, vals, ignore_endpoint=False):
		"""Integrate vals * dx_norm over the edge via trapezoidal rule"""
		if not self.is_parameterized:
			raise NotParameterizedError('integrating over edge')
		vals_dx_norm = self.multiply_by_dx_norm(vals, ignore_endpoint)
		return self.integrate_over_edge_preweighted(
			vals_dx_norm, ignore_endpoint)

	def integrate_over_edge_preweighted(self,
				     vals_dx_norm,
					 ignore_endpoint=False):
		"""Integrate vals_dx_norm over the edge via trapezoidal rule"""
		if not self.is_parameterized:
			raise NotParameterizedError('integrating over edge')
		h = 2 * np.pi / (self.num_pts - 1)
		if ignore_endpoint:
			# left Riemann sum
			if len(vals_dx_norm) != self.num_pts - 1:
				raise Exception('vals must be same length as edge')
			res = np.sum(h * vals_dx_norm[:-1])
		else:
			# trapezoidal rule
			if len(vals_dx_norm) != self.num_pts:
				raise Exception('vals must be same length as edge')
			res = 0.5 * h * (vals_dx_norm[0] + vals_dx_norm[-1]) + \
				np.sum(h * vals_dx_norm[1:-1])
		return res