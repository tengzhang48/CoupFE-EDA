"""Hex8 meshing via **gmsh** (not a hand-rolled generator) + the glue to our compiled element.

We do NOT write our own mesh generator. gmsh (the standard open-source mesher) builds the
geometry with its OpenCASCADE kernel and produces an **all-hexahedral** mesh via its subdivision
algorithm (`Mesh.SubdivisionAlgorithm = 2`) for the generated device solids defined here. Arbitrary
imported CAD should use the Tet4 path unless separately qualified. This module is only the thin
glue: drive gmsh, pull (coords, hex-connectivity) in our Hex8
node order (checked by signed Jacobian > 0, no remap), and classify boundary nodes by
the OCC surface they live on (for BCs). Multi-material solids tag volumes -> a per-element
material id.

Requires `gmsh` + `meshio` in the venv (`pip install gmsh meshio`).
"""
from __future__ import annotations

import math

import numpy as np


def _occ_tol(scale):
    """Bounding-box tolerance covering OCC's ~1e-7 absolute surface extent."""
    return max(1e-6, 1e-4 * abs(float(scale)))


def _node_table(gmsh):
    """All mesh nodes as coords[nn,3], plus a tag->row-index map (max tag + 1)."""
    ntags, nc, _ = gmsh.model.mesh.getNodes()
    nc = nc.reshape(-1, 3)
    order = np.argsort(ntags)
    tags_sorted = ntags[order]
    inv = np.full(int(ntags.max()) + 1, -1, dtype=np.int64)
    inv[tags_sorted] = np.arange(len(ntags))
    return nc[order], inv


def _hex_elements(gmsh, inv):
    """0-based Hex8 connectivity (gmsh element type 5), remapped through `inv`."""
    et, _, en = gmsh.model.mesh.getElements(dim=3)
    conn = np.concatenate([n.reshape(-1, 8) for e, n in zip(et, en) if e == 5], axis=0)
    return inv[conn]


def _surface_nodes(gmsh, inv, predicate, surface_tags=None):
    """Indices of nodes lying on any OCC surface whose bounding box satisfies predicate(bb)."""
    idx = []
    entities = (gmsh.model.getEntities(2) if surface_tags is None
                else [(2, int(tag)) for tag in surface_tags])
    for dim, tag in entities:
        bb = gmsh.model.getBoundingBox(dim, tag)          # xmin,ymin,zmin,xmax,ymax,zmax
        if predicate(bb):
            nt, _, _ = gmsh.model.mesh.getNodes(dim, tag, includeBoundary=True)
            if len(nt):
                mapped = inv[nt.astype(np.int64)]
                mapped = mapped[mapped >= 0]
                if len(mapped):
                    idx.append(mapped)
    return np.unique(np.concatenate(idx)) if idx else np.array([], dtype=np.int64)


def min_signed_jacobian(coords, elems):
    """Min Hex8 trilinear signed Jacobian (at the element center) over the mesh.

    >0 everywhere == valid, correctly-oriented mesh in our node convention. A robustness
    self-check to run on every generated mesh.
    """
    xi = np.array([[-1, -1, -1], [1, -1, -1], [1, 1, -1], [-1, 1, -1],
                   [-1, -1, 1], [1, -1, 1], [1, 1, 1], [-1, 1, 1]], float)
    dN = 0.125 * xi                                       # dN_i/dxi_j at center
    J = np.einsum('ij,ejk->eik', dN.T, coords[elems])     # (ne,3,3)
    return float(np.linalg.det(J).min())


def _volume_hexes(gmsh, inv, tag):
    """0-based Hex8 connectivity for a single volume entity `tag`."""
    et, _, en = gmsh.model.mesh.getElements(dim=3, tag=tag)
    blocks = [n.reshape(-1, 8) for e, n in zip(et, en) if e == 5]
    if not blocks:
        return np.zeros((0, 8), dtype=np.int64)
    return inv[np.concatenate(blocks, axis=0)]


def _hex_volume_mesh(gmsh, tag):
    """Coordinates/connectivity for one volume, excluding orphan CAD-entity mesh nodes."""
    coords, regions, inv = _hex_region_mesh(gmsh, {"volume": [tag]})
    return coords, regions["volume"], inv


def _hex_region_mesh(gmsh, region_tags):
    """One connected node table plus Hex8 arrays for named groups of OCC volume tags."""
    raw = {}
    for name, tags in region_tags.items():
        blocks = []
        for tag in tags:
            et, _, en = gmsh.model.mesh.getElements(dim=3, tag=int(tag))
            blocks.extend(n.reshape(-1, 8) for e, n in zip(et, en) if e == 5)
        if not blocks:
            raise RuntimeError(f"region {name!r} produced no Hex8 elements")
        raw[name] = np.concatenate(blocks, axis=0).astype(np.int64)
    used_tags = np.unique(np.concatenate(list(raw.values()), axis=0))
    all_coords, all_inv = _node_table(gmsh)
    coords = all_coords[all_inv[used_tags]]
    inv = np.full(int(used_tags.max()) + 1, -1, dtype=np.int64)
    inv[used_tags] = np.arange(len(used_tags))
    regions = {name: inv[conn] for name, conn in raw.items()}
    return coords, regions, inv


def _add_solder_profile_occ(gmsh, R_pad, R_mid, L):
    """Add a revolved solder solid to the active OCC model; return its volume and source surface."""
    axis0 = gmsh.model.occ.addPoint(0.0, 0.0, 0.0)
    outer0 = gmsh.model.occ.addPoint(R_pad, 0.0, 0.0)
    outerm = gmsh.model.occ.addPoint(R_mid, 0.0, 0.5 * L)
    outerL = gmsh.model.occ.addPoint(R_pad, 0.0, L)
    axisL = gmsh.model.occ.addPoint(0.0, 0.0, L)
    bottom = gmsh.model.occ.addLine(axis0, outer0)
    profile = gmsh.model.occ.addSpline([outer0, outerm, outerL])
    top = gmsh.model.occ.addLine(outerL, axisL)
    axis = gmsh.model.occ.addLine(axisL, axis0)
    wire = gmsh.model.occ.addWire([bottom, profile, top, axis])
    meridian = gmsh.model.occ.addPlaneSurface([wire])
    revolved = gmsh.model.occ.revolve(
        [(2, meridian)], 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 2.0 * math.pi
    )
    volume_tags = [tag for dim, tag in revolved if dim == 3]
    if len(volume_tags) != 1:
        raise RuntimeError(f"expected one solder volume, got {volume_tags}")
    return volume_tags[0], meridian


