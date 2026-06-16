import FreeCAD as App
import FreeCADGui as Gui
import Part
import math
import time
from collections import defaultdict

try:
    from PySide6 import QtCore, QtGui, QtWidgets
except ImportError:
    try:
        from PySide2 import QtCore, QtGui, QtWidgets
    except ImportError:
        from PySide import QtCore, QtGui
        QtWidgets = QtGui

class KCICrossSectionCurves:
    def __init__(self):
        sel = Gui.Selection.getSelection()
        if not sel or not hasattr(sel[0], "Mesh"):
            QtWidgets.QMessageBox.critical(None, "Error", "Select a Mesh object!")
            return

        self.mesh_obj = sel[0]
        self.mesh = self.mesh_obj.Mesh
        self.bbox = self.mesh.BoundBox
        self.debug = True

        # UI
        self.form = QtWidgets.QWidget()
        self.form.setWindowTitle("KCI Cross-Section Curves")
        layout = QtWidgets.QVBoxLayout(self.form)

        # Mesh Info
        info_group = QtWidgets.QGroupBox("Mesh Info")
        info_layout = QtWidgets.QGridLayout(info_group)
        info_layout.addWidget(QtWidgets.QLabel(f"X: {self.bbox.XLength:.1f} mm"), 0, 0)
        info_layout.addWidget(QtWidgets.QLabel(f"Y: {self.bbox.YLength:.1f} mm"), 1, 0)
        info_layout.addWidget(QtWidgets.QLabel(f"Z: {self.bbox.ZLength:.1f} mm"), 2, 0)
        info_layout.addWidget(QtWidgets.QLabel(f"Facets: {len(self.mesh.Facets):,}"), 0, 1)
        info_layout.addWidget(QtWidgets.QLabel(f"Vertices: {len(self.mesh.Points):,}"), 1, 1)
        layout.addWidget(info_group)

        # Curve Type
        curve_group = QtWidgets.QGroupBox("Curve Type")
        curve_layout = QtWidgets.QVBoxLayout(curve_group)
        self.curve_combo = QtWidgets.QComboBox()
        self.curve_combo.addItems(["B-Spline", "NURBS", "Bezier", "Polyline"])
        self.curve_combo.setToolTip("Curve fitting method:\n- B-Spline: standard smooth\n- NURBS: rational B-Spline\n- Bezier: stable for simple shapes\n- Polyline: straight segments")
        curve_layout.addWidget(self.curve_combo)
        layout.addWidget(curve_group)

        # Settings
        settings_group = QtWidgets.QGroupBox("Settings")
        form_layout = QtWidgets.QFormLayout(settings_group)
        
        self.axis_combo = QtWidgets.QComboBox()
        self.axis_combo.addItems(["X", "Y", "Z"])
        self.axis_combo.setToolTip("Axis perpendicular to cutting planes")
        form_layout.addRow("Axis:", self.axis_combo)
        
        self.count_spin = QtWidgets.QSpinBox()
        self.count_spin.setRange(2, 100)
        self.count_spin.setValue(12)
        self.count_spin.setToolTip("Number of parallel sections")
        form_layout.addRow("Sections:", self.count_spin)
        
        self.degree_spin = QtWidgets.QSpinBox()
        self.degree_spin.setRange(2, 5)
        self.degree_spin.setValue(3)
        self.degree_spin.setToolTip("Curve degree (3 = cubic)")
        form_layout.addRow("Degree:", self.degree_spin)
        
        self.close_thresh_spin = QtWidgets.QDoubleSpinBox()
        self.close_thresh_spin.setRange(0.1, 20.0)
        self.close_thresh_spin.setValue(0.5)
        self.close_thresh_spin.setToolTip("Max distance between endpoints to consider closed.\nIncrease for closed surfaces, decrease for open ones.")
        form_layout.addRow("Closeness (mm):", self.close_thresh_spin)
        
        self.closed_check = QtWidgets.QCheckBox()
        self.closed_check.setChecked(True)
        self.closed_check.setToolTip("Enable closure detection.\nUncheck to keep all curves open.")
        form_layout.addRow("Closed:", self.closed_check)
        
        self.smooth_spin = QtWidgets.QDoubleSpinBox()
        self.smooth_spin.setRange(0.0, 1.0)
        self.smooth_spin.setValue(0.3)
        self.smooth_spin.setSingleStep(0.05)
        self.smooth_spin.setToolTip("Smoothing amount (0 = none, 1 = max)")
        form_layout.addRow("Smoothing:", self.smooth_spin)
        
        layout.addWidget(settings_group)

        # Progress
        self.progress = QtWidgets.QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        # Buttons
        self.btn_run = QtWidgets.QPushButton("Run")
        self.btn_run.setToolTip("Start section generation")
        self.btn_run.clicked.connect(self.generate_curves)
        layout.addWidget(self.btn_run)
        
        self.cancel_btn = QtWidgets.QPushButton("Cancel")
        self.cancel_btn.setToolTip("Cancel current operation")
        self.cancel_btn.clicked.connect(self.cancel_operation)
        self.cancel_btn.setVisible(False)
        layout.addWidget(self.cancel_btn)

        self.is_cancelled = False
        self.start_time = None

        # Auto closeness based on object size
        avg_dim = (self.bbox.XLength + self.bbox.YLength + self.bbox.ZLength) / 3.0
        self.close_thresh_spin.setValue(max(0.5, avg_dim * 0.02))
        self.debug_print(f"Auto closeness = {self.close_thresh_spin.value():.2f} mm")

    def debug_print(self, msg):
        if self.debug:
            App.Console.PrintMessage(f"[DEBUG] {msg}\n")

    def cancel_operation(self):
        self.is_cancelled = True
        App.Console.PrintMessage("Cancelled by user.\n")

    # ---------- Triangle-plane intersection ----------
    def intersect_triangle_with_plane(self, v1, v2, v3, axis, value):
        edges = [(v1, v2), (v2, v3), (v3, v1)]
        points = []
        for a, b in edges:
            if axis == 'X':
                d1 = a.x - value
                d2 = b.x - value
            elif axis == 'Y':
                d1 = a.y - value
                d2 = b.y - value
            else:
                d1 = a.z - value
                d2 = b.z - value

            if d1 * d2 > 0:
                continue
            if abs(d1) < 1e-8:
                points.append(a)
                continue
            if abs(d2) < 1e-8:
                points.append(b)
                continue
            t = -d1 / (d2 - d1)
            p = a + t * (b - a)
            points.append(p)

        if len(points) == 2:
            return [points]
        return []

    # ---------- Improved chain builder ----------
    def build_chains(self, segments, close_threshold):
        if not segments:
            return []

        graph = defaultdict(list)
        for p1, p2 in segments:
            key1 = (round(p1.x, 4), round(p1.y, 4), round(p1.z, 4))
            key2 = (round(p2.x, 4), round(p2.y, 4), round(p2.z, 4))
            graph[key1].append(key2)
            graph[key2].append(key1)

        # Debug: check degrees
        degrees = [len(v) for v in graph.values()]
        self.debug_print(f"  Graph degrees: min={min(degrees) if degrees else 0}, max={max(degrees) if degrees else 0}")

        visited = set()
        chains = []

        # Find start nodes: degree 1 for open chains, or any node for closed
        start_nodes = [k for k, v in graph.items() if len(v) == 1]
        if not start_nodes:
            # Closed loop: pick any node
            start_nodes = list(graph.keys())

        for start in start_nodes:
            if start in visited:
                continue
            chain = [start]
            visited.add(start)
            current = start
            
            while True:
                neighbors = graph.get(current, [])
                # Choose next unvisited neighbor (prefer the one that continues direction)
                next_node = None
                for nb in neighbors:
                    if nb not in visited:
                        next_node = nb
                        break
                if next_node is None:
                    # Check if we have returned to start (closed loop)
                    if len(chain) > 2 and chain[0] in neighbors:
                        # Closed loop completed
                        chain.append(chain[0])
                        break
                    # Check if start and end are close (closure by distance)
                    if len(chain) > 2:
                        p1 = App.Vector(chain[0][0], chain[0][1], chain[0][2])
                        p2 = App.Vector(chain[-1][0], chain[-1][1], chain[-1][2])
                        if (p1 - p2).Length <= close_threshold:
                            chain.append(chain[0])
                            break
                    # Otherwise, it's an open chain
                    break
                chain.append(next_node)
                visited.add(next_node)
                current = next_node

            # Convert tuples to App.Vector
            pts = [App.Vector(p[0], p[1], p[2]) for p in chain]
            chains.append(pts)

        return chains

    # ---------- Curve creation (robust) ----------
    def create_bspline_curve(self, points, degree, closed):
        if len(points) < 3:
            return None
        
        # For closed, ensure start == end
        if closed and len(points) > 1:
            if (points[0] - points[-1]).Length > 1e-6:
                points.append(points[0])
        
        # Reduce if too many points
        if len(points) > 100:
            step = max(1, len(points) // 80)
            points = points[::step]
            if len(points) < 3:
                points = points[::1]
        
        try:
            bspline = Part.BSplineCurve()
            # Try interpolation
            try:
                bspline.interpolate(points)
            except:
                try:
                    bspline.interpolate(points, degree)
                except:
                    bspline.approximate(points, Tolerance=0.1)
            
            # Set periodic if closed
            if closed and len(points) > 3:
                try:
                    bspline.setPeriodic(True)
                except:
                    pass
            return bspline.toShape()
        except Exception as e:
            self.debug_print(f"  BSpline creation failed: {str(e)}")
            return None

    def create_bezier_curve(self, points):
        if len(points) < 2:
            return None
        if len(points) > 20:
            step = max(1, len(points) // 15)
            points = points[::step]
        try:
            bez = Part.BezierCurve()
            bez.setPoles(points)
            return bez.toShape()
        except:
            return None

    def create_polyline_curve(self, points):
        if len(points) < 2:
            return None
        return Part.makePolygon(points)

    def create_curve(self, points, degree, closed, curve_type):
        if len(points) < 3:
            return None

        # Smoothing (only if not closed, or with care)
        if self.smooth_spin.value() > 0.1 and len(points) > 5:
            n = len(points)
            smoothed = []
            for i in range(n):
                if closed:
                    prev = (i - 1) % n
                    next = (i + 1) % n
                    idx = [prev, i, next]
                else:
                    idx = [max(0,i-1), i, min(n-1,i+1)]
                avg = App.Vector(0,0,0)
                for j in idx:
                    avg += points[j]
                avg /= len(idx)
                smoothed.append(avg)
            points = smoothed

        if curve_type == "Bezier":
            return self.create_bezier_curve(points)
        elif curve_type == "Polyline":
            return self.create_polyline_curve(points)
        else:  # B-Spline or NURBS
            return self.create_bspline_curve(points, degree, closed)

    # ---------- Main function ----------
    def generate_curves(self):
        axis = self.axis_combo.currentText()
        num_sections = self.count_spin.value()
        degree = self.degree_spin.value()
        close_thresh = self.close_thresh_spin.value()
        closed_enabled = self.closed_check.isChecked()
        curve_type = self.curve_combo.currentText()

        self.progress.setVisible(True)
        self.progress.setRange(0, num_sections)
        self.cancel_btn.setVisible(True)
        self.btn_run.setEnabled(False)
        self.is_cancelled = False
        self.start_time = time.time()

        self.debug_print("=== Starting REAL cross-section algorithm ===")

        doc = App.ActiveDocument
        
        # Create group
        group_name = f"{axis}_{curve_type}"
        group = None
        for obj in doc.Objects:
            if hasattr(obj, "Group") and obj.Name == group_name:
                group = obj
                break
        if not group:
            group = doc.addObject("App::DocumentObjectGroup", group_name)
            self.debug_print(f"Created group: {group_name}")

        facets = self.mesh.Facets
        points = [v.Vector for v in self.mesh.Points]

        if axis == "X":
            dmin, dmax = self.bbox.XMin, self.bbox.XMax
        elif axis == "Y":
            dmin, dmax = self.bbox.YMin, self.bbox.YMax
        else:
            dmin, dmax = self.bbox.ZMin, self.bbox.ZMax
        length = dmax - dmin
        pad = length * 0.02
        start = dmin + pad
        end = dmax - pad
        step = (end - start) / (num_sections - 1) if num_sections > 1 else 0

        created = 0
        closed_count = 0
        failed = 0

        for idx in range(num_sections):
            if self.is_cancelled:
                break
            self.progress.setValue(idx + 1)
            target = start + idx * step

            self.debug_print(f"Section {idx+1}/{num_sections} at {target:.2f}")

            segments = []
            for facet in facets:
                v1 = points[facet.PointIndices[0]]
                v2 = points[facet.PointIndices[1]]
                v3 = points[facet.PointIndices[2]]
                segs = self.intersect_triangle_with_plane(v1, v2, v3, axis, target)
                if segs:
                    segments.extend(segs)

            if not segments:
                self.debug_print("  No intersections")
                failed += 1
                continue

            self.debug_print(f"  {len(segments)} segments")

            chains = self.build_chains(segments, close_thresh)
            self.debug_print(f"  {len(chains)} chain(s)")

            for ci, chain_pts in enumerate(chains):
                if len(chain_pts) < 3:
                    continue

                # Determine if closed
                is_closed = False
                if closed_enabled:
                    dist = (chain_pts[0] - chain_pts[-1]).Length
                    if dist <= close_thresh:
                        is_closed = True
                        self.debug_print(f"    Chain {ci+1}: {len(chain_pts)} points, closed (dist={dist:.3f})")
                    else:
                        self.debug_print(f"    Chain {ci+1}: {len(chain_pts)} points, open (dist={dist:.3f})")
                else:
                    self.debug_print(f"    Chain {ci+1}: {len(chain_pts)} points, open (closure disabled)")

                # If closed, ensure start == end
                if is_closed and (chain_pts[-1] - chain_pts[0]).Length > 1e-6:
                    chain_pts.append(chain_pts[0])
                    self.debug_print("    Forced closure by appending start point")

                shape = self.create_curve(chain_pts, degree, is_closed, curve_type)
                if shape:
                    name = f"{axis}_{idx+1}_{ci+1}{'_Closed' if is_closed else ''}"
                    obj = doc.addObject("Part::Feature", name)
                    obj.Shape = shape
                    obj.ViewObject.ShapeColor = (0.2, 0.8, 0.2) if is_closed else (0.6, 0.6, 0.1)
                    group.addObject(obj)
                    created += 1
                    if is_closed:
                        closed_count += 1
                    self.debug_print(f"    Created {name} ({len(chain_pts)} pts)")
                else:
                    failed += 1

        doc.recompute()
        self.progress.setVisible(False)
        self.cancel_btn.setVisible(False)
        self.btn_run.setEnabled(True)
        Gui.Control.closeDialog()

        elapsed = time.time() - self.start_time
        msg = f"Done! {created} curves ({closed_count} closed), {failed} failed.\nTime: {elapsed:.1f}s"
        self.debug_print(msg)
        QtWidgets.QMessageBox.information(None, "Status", msg)

    def getStandardButtons(self):
        return QtWidgets.QDialogButtonBox.StandardButton.Close

# Execute
if App.ActiveDocument:
    panel = KCICrossSectionCurves()
    if hasattr(panel, 'form'):
        Gui.Control.showDialog(panel)
