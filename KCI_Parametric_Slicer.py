import FreeCAD as App
import FreeCADGui as Gui
import Part
import math

try:
    from PySide6 import QtCore, QtGui, QtWidgets
except ImportError:
    try:
        from PySide2 import QtCore, QtGui, QtWidgets
    except ImportError:
        from PySide import QtCore, QtGui
        QtWidgets = QtGui

class KCIParametricSlicer:
    def __init__(self):
        selection = Gui.Selection.getSelection()
        if not selection or not hasattr(selection[0], "Mesh"):
            QtWidgets.QMessageBox.critical(None, "Error", "Please select a Mesh object from the tree or 3D view!")
            return
        
        self.mesh_obj = selection[0]
        self.mesh_data = self.mesh_obj.Mesh
        self.bbox = self.mesh_data.BoundBox
        
        # Task Panel User Interface
        self.form = QtWidgets.QWidget()
        self.form.setWindowTitle("KCI Parametric Slicer")
        layout = QtWidgets.QVBoxLayout(self.form)
        
        # Mesh Info Group
        info_group = QtWidgets.QGroupBox("Mesh Information")
        info_layout = QtWidgets.QGridLayout(info_group)
        info_layout.addWidget(QtWidgets.QLabel(f"X Length: {self.bbox.XLength:.2f} mm"), 0, 0)
        info_layout.addWidget(QtWidgets.QLabel(f"Y Length: {self.bbox.YLength:.2f} mm"), 1, 0)
        info_layout.addWidget(QtWidgets.QLabel(f"Z Length: {self.bbox.ZLength:.2f} mm"), 2, 0)
        layout.addWidget(info_group)
        
        # B-Spline Configuration Group
        settings_group = QtWidgets.QGroupBox("KCI Engine Geometry Settings")
        form_layout = QtWidgets.QFormLayout(settings_group)
        
        # Slicing Axis Combo Box
        self.axis_combo = QtWidgets.QComboBox()
        self.axis_combo.addItems(["X-Axis", "Y-Axis", "Z-Axis"])
        form_layout.addRow("Slicing Axis Orientation:", self.axis_combo)
        
        self.count_spin = QtWidgets.QSpinBox()
        self.count_spin.setRange(2, 100)
        self.count_spin.setValue(12)
        form_layout.addRow("Number of Sections:", self.count_spin)
        
        self.tol_spin = QtWidgets.QDoubleSpinBox()
        self.tol_spin.setRange(0.05, 10.0)
        self.tol_spin.setValue(1.5)
        form_layout.addRow("Corridor Tolerance (W - mm):", self.tol_spin)
        
        self.radius_spin = QtWidgets.QDoubleSpinBox()
        self.radius_spin.setRange(0.5, 50.0)
        self.radius_spin.setValue(6.0)
        form_layout.addRow("Max Search Radius (R - mm):", self.radius_spin)
        
        self.step_spin = QtWidgets.QDoubleSpinBox()
        self.step_spin.setRange(0.1, 20.0)
        self.step_spin.setValue(3.0)
        self.step_spin.setToolTip("Minimum distance between nodes. Higher values result in smoother curves.")
        form_layout.addRow("Suppression Distance (mm):", self.step_spin)
        
        layout.addWidget(settings_group)
        
        # Execution Button
        self.btn_run = QtWidgets.QPushButton("Execute KCI Spline Generation")
        self.btn_run.setStyleSheet("font-weight: bold; background-color: #2ecc71; color: white; padding: 6px;")
        self.btn_run.clicked.connect(self.generate_bspline_curves)
        layout.addWidget(self.btn_run)
        
    def generate_bspline_curves(self):
        selected_axis_str = self.axis_combo.currentText()
        axis = selected_axis_str.split("-")[0] # "X", "Y", "Z"
        
        num_sections = self.count_spin.value()
        strip_width = self.tol_spin.value()
        search_radius = self.radius_spin.value()
        min_step = self.step_spin.value()
        
        r_squared = search_radius ** 2
        min_step_squared = min_step ** 2
        
        doc = App.ActiveDocument
        doc.openTransaction("KCI_Parametric_Slice_Operation")
        
        vertices = [v.Vector for v in self.mesh_data.Points]
        
        if axis == "X":
            dim_min, dim_max, dim_length = self.bbox.XMin, self.bbox.XMax, self.bbox.XLength
        elif axis == "Y":
            dim_min, dim_max, dim_length = self.bbox.YMin, self.bbox.YMax, self.bbox.YLength
        else: # Z
            dim_min, dim_max, dim_length = self.bbox.ZMin, self.bbox.ZMax, self.bbox.ZLength
            
        pad = dim_length * 0.02
        start_pos = dim_min + pad
        end_pos = dim_max - pad
        step_pos = (end_pos - start_pos) / (num_sections - 1) if num_sections > 1 else 0
        
        created_count = 0
        
        for idx in range(num_sections):
            target_val = start_pos + (idx * step_pos)
            projected_pool = []
            
            # STEP 1: Slicing corridor projection filter
            for v in vertices:
                if axis == "X" and abs(v.x - target_val) <= strip_width:
                    projected_pool.append(App.Vector(target_val, v.y, v.z))
                elif axis == "Y" and abs(v.y - target_val) <= strip_width:
                    projected_pool.append(App.Vector(v.x, target_val, v.z))
                elif axis == "Z" and abs(v.z - target_val) <= strip_width:
                    projected_pool.append(App.Vector(v.x, v.y, target_val))
            
            if len(projected_pool) < 3:
                continue
                
            unvisited = list(projected_pool)
            section_spline_index = 1
            
            # Continuous scanning across gaps within the bounding box limit
            while len(unvisited) >= 3:
                initial_pool_size = len(unvisited) # Kilitlenme takip eşiği
                
                # Find the next logical starting point based on the current active plane alignment
                if axis == "X":
                    start_node = min(unvisited, key=lambda p: p.y)
                elif axis == "Y":
                    start_node = min(unvisited, key=lambda p: p.x)
                else: # Z
                    start_node = min(unvisited, key=lambda p: p.x)
                    
                curve_points = [start_node]
                
                # Suppression filtering for the initial start node cluster
                if axis == "X":
                    unvisited = [p for p in unvisited if (p.y - start_node.y)**2 + (p.z - start_node.z)**2 >= min_step_squared]
                elif axis == "Y":
                    unvisited = [p for p in unvisited if (p.x - start_node.x)**2 + (p.z - start_node.z)**2 >= min_step_squared]
                else: # Z
                    unvisited = [p for p in unvisited if (p.x - start_node.x)**2 + (p.y - start_node.y)**2 >= min_step_squared]
                    
                current_node = start_node
                prev_dir = None
                
                # STEP 2: Chain Tracking Routine
                while len(unvisited) > 0:
                    candidates = []
                    for p in unvisited:
                        if axis == "X":
                            dist_sq = (p.y - current_node.y)**2 + (p.z - current_node.z)**2
                        elif axis == "Y":
                            dist_sq = (p.x - current_node.x)**2 + (p.z - current_node.z)**2
                        else: # Z
                            dist_sq = (p.x - current_node.x)**2 + (p.y - current_node.y)**2
                            
                        if dist_sq <= r_squared:
                            candidates.append((p, dist_sq))
                    
                    if not candidates:
                        break
                    
                    best_cand = None
                    
                    if prev_dir is None:
                        best_cand = min(candidates, key=lambda item: item[1])[0]
                        if axis == "X":
                            prev_dir = App.Vector(0, best_cand.y - current_node.y, best_cand.z - current_node.z)
                        elif axis == "Y":
                            prev_dir = App.Vector(best_cand.x - current_node.x, 0, best_cand.z - current_node.z)
                        else: # Z
                            prev_dir = App.Vector(best_cand.x - current_node.x, best_cand.y - current_node.y, 0)
                            
                        if prev_dir.Length > 0:
                            prev_dir.normalize()
                    else:
                        best_score = -2.0
                        for cand, d_sq in candidates:
                            if axis == "X":
                                v_cand = App.Vector(0, cand.y - current_node.y, cand.z - current_node.z)
                            elif axis == "Y":
                                v_cand = App.Vector(cand.x - current_node.x, 0, cand.z - current_node.z)
                            else: # Z
                                v_cand = App.Vector(cand.x - current_node.x, cand.y - current_node.y, 0)
                                
                            if v_cand.Length == 0:
                                continue
                            v_cand.normalize()
                            
                            dot = prev_dir.dot(v_cand)
                            if dot > best_score and dot > 0.1:
                                best_score = dot
                                best_cand = cand
                    
                    if best_cand is None:
                        break
                    
                    if axis == "X":
                        new_dir = App.Vector(0, best_cand.y - current_node.y, best_cand.z - current_node.z)
                    elif axis == "Y":
                        new_dir = App.Vector(best_cand.x - current_node.x, 0, best_cand.z - current_node.z)
                    else: # Z
                        new_dir = App.Vector(best_cand.x - current_node.x, best_cand.y - current_node.y, 0)
                        
                    if new_dir.Length > 0:
                        new_dir.normalize()
                        prev_dir = new_dir
                    
                    curve_points.append(best_cand)
                    current_node = best_cand
                    
                    if axis == "X":
                        unvisited = [p for p in unvisited if (p.y - current_node.y)**2 + (p.z - current_node.z)**2 >= min_step_squared]
                    elif axis == "Y":
                        unvisited = [p for p in unvisited if (p.x - current_node.x)**2 + (p.z - current_node.z)**2 >= min_step_squared]
                    else: # Z
                        unvisited = [p for p in unvisited if (p.x - current_node.x)**2 + (p.y - current_node.y)**2 >= min_step_squared]
                
                # STEP 3: Sub-Spline Generation
                if len(curve_points) >= 3:
                    try:
                        bspline_curve = Part.BSplineCurve()
                        bspline_curve.interpolate(curve_points)
                        
                        curve_shape = bspline_curve.toShape()
                        curve_obj = doc.addObject("Part::Feature", f"KCI_Spline_{axis}_{idx+1}_Part_{section_spline_index}")
                        curve_obj.Shape = curve_shape
                        created_count += 1
                        section_spline_index += 1
                    except Exception as e:
                        App.Console.PrintWarning(f"KCI Engine: Failed to generate B-Spline segment: {str(e)}\n")
                
                # Kesin Döngü Koruması: Havuz küçülmediyse start_node'u güvenli bir şekilde listeden temizle
                if len(unvisited) == initial_pool_size and start_node in unvisited:
                    unvisited.remove(start_node)
                        
        doc.recompute()
        Gui.Control.closeDialog()
        
        QtWidgets.QMessageBox.information(
            None, "KCI Engine Status", f"Operation completed successfully!\nGenerated {created_count} perfectly smoothed native B-Spline curves across all gaps."
        )

    def getStandardButtons(self):
        return int(QtWidgets.QDialogButtonBox.Close)

# Execute Macro
if doc := App.ActiveDocument:
    panel = KCIParametricSlicer()
    if hasattr(panel, 'form'):
        Gui.Control.showDialog(panel)