def via_annulus(a=0.5, b=1.0, L=1.0, h=0.12):
    """gmsh all-hex mesh of a CONCENTRIC two-material via: inner core r<a, outer annulus a<r<b.

    The two solids are `fragment`-ed so they share a conformal interface at r=a. Returns
    dict(coords, core, annulus, cap0, capL, outer) -- `core`/`annulus` are per-material Hex8
    connectivity (-> one ElementGroup each); `outer` is the lateral wall r=b (the heat sink).
    """
    import gmsh
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("annular_via")
        outer = gmsh.model.occ.addCylinder(0, 0, 0, 0, 0, L, b)
        inner = gmsh.model.occ.addCylinder(0, 0, 0, 0, 0, L, a)
        gmsh.model.occ.fragment([(3, outer)], [(3, inner)])   # conformal interface at r=a
        gmsh.model.occ.synchronize()
        gmsh.option.setNumber("Mesh.MeshSizeMax", h)
        gmsh.option.setNumber("Mesh.SubdivisionAlgorithm", 2)
        gmsh.model.mesh.generate(3)
        coords, inv = _node_table(gmsh)
        # classify the two volumes: the core's bounding box reaches only +/-a, the annulus +/-b
        vols = gmsh.model.getEntities(3)
        xext = {tag: gmsh.model.getBoundingBox(3, tag)[3] for _, tag in vols}   # xmax
        core_tag = min(xext, key=xext.get)
        core = _volume_hexes(gmsh, inv, core_tag)
        annulus = np.concatenate([_volume_hexes(gmsh, inv, t) for _, t in vols if t != core_tag])
        tol = _occ_tol(L)
        flat = lambda bb: abs(bb[5] - bb[2]) < tol
        cap0 = _surface_nodes(gmsh, inv, lambda bb: flat(bb) and abs(bb[2]) < tol)
        capL = _surface_nodes(gmsh, inv, lambda bb: flat(bb) and abs(bb[2] - L) < tol)
        # outer wall = curved surface whose bbox reaches r=b (NOT the r=a interface)
        outer = _surface_nodes(gmsh, inv, lambda bb: not flat(bb) and bb[3] > 0.5 * (a + b))
    finally:
        gmsh.finalize()
    return dict(coords=coords, core=core, annulus=annulus, cap0=cap0, capL=capL, outer=outer)


def layer_stack(thicknesses, W=1.0, h=0.12):
    """gmsh all-hex mesh of a vertical STACK of slabs (die/underfill/solder/substrate ...).

    `thicknesses` is the per-layer z-thickness list; the W x W boxes are `fragment`-ed so adjacent
    layers share a conformal interface. Returns dict(coords, layers, bottom, top, H, bounds):
    `layers[i]` is layer i's Hex8 connectivity (-> one ElementGroup each); `bottom`/`top` are the
    z=0 / z=H face node sets.
    """
    import gmsh
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("stack")
        z0 = 0.0; boxes = []; bounds = [0.0]
        for t in thicknesses:
            boxes.append(gmsh.model.occ.addBox(0, 0, z0, W, W, t)); z0 += t; bounds.append(z0)
        H = z0
        if len(boxes) > 1:
            gmsh.model.occ.fragment([(3, boxes[0])], [(3, b) for b in boxes[1:]])
        gmsh.model.occ.synchronize()
        gmsh.option.setNumber("Mesh.MeshSizeMax", h)
        gmsh.option.setNumber("Mesh.SubdivisionAlgorithm", 2)
        gmsh.model.mesh.generate(3)
        coords, inv = _node_table(gmsh)
        centers = [0.5 * (bounds[i] + bounds[i + 1]) for i in range(len(thicknesses))]
        buckets = [[] for _ in thicknesses]
        for _, tag in gmsh.model.getEntities(3):
            bb = gmsh.model.getBoundingBox(3, tag); zc = 0.5 * (bb[2] + bb[5])
            buckets[int(np.argmin([abs(zc - c) for c in centers]))].append(
                _volume_hexes(gmsh, inv, tag))
        layers = [np.concatenate(b) if b else np.zeros((0, 8), np.int64) for b in buckets]
        tol = _occ_tol(H)
        flat = lambda bb: abs(bb[5] - bb[2]) < tol
        bottom = _surface_nodes(gmsh, inv, lambda bb: flat(bb) and abs(bb[2]) < tol)
        top = _surface_nodes(gmsh, inv, lambda bb: flat(bb) and abs(bb[2] - H) < tol)
    finally:
        gmsh.finalize()
    return dict(coords=coords, layers=layers, bottom=bottom, top=top, H=H, bounds=bounds)


def via_cylinder(R=1.0, L=1.0, h=0.15):
    """gmsh all-hex mesh of a solid cylinder (a TSV), axis along z in [0,L].

    Returns dict(coords, elems, cap0, capL, lateral) -- cap0/capL/lateral are boundary node-index
    arrays (z=0 cap, z=L cap, curved wall r=R).
    """
    import gmsh
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("via")
        gmsh.model.occ.addCylinder(0, 0, 0, 0, 0, L, R)
        gmsh.model.occ.synchronize()
        gmsh.option.setNumber("Mesh.MeshSizeMax", h)
        gmsh.option.setNumber("Mesh.SubdivisionAlgorithm", 2)     # all-hexahedra
        gmsh.model.mesh.generate(3)
        coords, inv = _node_table(gmsh)
        elems = _hex_elements(gmsh, inv)
        tol = _occ_tol(L)                                  # OCC cap surfaces have ~1e-7 z-extent
        flat = lambda bb: abs(bb[5] - bb[2]) < tol        # a planar (cap) surface, not the wall
        cap0 = _surface_nodes(gmsh, inv, lambda bb: flat(bb) and abs(bb[2]) < tol)
        capL = _surface_nodes(gmsh, inv, lambda bb: flat(bb) and abs(bb[2] - L) < tol)
        lateral = _surface_nodes(gmsh, inv, lambda bb: not flat(bb))
    finally:
        gmsh.finalize()
    return dict(coords=coords, elems=elems, cap0=cap0, capL=capL, lateral=lateral)


