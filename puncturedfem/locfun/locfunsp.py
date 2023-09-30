"""
locfunsp.py
===========

Module containing the locfunspace class, which is used to represent a basis of
a basis of the local Poisson space V_p(K) on a mesh cell K.
"""

from tqdm import tqdm

from ..mesh.cell import cell
from ..solver.globkey import global_key
from .edge_space import edge_space
from .locfun import locfun, polynomial
from .nystrom import nystrom_solver


class locfunspace:
    """
    A collection of local functions (locfun objects) that form a basis of the
    local Poisson space V_p(K). The locfuns are partitioned into three types:
            vert_funs: vertex functions (harmonic, trace supported on two edges)
            edge_funs: edge functions (harmonic, trace supported on one edge)
            bubb_funs: bubble functions (polynomial Laplacian, zero trace)
    In the case where the mesh cell K has a vertex-free edge (that is, the edge
    is a simple closed contour, e.g. a circle), no vertex functions are
    associated with that edge.
    """

    deg: int
    num_vert_funs: int
    num_edge_funs: int
    num_bubb_funs: int
    num_funs: int
    vert_funs: list[locfun]
    edge_funs: list[locfun]
    bubb_funs: list[locfun]
    solver: nystrom_solver

    def __init__(
        self,
        K: cell,
        edge_spaces: list[edge_space],
        deg: int = 1,
        verbose: bool = True,
        processes: int = 1,
    ) -> None:
        """
        Initialize locfunspace object for a given cell K and the edge spaces,
        which is a list of edge_space objects for each edge in K, in the order
        that the edges appear in K.edges. The edge spaces must be computed
        before the locfunspace object is initialized. This initialization
        computes all function metadata (e.g. traces, interior values) and
        and interior values.

        Parameters
        ----------
        K : cell
            Mesh cell
        edge_spaces : list[edge_space]
            List of edge_space objects for each edge in K
        deg : int, optional
            (DEPRECATED) Degree of polynomial space, by default 1
        verbose : bool, optional
            Print progress, by default True
        processes : int, optional
            Number of processes to use for parallel computation, by default 1
        """

        # set up nyström solver
        self.solver = nystrom_solver(K, verbose=verbose)

        # set degree of polynomial space
        self.set_deg(deg)

        # bubble functions: zero trace, polynomial Laplacian
        self.build_bubble_funs()

        # build vertex functions...')
        self.build_vert_funs(edge_spaces)

        # build edge functions
        self.build_edge_funs(edge_spaces)

        # count number of each type of function
        self.compute_num_funs()

        # compute all function metadata
        self.compute_all(verbose=verbose, processes=processes)

        # find interior values
        self.find_interior_values(verbose=verbose)

    def set_deg(self, deg: int) -> None:
        """
        Set degree of polynomial space
        """
        if not isinstance(deg, int):
            raise TypeError("deg must be an integer")
        if deg < 1:
            raise ValueError("deg must be a positive integer")
        self.deg = deg

    def find_interior_values(self, verbose: bool = True) -> None:
        """
        Equivalent to running v.compute_interior_values() for each locfun v
        """
        if verbose:
            print("Finding interior values...")
            for v in tqdm(self.get_basis()):
                v.compute_interior_values()
        else:
            for v in self.get_basis():
                v.compute_interior_values()

    # BUILD FUNCTIONS ########################################################

    def compute_num_funs(self) -> None:
        """
        Sum the number of vertex, edge, and bubble functions
        """
        self.num_vert_funs = len(self.vert_funs)
        self.num_edge_funs = len(self.edge_funs)
        self.num_bubb_funs = len(self.bubb_funs)
        self.num_funs = (
            self.num_vert_funs + self.num_edge_funs + self.num_bubb_funs
        )

    def compute_all(self, verbose: bool = True, processes: int = 1) -> None:
        """
        Equivalent to running v.compute_all(K) for each locfun v.
        """
        if processes == 1:
            self.compute_all_sequential(verbose=verbose)
        elif processes > 1:
            self.compute_all_parallel(verbose=verbose, processes=processes)
        else:
            raise ValueError("processes must be a positive integer")

    def compute_all_sequential(self, verbose: bool = True) -> None:
        """
        Equivalent to running v.compute_all(K) for each locfun v.
        """
        if verbose:
            print("Computing function metadata...")
            for v in tqdm(self.get_basis()):
                v.compute_all()
        else:
            for v in self.get_basis():
                v.compute_all()

    def compute_all_parallel(
        self, verbose: bool = True, processes: int = 1
    ) -> None:
        """
        Equivalent to running v.compute_all(K) for each locfun v, using
        multiprocessing to parallelize computation.
        """
        raise NotImplementedError("Parallel computation not yet implemented")

    def build_bubble_funs(self) -> None:
        """Construct bubble functions"""
        # bubble functions
        num_bubb = (self.deg * (self.deg - 1)) // 2
        self.bubb_funs = []
        for k in range(num_bubb):
            v_key = global_key(fun_type="bubb", bubb_space_idx=k)
            v = locfun(solver=self.solver, key=v_key)
            p = polynomial()
            p.add_monomial_with_idx(coef=1.0, idx=k)
            v.set_laplacian_polynomial(p)
            self.bubb_funs.append(v)

    def build_vert_funs(self, edge_spaces: list[edge_space]) -> None:
        """Construct vertex functions from edge spaces"""

        # find all vertices on cell
        vert_idx_set = set()
        for c in self.solver.K.components:
            for e in c.edges:
                if not e.is_loop:
                    vert_idx_set.add(e.anchor.idx)
                    vert_idx_set.add(e.endpnt.idx)
        vert_keys: list[global_key] = []
        for vert_idx in vert_idx_set:
            vert_keys.append(global_key(fun_type="vert", vert_idx=vert_idx))

        # initialize list of vertex functions and set traces
        self.vert_funs = []
        for vert_key in vert_keys:
            v = locfun(solver=self.solver, key=vert_key)
            for j, b in enumerate(edge_spaces):
                for k in range(b.num_vert_funs):
                    if b.vert_fun_global_keys[k].vert_idx == vert_key.vert_idx:
                        v.poly_trace.polys[j] = b.vert_fun_traces[k]
            self.vert_funs.append(v)

    def build_edge_funs(self, edge_spaces: list[edge_space]) -> None:
        """Construct edge functions from edge spaces"""

        # initialize list of edge functions
        self.edge_funs = []

        # loop over edges on cell
        for b in edge_spaces:
            # locate edge within cell
            glob_edge_idx = b.e.idx
            glob_edge_idx_list = [e.idx for e in self.solver.K.get_edges()]
            edge_idx = glob_edge_idx_list.index(glob_edge_idx)

            # loop over edge functions
            for k in range(b.num_edge_funs):
                v_trace = b.edge_fun_traces[k]

                # create harmonic locfun
                v = locfun(solver=self.solver, key=b.edge_fun_global_keys[k])

                # set Dirichlet data
                v.poly_trace.polys[edge_idx] = v_trace

                # add to list of edge functions
                self.edge_funs.append(v)

    def get_basis(self) -> list[locfun]:
        """Return list of all functions"""
        return self.vert_funs + self.edge_funs + self.bubb_funs