def solder_bump(R_pad=0.42, R_mid=0.50, L=0.40, h=0.12):
    """Parametric axisymmetric solder-joint geometry meshed with all Hex8 elements.

    The radial profile is a smooth spline through ``(z, r) = (0, R_pad)``,
    ``(L/2, R_mid)``, and ``(L, R_pad)`` and is revolved with Gmsh/OpenCASCADE.  Therefore:

    - ``R_mid > R_pad`` creates a barrel joint;
    - ``R_mid < R_pad`` creates an hourglass/waisted joint; and
    - ``R_mid == R_pad`` creates a cylindrical joint through the same geometry path.

    Returns the standard ``coords``, ``elems``, ``cap0``, ``capL``, and ``lateral`` sets plus
    profile metadata and the exact OCC volume.  Dimensions are unit-agnostic but must use one
    consistent unit.  The two caps are intended for pad/platen boundary conditions; the lateral
    surface is left traction-free by the solder reliability solve.
    """
    values = {"R_pad": R_pad, "R_mid": R_mid, "L": L, "h": h}
    for name, value in values.items():
        if not np.isfinite(value) or value <= 0.0:
            raise ValueError(f"{name} must be positive and finite, got {value!r}")

    import gmsh
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("solder_bump")

        volume_tag, meridian = _add_solder_profile_occ(gmsh, R_pad, R_mid, L)
        # A full revolution leaves the source meridian as an orphan CAD surface. Remove it so its
        # mesh cannot introduce disconnected nodes into the FE system.
        gmsh.model.occ.remove([(2, meridian)], recursive=True)
        gmsh.model.occ.synchronize()
        volume = float(gmsh.model.occ.getMass(3, volume_tag))

        gmsh.option.setNumber("Mesh.MeshSizeMax", h)
        gmsh.option.setNumber("Mesh.SubdivisionAlgorithm", 2)
        gmsh.model.mesh.generate(3)
        coords, elems, inv = _hex_volume_mesh(gmsh, volume_tag)
        boundary_tags = [tag for dim, tag in gmsh.model.getBoundary(
            [(3, volume_tag)], oriented=False, recursive=False) if dim == 2]
        tol = _occ_tol(L)
        flat = lambda bb: abs(bb[5] - bb[2]) < tol
        cap0 = _surface_nodes(gmsh, inv, lambda bb: flat(bb) and abs(bb[2]) < tol,
                              boundary_tags)
        capL = _surface_nodes(gmsh, inv, lambda bb: flat(bb) and abs(bb[2] - L) < tol,
                              boundary_tags)
        lateral = _surface_nodes(gmsh, inv, lambda bb: not flat(bb), boundary_tags)
    finally:
        gmsh.finalize()

    shape = "barrel" if R_mid > R_pad else ("hourglass" if R_mid < R_pad else "cylinder")
    return dict(coords=coords, elems=elems, cap0=cap0, capL=capL, lateral=lateral,
                shape=shape, R_pad=float(R_pad), R_mid=float(R_mid), L=float(L),
                profile_z=np.array([0.0, 0.5 * L, L]),
                profile_r=np.array([R_pad, R_mid, R_pad], dtype=float), volume=volume)


def solder_package(R_pad=0.50, R_mid=0.575, L=0.40, *, R_ubm=0.58, R_metal=0.70,
                   R_underfill=0.90, t_ubm=0.05, t_pad=0.08, h=0.25):
    """Conformal six-region Tet4 package model around a profiled solder joint.

    Regions are ``solder``, ``underfill``, ``bottom_ubm``, ``top_ubm``, ``bottom_pad``, and
    ``top_pad``. The underfill is cut by the solder profile, then every touching solid is fragmented
    so material interfaces share nodes. Native tetrahedra are used because the multiply connected
    underfill shell does not reliably pass the all-Hex8 subdivision Jacobian gate. Returns named
    Tet4 region arrays, exterior boundary sets,
    named interface-node sets, per-region OCC volumes, and geometry provenance.

    This is a local axisymmetric material-region model, not an imported package-CAD assembly.
    """
    values = dict(R_pad=R_pad, R_mid=R_mid, L=L, R_ubm=R_ubm, R_metal=R_metal,
                  R_underfill=R_underfill, t_ubm=t_ubm, t_pad=t_pad, h=h)
    for name, value in values.items():
        if not np.isfinite(value) or value <= 0.0:
            raise ValueError(f"{name} must be positive and finite, got {value!r}")
    if R_ubm < R_pad:
        raise ValueError("R_ubm must cover the solder pad radius")
    if R_metal < R_ubm:
        raise ValueError("R_metal must be at least R_ubm")
    if R_underfill <= max(R_pad, R_mid):
        raise ValueError("R_underfill must exceed the maximum solder radius")

    import gmsh
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("solder_package")
        occ = gmsh.model.occ
        solder, meridian = _add_solder_profile_occ(gmsh, R_pad, R_mid, L)
        occ.remove([(2, meridian)], recursive=True)
        bottom_pad = occ.addCylinder(0, 0, -t_ubm - t_pad, 0, 0, t_pad, R_metal)
        bottom_ubm = occ.addCylinder(0, 0, -t_ubm, 0, 0, t_ubm, R_ubm)
        top_ubm = occ.addCylinder(0, 0, L, 0, 0, t_ubm, R_ubm)
        top_pad = occ.addCylinder(0, 0, L + t_ubm, 0, 0, t_pad, R_metal)
        underfill_outer = occ.addCylinder(0, 0, 0, 0, 0, L, R_underfill)
        cut, _ = occ.cut([(3, underfill_outer)], [(3, solder)],
                         removeObject=True, removeTool=False)
        underfill_parts = [tag for dim, tag in cut if dim == 3]
        occ.fragment([(3, solder)], [(3, tag) for tag in
                     [*underfill_parts, bottom_pad, bottom_ubm, top_ubm, top_pad]])
        occ.synchronize()

        tol = 1e-6 * max(1.0, L + 2.0 * (t_ubm + t_pad))
        region_tags = {name: [] for name in
                       ("solder", "underfill", "bottom_ubm", "top_ubm",
                        "bottom_pad", "top_pad")}
        for _, tag in gmsh.model.getEntities(3):
            bb = gmsh.model.getBoundingBox(3, tag)
            zmin, zmax = bb[2], bb[5]
            rmax = max(abs(bb[0]), abs(bb[1]), abs(bb[3]), abs(bb[4]))
            if zmax <= -t_ubm + tol:
                name = "bottom_pad"
            elif zmax <= tol:
                name = "bottom_ubm"
            elif zmin >= L + t_ubm - tol:
                name = "top_pad"
            elif zmin >= L - tol:
                name = "top_ubm"
            elif rmax > max(R_pad, R_mid) + tol:
                name = "underfill"
            else:
                name = "solder"
            region_tags[name].append(tag)
        missing = [name for name, tags in region_tags.items() if not tags]
        if missing:
            raise RuntimeError(f"failed to classify package regions: {missing}")

        volumes = {name: float(sum(occ.getMass(3, tag) for tag in tags))
                   for name, tags in region_tags.items()}
        gmsh.option.setNumber("Mesh.MeshSizeMax", h)
        gmsh.model.mesh.generate(3)
        coords, regions, inv = _tet_region_mesh(gmsh, region_tags)
        tets = np.concatenate(list(regions.values()), axis=0)

        all_boundary_tags = set()
        for tags in region_tags.values():
            for tag in tags:
                all_boundary_tags.update(t for dim, t in gmsh.model.getBoundary(
                    [(3, tag)], oriented=False, recursive=False) if dim == 2)
        z0 = -t_ubm - t_pad
        z1 = L + t_ubm + t_pad
        surface_tol = _occ_tol(z1 - z0)
        flat = lambda bb: abs(bb[5] - bb[2]) < surface_tol
        bottom = _surface_nodes(gmsh, inv,
                                lambda bb: flat(bb) and abs(bb[2] - z0) < surface_tol,
                                all_boundary_tags)
        top = _surface_nodes(gmsh, inv,
                             lambda bb: flat(bb) and abs(bb[2] - z1) < surface_tol,
                             all_boundary_tags)

        def nodes(name):
            return np.unique(regions[name])

        interfaces = {
            "solder_bottom_ubm": np.intersect1d(nodes("solder"), nodes("bottom_ubm")),
            "solder_top_ubm": np.intersect1d(nodes("solder"), nodes("top_ubm")),
            "solder_underfill": np.intersect1d(nodes("solder"), nodes("underfill")),
            "bottom_pad_ubm": np.intersect1d(nodes("bottom_pad"), nodes("bottom_ubm")),
            "top_pad_ubm": np.intersect1d(nodes("top_pad"), nodes("top_ubm")),
        }
    finally:
        gmsh.finalize()

    shape = "barrel" if R_mid > R_pad else ("hourglass" if R_mid < R_pad else "cylinder")
    return dict(coords=coords, tets=tets, elems=tets, element="Tet4",
                regions=regions, bottom=bottom, top=top,
                interfaces=interfaces, volumes=volumes, shape=shape,
                R_pad=float(R_pad), R_mid=float(R_mid), L=float(L),
                geometry={name: float(value) for name, value in values.items()})


# --- linear tetrahedra (gmsh's native output for ARBITRARY CAD; element ported in tet_element.py) ---

def _tet_elements(gmsh, inv):
    """0-based Tet4 connectivity (gmsh element type 4), remapped through `inv`."""
    et, _, en = gmsh.model.mesh.getElements(dim=3)
    conn = np.concatenate([n.reshape(-1, 4) for e, n in zip(et, en) if e == 4], axis=0)
    return inv[conn]


def _tet_region_mesh(gmsh, region_tags):
    """One connected node table plus positively oriented Tet4 arrays for named OCC regions."""
    raw = {}
    for name, tags in region_tags.items():
        blocks = []
        for tag in tags:
            et, _, en = gmsh.model.mesh.getElements(dim=3, tag=int(tag))
            blocks.extend(n.reshape(-1, 4) for e, n in zip(et, en) if e == 4)
        if not blocks:
            raise RuntimeError(f"region {name!r} produced no Tet4 elements")
        raw[name] = np.concatenate(blocks, axis=0).astype(np.int64)
    used_tags = np.unique(np.concatenate(list(raw.values()), axis=0))
    all_coords, all_inv = _node_table(gmsh)
    coords = all_coords[all_inv[used_tags]]
    inv = np.full(int(used_tags.max()) + 1, -1, dtype=np.int64)
    inv[used_tags] = np.arange(len(used_tags))
    regions = {name: _orient_tets(coords, inv[conn]) for name, conn in raw.items()}
    return coords, regions, inv


def _tet_signed_volume(coords, tets):
    d = coords[tets]
    return np.einsum('ei,ei->e', np.cross(d[:, 1] - d[:, 0], d[:, 2] - d[:, 0]), d[:, 3] - d[:, 0]) / 6.0


def min_signed_tet_volume(coords, tets):
    """Min Tet4 signed volume over the mesh; >0 everywhere == valid, correctly-oriented (our
    convention). The tet analogue of `min_signed_jacobian` -- run on every generated mesh."""
    return float(_tet_signed_volume(coords, tets).min())


def _orient_tets(coords, tets):
    """Flip any inverted tets (swap the last two nodes) so every signed volume is > 0. gmsh's
    tet node order usually already gives detJ>0, but this makes the mesh robust regardless."""
    v = _tet_signed_volume(coords, tets)
    return np.where((v < 0)[:, None], tets[:, [0, 1, 3, 2]], tets)


def tet_box(W=1.0, h=0.18):
    """gmsh all-Tet4 mesh of a WxWxW box (default Delaunay, no recombination -- the mesh
    gmsh grows for arbitrary solids). Returns (coords[nn,3], tets[ne,4]) with all signed vols > 0."""
    import gmsh
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("tetbox")
        gmsh.model.occ.addBox(0, 0, 0, W, W, W)
        gmsh.model.occ.synchronize()
        gmsh.option.setNumber("Mesh.MeshSizeMax", h)
        gmsh.model.mesh.generate(3)
        coords, inv = _node_table(gmsh)
        tets = _orient_tets(coords, _tet_elements(gmsh, inv))
    finally:
        gmsh.finalize()
    return coords, tets


def tet_cylinder(R=1.0, L=1.0, h=0.18):
    """gmsh all-TET mesh of a solid cylinder -- a curved shape the all-hex subdivision handles
    poorly, meshed natively as tets. Returns dict(coords, tets, cap0, capL, lateral) like
    `via_cylinder` (boundary node-index arrays: z=0 cap, z=L cap, curved wall)."""
    import gmsh
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("tetvia")
        gmsh.model.occ.addCylinder(0, 0, 0, 0, 0, L, R)
        gmsh.model.occ.synchronize()
        gmsh.option.setNumber("Mesh.MeshSizeMax", h)
        gmsh.model.mesh.generate(3)
        coords, inv = _node_table(gmsh)
        tets = _orient_tets(coords, _tet_elements(gmsh, inv))
        tol = _occ_tol(L)
        flat = lambda bb: abs(bb[5] - bb[2]) < tol
        cap0 = _surface_nodes(gmsh, inv, lambda bb: flat(bb) and abs(bb[2]) < tol)
        capL = _surface_nodes(gmsh, inv, lambda bb: flat(bb) and abs(bb[2] - L) < tol)
        lateral = _surface_nodes(gmsh, inv, lambda bb: not flat(bb))
    finally:
        gmsh.finalize()
    return dict(coords=coords, tets=tets, cap0=cap0, capL=capL, lateral=lateral)


def tsv_device_submodel(*, diameter_um=10.0, via_depth_um=55.0, oxide_um=0.4,
                        si_radius_um=30.0, si_depth_um=60.0, h_um=2.0,
                        raman_depth_um=0.2, tsv_id="TSV_0001",
                        h_near_um=None, refine_extent_um=None):
    """Conformal Tet4 Cu/SiO2/Si blind-TSV local geometry in micrometers.

    The wafer surface is ``z=0`` and the model occupies negative z.  The Cu core terminates at
    ``z=-via_depth_um`` and the conformal oxide cup extends one liner thickness beneath it. Gmsh's
    frontal 3-D algorithm is used because the thin conformal liner is not a qualified all-Hex
    subdivision shape. This function constructs geometry only; it does not imply Raman validation.

    Returns a dict with one connected ``coords`` table, named Tet4 ``regions``, ``top``/``bottom``/
    ``outer`` boundaries, shared ``interfaces``, exact and meshed region volumes, and explicit
    geometry/unit/provenance metadata.
    """
    values = {
        "diameter_um": diameter_um, "via_depth_um": via_depth_um, "oxide_um": oxide_um,
        "si_radius_um": si_radius_um, "si_depth_um": si_depth_um, "h_um": h_um,
        "raman_depth_um": raman_depth_um,
    }
    if any(not np.isfinite(value) or value <= 0.0 for value in values.values()):
        raise ValueError("all TSV geometry and mesh dimensions must be positive and finite")
    if not str(tsv_id):
        raise ValueError("tsv_id must be non-empty")
    radius = 0.5 * float(diameter_um)
    liner_radius = radius + float(oxide_um)
    if si_radius_um <= liner_radius:
        raise ValueError("si_radius_um must exceed the Cu radius plus oxide thickness")
    if si_depth_um <= via_depth_um + oxide_um:
        raise ValueError("si_depth_um must exceed via_depth_um + oxide_um for a lined blind TSV")
    if raman_depth_um >= via_depth_um:
        raise ValueError("raman_depth_um must lie above the blind-via tip")
    if (h_near_um is None) != (refine_extent_um is None):
        raise ValueError("h_near_um and refine_extent_um must be supplied together")
    if h_near_um is not None:
        if (not np.isfinite(h_near_um) or h_near_um <= 0.0 or h_near_um > h_um
                or not np.isfinite(refine_extent_um) or refine_extent_um <= 0.0):
            raise ValueError("near-surface refinement requires 0 < h_near_um <= h_um and a positive extent")

    import gmsh
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("tsv_device_submodel")
        occ = gmsh.model.occ
        silicon = occ.addCylinder(0.0, 0.0, -si_depth_um, 0.0, 0.0, si_depth_um,
                                  si_radius_um)
        liner_outer = occ.addCylinder(
            0.0, 0.0, -(via_depth_um + oxide_um), 0.0, 0.0, via_depth_um + oxide_um,
            liner_radius,
        )
        copper = occ.addCylinder(0.0, 0.0, -via_depth_um, 0.0, 0.0, via_depth_um, radius)
        # Nested fragmentation yields three conformal volumes: core, annulus, and silicon with a
        # blind recess. removeAllDuplicates is important at the Cu/liner/Si triple edge.
        occ.fragment([(3, silicon)], [(3, liner_outer), (3, copper)])
        occ.removeAllDuplicates()
        occ.synchronize()

        region_tags = {"copper": [], "oxide": [], "silicon": []}
        exact_volumes = {}
        radial_split = 0.5 * (radius + liner_radius)
        for _, tag in gmsh.model.getEntities(3):
            bb = gmsh.model.getBoundingBox(3, tag)
            extent = max(abs(bb[0]), abs(bb[1]), abs(bb[3]), abs(bb[4]))
            if extent < radial_split:
                name = "copper"
            elif extent < 0.5 * (liner_radius + si_radius_um):
                name = "oxide"
            else:
                name = "silicon"
            region_tags[name].append(tag)
            exact_volumes[name] = exact_volumes.get(name, 0.0) + float(occ.getMass(3, tag))
        if any(len(tags) != 1 for tags in region_tags.values()):
            raise RuntimeError(f"expected one Cu/oxide/Si volume, got {region_tags}")

        tol = _occ_tol(si_depth_um)
        gmsh.option.setNumber("Mesh.MeshSizeMax", h_um)
        refinement_sources = []
        if h_near_um is not None:
            # Refine by distance from the Cu/liner top faces, not the full wafer surface. This
            # creates a local near-surface zone around the TSV without refining the entire Si disk.
            for _, tag in gmsh.model.getEntities(2):
                bb = gmsh.model.getBoundingBox(2, tag)
                is_top = abs(bb[5] - bb[2]) < tol and abs(bb[5]) < tol
                radial_extent = max(abs(bb[0]), abs(bb[1]), abs(bb[3]), abs(bb[4]))
                if is_top and radial_extent < liner_radius + 10.0 * tol:
                    refinement_sources.append(tag)
            if not refinement_sources:
                raise RuntimeError("could not identify Cu/liner top surfaces for local refinement")
            distance = gmsh.model.mesh.field.add("Distance")
            gmsh.model.mesh.field.setNumbers(distance, "SurfacesList", refinement_sources)
            gmsh.model.mesh.field.setNumber(distance, "Sampling", 100)
            threshold = gmsh.model.mesh.field.add("Threshold")
            gmsh.model.mesh.field.setNumber(threshold, "InField", distance)
            gmsh.model.mesh.field.setNumber(threshold, "SizeMin", h_near_um)
            gmsh.model.mesh.field.setNumber(threshold, "SizeMax", h_um)
            gmsh.model.mesh.field.setNumber(threshold, "DistMin", 0.0)
            gmsh.model.mesh.field.setNumber(threshold, "DistMax", refine_extent_um)
            gmsh.model.mesh.field.setAsBackgroundMesh(threshold)
        gmsh.option.setNumber("Mesh.Algorithm3D", 4)  # frontal: robust for the thin blind liner
        gmsh.model.mesh.generate(3)
        coords, regions, inv = _tet_region_mesh(gmsh, region_tags)
        all_tets = np.concatenate(list(regions.values()), axis=0)
        flat = lambda bb: abs(bb[5] - bb[2]) < tol
        top = _surface_nodes(gmsh, inv, lambda bb: flat(bb) and abs(bb[5]) < tol)
        bottom = _surface_nodes(
            gmsh, inv, lambda bb: flat(bb) and abs(bb[2] + si_depth_um) < tol
        )
        outer = _surface_nodes(
            gmsh, inv,
            lambda bb: (not flat(bb)) and bb[3] > 0.5 * (liner_radius + si_radius_um),
        )
    finally:
        gmsh.finalize()

    used = {name: np.unique(tets) for name, tets in regions.items()}
    interfaces = {
        "copper_oxide": np.intersect1d(used["copper"], used["oxide"]),
        "oxide_silicon": np.intersect1d(used["oxide"], used["silicon"]),
    }
    if any(not len(nodes) for nodes in interfaces.values()):
        raise RuntimeError("TSV material interfaces do not share conformal nodes")
    direct_copper_silicon = np.intersect1d(used["copper"], used["silicon"])
    if len(direct_copper_silicon):
        raise RuntimeError("oxide cup is incomplete: Cu and Si share direct interface nodes")
    mesh_volumes = {
        name: float(_tet_signed_volume(coords, tets).sum()) for name, tets in regions.items()
    }
    return {
        "coords": coords, "regions": regions, "top": top, "bottom": bottom, "outer": outer,
        "interfaces": interfaces, "direct_copper_silicon_nodes": direct_copper_silicon,
        "exact_volumes_um3": exact_volumes,
        "mesh_volumes_um3": mesh_volumes, "min_signed_tet_volume_um3":
        min_signed_tet_volume(coords, all_tets),
        "geometry": {name: float(value) for name, value in values.items()},
        "mesh_refinement": {
            "h_near_um": None if h_near_um is None else float(h_near_um),
            "refine_extent_um": None if refine_extent_um is None else float(refine_extent_um),
            "source_surface_count": len(refinement_sources),
        },
        "units": {"length": "um", "volume": "um^3"}, "tsv_id": str(tsv_id),
        "coordinate_frame": {
            "name": "tsv_crystal_natural", "origin_um": [0.0, 0.0, 0.0],
            "x_axis": "[100]", "y_axis": "[010]", "z_axis": "[001]",
            "handedness": "right", "z_sign": "out_of_wafer",
        },
        "crystal_to_global": np.eye(3),
        "wafer_surface_z_um": 0.0, "raman_plane_z_um": -float(raman_depth_um),
        "copper_tip_z_um": -float(via_depth_um),
        "liner_tip_z_um": -float(via_depth_um + oxide_um),
        "geometry_fidelity": "parametric_device_submodel",
        "release_validation": False,
    }


def tsv_periodic_cell(*, pitch_110_um=40.0, pitch_1m10_um=50.0, diameter_um=10.0,
                      via_depth_um=55.0, oxide_um=0.4, si_depth_um=60.0, h_um=2.0,
                      raman_depth_um=0.2, tsv_id="TSV_0001", h_near_um=None,
                      refine_extent_um=None):
    """Full rectangular foundation for the Jiang 40/50 µm periodic Raman cell.

    Mesh x is [110], mesh y is [-110] (the opposite sign of the paper's [1-10] pitch direction,
    chosen to keep x/y/z=[001] right-handed), and z points out of the wafer.  The function creates
    conformal Cu/oxide-cup/Si Tet4 regions and matching opposite-face meshes. Gmsh creates the
    surface correspondence; CoupFE's exact affine MPC supplies the mechanics separately.
    """
    values = {
        "pitch_110_um": pitch_110_um, "pitch_1m10_um": pitch_1m10_um,
        "diameter_um": diameter_um, "via_depth_um": via_depth_um, "oxide_um": oxide_um,
        "si_depth_um": si_depth_um, "h_um": h_um, "raman_depth_um": raman_depth_um,
    }
    if any(not np.isfinite(value) or value <= 0.0 for value in values.values()):
        raise ValueError("all periodic-cell geometry and mesh dimensions must be positive and finite")
    radius = 0.5 * float(diameter_um)
    liner_radius = radius + float(oxide_um)
    if min(pitch_110_um, pitch_1m10_um) <= 2.0 * liner_radius:
        raise ValueError("periodic pitches must exceed the lined TSV diameter")
    if si_depth_um <= via_depth_um + oxide_um:
        raise ValueError("si_depth_um must exceed the lined blind-via depth")
    if raman_depth_um >= via_depth_um or not str(tsv_id):
        raise ValueError("Raman depth must lie above the via tip and tsv_id must be non-empty")
    if (h_near_um is None) != (refine_extent_um is None):
        raise ValueError("h_near_um and refine_extent_um must be supplied together")
    if h_near_um is not None and (
        not np.isfinite(h_near_um) or h_near_um <= 0.0 or h_near_um > h_um
        or not np.isfinite(refine_extent_um) or refine_extent_um <= 0.0
    ):
        raise ValueError("near-surface refinement requires 0 < h_near_um <= h_um and a positive extent")

    import gmsh
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("tsv_periodic_cell")
        occ = gmsh.model.occ
        silicon = occ.addBox(
            -0.5 * pitch_110_um, -0.5 * pitch_1m10_um, -si_depth_um,
            pitch_110_um, pitch_1m10_um, si_depth_um,
        )
        liner_outer = occ.addCylinder(
            0.0, 0.0, -(via_depth_um + oxide_um), 0.0, 0.0, via_depth_um + oxide_um,
            liner_radius,
        )
        copper = occ.addCylinder(0.0, 0.0, -via_depth_um, 0.0, 0.0, via_depth_um, radius)
        occ.fragment([(3, silicon)], [(3, liner_outer), (3, copper)])
        occ.removeAllDuplicates(); occ.synchronize()

        region_tags = {"copper": [], "oxide": [], "silicon": []}
        exact_volumes = {}
        radial_split = 0.5 * (radius + liner_radius)
        for _, tag in gmsh.model.getEntities(3):
            bb = gmsh.model.getBoundingBox(3, tag)
            extent = max(abs(bb[0]), abs(bb[1]), abs(bb[3]), abs(bb[4]))
            if extent < radial_split:
                name = "copper"
            elif extent < 0.5 * (liner_radius + 0.5 * min(pitch_110_um, pitch_1m10_um)):
                name = "oxide"
            else:
                name = "silicon"
            region_tags[name].append(tag)
            exact_volumes[name] = exact_volumes.get(name, 0.0) + float(occ.getMass(3, tag))
        if any(len(tags) != 1 for tags in region_tags.values()):
            raise RuntimeError(f"expected one periodic Cu/oxide/Si volume, got {region_tags}")

        tol = _occ_tol(max(pitch_110_um, pitch_1m10_um, si_depth_um))
        flat_x = lambda bb: abs(bb[3] - bb[0]) < tol
        flat_y = lambda bb: abs(bb[4] - bb[1]) < tol
        side_tags = {name: [] for name in ("x_minus", "x_plus", "y_minus", "y_plus")}
        for _, tag in gmsh.model.getEntities(2):
            bb = gmsh.model.getBoundingBox(2, tag)
            if flat_x(bb) and abs(bb[0] + 0.5 * pitch_110_um) < tol:
                side_tags["x_minus"].append(tag)
            elif flat_x(bb) and abs(bb[3] - 0.5 * pitch_110_um) < tol:
                side_tags["x_plus"].append(tag)
            elif flat_y(bb) and abs(bb[1] + 0.5 * pitch_1m10_um) < tol:
                side_tags["y_minus"].append(tag)
            elif flat_y(bb) and abs(bb[4] - 0.5 * pitch_1m10_um) < tol:
                side_tags["y_plus"].append(tag)
        if any(len(tags) != 1 for tags in side_tags.values()):
            raise RuntimeError(f"expected one surface on each periodic side, got {side_tags}")

        def translation_affine(dx=0.0, dy=0.0, dz=0.0):
            return [1.0, 0.0, 0.0, dx,
                    0.0, 1.0, 0.0, dy,
                    0.0, 0.0, 1.0, dz,
                    0.0, 0.0, 0.0, 1.0]

        gmsh.model.mesh.setPeriodic(
            2, side_tags["x_plus"], side_tags["x_minus"],
            translation_affine(dx=pitch_110_um),
        )
        gmsh.model.mesh.setPeriodic(
            2, side_tags["y_plus"], side_tags["y_minus"],
            translation_affine(dy=pitch_1m10_um),
        )
        gmsh.option.setNumber("Mesh.MeshSizeMax", h_um)
        refinement_sources = []
        if h_near_um is not None:
            for _, tag in gmsh.model.getEntities(2):
                bb = gmsh.model.getBoundingBox(2, tag)
                is_top = abs(bb[5] - bb[2]) < tol and abs(bb[5]) < tol
                radial_extent = max(abs(bb[0]), abs(bb[1]), abs(bb[3]), abs(bb[4]))
                if is_top and radial_extent < liner_radius + 10.0 * tol:
                    refinement_sources.append(tag)
            if not refinement_sources:
                raise RuntimeError("could not identify periodic-cell Cu/liner refinement surfaces")
            distance = gmsh.model.mesh.field.add("Distance")
            gmsh.model.mesh.field.setNumbers(distance, "SurfacesList", refinement_sources)
            gmsh.model.mesh.field.setNumber(distance, "Sampling", 100)
            threshold = gmsh.model.mesh.field.add("Threshold")
            gmsh.model.mesh.field.setNumber(threshold, "InField", distance)
            gmsh.model.mesh.field.setNumber(threshold, "SizeMin", h_near_um)
            gmsh.model.mesh.field.setNumber(threshold, "SizeMax", h_um)
            gmsh.model.mesh.field.setNumber(threshold, "DistMin", 0.0)
            gmsh.model.mesh.field.setNumber(threshold, "DistMax", refine_extent_um)
            gmsh.model.mesh.field.setAsBackgroundMesh(threshold)
        gmsh.option.setNumber("Mesh.Algorithm3D", 4)
        gmsh.model.mesh.generate(3)
        coords, regions, inv = _tet_region_mesh(gmsh, region_tags)
        all_tets = np.concatenate(list(regions.values()), axis=0)
        flat_z = lambda bb: abs(bb[5] - bb[2]) < tol
        top = _surface_nodes(gmsh, inv, lambda bb: flat_z(bb) and abs(bb[5]) < tol)
        bottom = _surface_nodes(
            gmsh, inv, lambda bb: flat_z(bb) and abs(bb[2] + si_depth_um) < tol
        )
        x_minus = _surface_nodes(
            gmsh, inv, lambda bb: flat_x(bb) and abs(bb[0] + 0.5 * pitch_110_um) < tol
        )
        x_plus = _surface_nodes(
            gmsh, inv, lambda bb: flat_x(bb) and abs(bb[3] - 0.5 * pitch_110_um) < tol
        )
        y_minus = _surface_nodes(
            gmsh, inv, lambda bb: flat_y(bb) and abs(bb[1] + 0.5 * pitch_1m10_um) < tol
        )
        y_plus = _surface_nodes(
            gmsh, inv, lambda bb: flat_y(bb) and abs(bb[4] - 0.5 * pitch_1m10_um) < tol
        )
        gmsh_periodic_counts = {}
        for axis, slave_name in (("x", "x_plus"), ("y", "y_plus")):
            _master_tag, slave_raw, master_raw, _affine = gmsh.model.mesh.getPeriodicNodes(
                2, side_tags[slave_name][0], includeHighOrderNodes=True
            )
            slave_raw = np.asarray(slave_raw, dtype=np.int64)
            master_raw = np.asarray(master_raw, dtype=np.int64)
            valid = ((slave_raw < len(inv)) & (master_raw < len(inv))
                     & (inv[slave_raw] >= 0) & (inv[master_raw] >= 0))
            gmsh_periodic_counts[axis] = int(np.count_nonzero(valid))
    finally:
        gmsh.finalize()

    used = {name: np.unique(tets) for name, tets in regions.items()}
    interfaces = {
        "copper_oxide": np.intersect1d(used["copper"], used["oxide"]),
        "oxide_silicon": np.intersect1d(used["oxide"], used["silicon"]),
    }
    direct = np.intersect1d(used["copper"], used["silicon"])
    if any(not len(nodes) for nodes in interfaces.values()) or len(direct):
        raise RuntimeError("periodic TSV cup interfaces are nonconformal or permit direct Cu-Si contact")
    mesh_volumes = {
        name: float(_tet_signed_volume(coords, tets).sum()) for name, tets in regions.items()
    }
    inv_sqrt2 = 1.0 / np.sqrt(2.0)
    rotation = np.array([
        [inv_sqrt2, inv_sqrt2, 0.0], [-inv_sqrt2, inv_sqrt2, 0.0], [0.0, 0.0, 1.0]
    ])
    from eda_multiphysics.periodic import PeriodicBox

    box = PeriodicBox(
        origin=[-0.5 * pitch_110_um, -0.5 * pitch_1m10_um, -si_depth_um],
        lattice=np.diag([pitch_110_um, pitch_1m10_um, si_depth_um]),
        periodic=(True, True, False),
        coordinate_frame={"x": "[110]", "y": "[-110]", "z": "[001]"},
    )
    x_pairs = box.pair_faces(coords, x_minus, x_plus, 0, atol=10.0 * tol)
    y_pairs = box.pair_faces(coords, y_minus, y_plus, 1, atol=10.0 * tol)

    def pair_record(pairs):
        return {
            "master_nodes": pairs.master_nodes.copy(),
            "slave_nodes": pairs.slave_nodes.copy(),
            "translation_um": pairs.translation.copy(),
            "max_mismatch_um": float(pairs.max_mismatch),
            "rms_mismatch_um": float(pairs.rms_mismatch),
            "tolerance_um": float(pairs.tolerance),
            "sha256": pairs.sha256,
        }

    return {
        "coords": coords, "regions": regions, "top": top, "bottom": bottom,
        "outer": np.unique(np.r_[x_minus, x_plus, y_minus, y_plus]),
        "periodic_faces": {"x_minus": x_minus, "x_plus": x_plus,
                           "y_minus": y_minus, "y_plus": y_plus},
        "periodic_node_pairs": {"x": pair_record(x_pairs), "y": pair_record(y_pairs)},
        "periodic_pairing_status": "matching_nodes_verified",
        "periodic_mechanics_status": "not_solved",
        "gmsh_periodic_interior_node_counts": gmsh_periodic_counts,
        "interfaces": interfaces, "direct_copper_silicon_nodes": direct,
        "exact_volumes_um3": exact_volumes, "mesh_volumes_um3": mesh_volumes,
        "min_signed_tet_volume_um3": min_signed_tet_volume(coords, all_tets),
        "geometry": {name: float(value) for name, value in values.items()},
        "mesh_refinement": {
            "h_near_um": None if h_near_um is None else float(h_near_um),
            "refine_extent_um": None if refine_extent_um is None else float(refine_extent_um),
            "source_surface_count": len(refinement_sources),
        },
        "units": {"length": "um", "volume": "um^3"}, "tsv_id": str(tsv_id),
        "coordinate_frame": {
            "name": "jiang_periodic_cell", "origin_um": [0.0, 0.0, 0.0],
            "x_axis": "[110]", "y_axis": "[-110]", "z_axis": "[001]",
            "paper_y_pitch_direction": "[1-10] (opposite sign equivalent)",
            "handedness": "right", "z_sign": "out_of_wafer",
        },
        "crystal_to_global": rotation,
        "periodic_box": {
            "origin_um": box.origin.copy(), "lattice_um": box.lattice.copy(),
            "periodic": box.periodic, "sha256": box.sha256,
        },
        "wafer_surface_z_um": 0.0, "raman_plane_z_um": -float(raman_depth_um),
        "copper_tip_z_um": -float(via_depth_um),
        "liner_tip_z_um": -float(via_depth_um + oxide_um),
        "geometry_fidelity": "periodic_raman_cell_foundation",
        "release_validation": False,
    }
