import FreeCAD as App
import FreeCADGui as Gui
import Part
from typing import List, Tuple, Optional
from enum import Enum

try:
    from PySide6 import QtCore, QtGui, QtWidgets
except ImportError:
    try:
        from PySide2 import QtCore, QtGui, QtWidgets
    except ImportError:
        from PySide import QtCore, QtGui
        QtWidgets = QtGui


class SliceAxis(Enum):
    """Kesit ekseni tanımı"""
    X = "X"
    Y = "Y"
    Z = "Z"


class KCIParametricNURBSSurface:
    """
    KCI NURBS Yüzey Oluşturucu - Mesh yüzeyine yapışan NURBS yüzey oluşturur
    Spline eğrileri kullanarak yüzeyi mesh'in üzerine sarıyor
    """
    
    def __init__(self):
        self.mesh_obj = None
        self.mesh_data = None
        self.bbox = None
        self.form = None
        self.transaction_name = "KCI_NURBS_Yüzey_İşlemi"
        
        self._init_mesh()
        if self.mesh_obj:
            self._create_ui()
    
    def _init_mesh(self) -> bool:
        """Mesh nesnesini seçimden yükle"""
        selection = Gui.Selection.getSelection()
        if not selection or not hasattr(selection[0], "Mesh"):
            QtWidgets.QMessageBox.critical(
                None, "Hata", 
                "Lütfen ağaç veya 3D görünümden bir Mesh nesnesi seçin!"
            )
            return False
        
        self.mesh_obj = selection[0]
        self.mesh_data = self.mesh_obj.Mesh
        self.bbox = self.mesh_data.BoundBox
        return True
    
    def _create_ui(self):
        """Kullanıcı arayüzünü oluştur"""
        self.form = QtWidgets.QWidget()
        self.form.setWindowTitle("KCI NURBS Yüzey Oluşturucu")
        layout = QtWidgets.QVBoxLayout(self.form)
        
        # Mesh Bilgisi Grubu
        info_group = self._create_mesh_info_group()
        layout.addWidget(info_group)
        
        # Ayarlar Grubu
        settings_group = self._create_settings_group()
        layout.addWidget(settings_group)
        
        # İleri Ayarlar Grubu
        advanced_group = self._create_advanced_settings_group()
        layout.addWidget(advanced_group)
        
        # Butonlar Grubu
        button_group = self._create_button_group()
        layout.addWidget(button_group)
        
        # Spacer
        layout.addStretch()
    
    def _create_mesh_info_group(self) -> QtWidgets.QGroupBox:
        """Mesh bilgi grubunu oluştur"""
        group = QtWidgets.QGroupBox("Mesh Bilgisi")
        layout = QtWidgets.QGridLayout(group)
        
        num_vertices = len(self.mesh_data.Points)
        num_faces = len(self.mesh_data.Facets)
        
        layout.addWidget(QtWidgets.QLabel(f"Vertex Sayısı: {num_vertices}"), 0, 0)
        layout.addWidget(QtWidgets.QLabel(f"Yüz Sayısı: {num_faces}"), 1, 0)
        layout.addWidget(
            QtWidgets.QLabel(f"X Uzunluğu: {self.bbox.XLength:.2f} mm"), 0, 1
        )
        layout.addWidget(
            QtWidgets.QLabel(f"Y Uzunluğu: {self.bbox.YLength:.2f} mm"), 1, 1
        )
        layout.addWidget(
            QtWidgets.QLabel(f"Z Uzunluğu: {self.bbox.ZLength:.2f} mm"), 2, 1
        )
        
        return group
    
    def _create_settings_group(self) -> QtWidgets.QGroupBox:
        """Temel ayarlar grubunu oluştur"""
        group = QtWidgets.QGroupBox("NURBS Yüzey Parametreleri")
        layout = QtWidgets.QFormLayout(group)
        
        # Eksen seçimi
        self.axis_combo = QtWidgets.QComboBox()
        self.axis_combo.addItems(["X-Ekseni", "Y-Ekseni", "Z-Ekseni"])
        layout.addRow("Kesit Ekseni:", self.axis_combo)
        
        # U-Yönü (Kesit sayısı) - Y veya X
        self.u_count_spin = QtWidgets.QSpinBox()
        self.u_count_spin.setRange(3, 50)
        self.u_count_spin.setValue(12)
        self.u_count_spin.setToolTip("Eksen yönündeki kesit sayısı")
        layout.addRow("U Yönü - Kesit Sayısı:", self.u_count_spin)
        
        # V-Yönü (Eğri üstündeki nokta sayısı)
        self.v_count_spin = QtWidgets.QSpinBox()
        self.v_count_spin.setRange(3, 100)
        self.v_count_spin.setValue(20)
        self.v_count_spin.setToolTip("Her kesit üstündeki nokta sayısı")
        layout.addRow("V Yönü - Nokta Sayısı:", self.v_count_spin)
        
        # Koridor toleransı
        self.tol_spin = QtWidgets.QDoubleSpinBox()
        self.tol_spin.setRange(0.05, 10.0)
        self.tol_spin.setValue(1.5)
        self.tol_spin.setToolTip("Kesit düzleminin genişliği")
        layout.addRow("Koridor Toleransı (mm):", self.tol_spin)
        
        # Arama yarıçapı
        self.radius_spin = QtWidgets.QDoubleSpinBox()
        self.radius_spin.setRange(0.5, 50.0)
        self.radius_spin.setValue(6.0)
        self.radius_spin.setToolTip("Nokta arama mesafesi")
        layout.addRow("Maksimum Arama Yarıçapı (mm):", self.radius_spin)
        
        return group
    
    def _create_advanced_settings_group(self) -> QtWidgets.QGroupBox:
        """İleri ayarlar grubunu oluştur"""
        group = QtWidgets.QGroupBox("İleri Ayarlar")
        layout = QtWidgets.QFormLayout(group)
        
        # Bastırma mesafesi
        self.step_spin = QtWidgets.QDoubleSpinBox()
        self.step_spin.setRange(0.1, 20.0)
        self.step_spin.setValue(2.0)
        self.step_spin.setToolTip("Düğümler arasında minimum mesafe")
        layout.addRow("Bastırma Mesafesi (mm):", self.step_spin)
        
        # Yüzey derecesi U
        self.u_degree_spin = QtWidgets.QSpinBox()
        self.u_degree_spin.setRange(1, 5)
        self.u_degree_spin.setValue(3)
        self.u_degree_spin.setToolTip("U yönü spline derecesi (1-5)")
        layout.addRow("U Yönü Derece:", self.u_degree_spin)
        
        # Yüzey derecesi V
        self.v_degree_spin = QtWidgets.QSpinBox()
        self.v_degree_spin.setRange(1, 5)
        self.v_degree_spin.setValue(3)
        self.v_degree_spin.setToolTip("V yönü spline derecesi (1-5)")
        layout.addRow("V Yönü Derece:", self.v_degree_spin)
        
        # Parazit nokta filtreleme
        self.filter_outliers_check = QtWidgets.QCheckBox("Parazit Noktaları Filtrele")
        self.filter_outliers_check.setChecked(True)
        self.filter_outliers_check.setToolTip("Izole noktaları ve gürültüyü kaldır")
        layout.addRow("", self.filter_outliers_check)
        
        # Yüzey düşletme
        self.smooth_check = QtWidgets.QCheckBox("Yüzey Düzeltmesi Uygula")
        self.smooth_check.setChecked(True)
        layout.addRow("", self.smooth_check)
        
        # Otomatik kaydet
        self.auto_save_check = QtWidgets.QCheckBox("İşlem Sonrası Otomatik Kaydet")
        self.auto_save_check.setChecked(True)
        layout.addRow("", self.auto_save_check)
        
        return group
    
    def _create_button_group(self) -> QtWidgets.QGroupBox:
        """Buton grubunu oluştur"""
        group = QtWidgets.QGroupBox()
        layout = QtWidgets.QHBoxLayout(group)
        
        # NURBS Oluştur Butonu
        self.btn_run = QtWidgets.QPushButton("NURBS Yüzey Oluştur")
        self.btn_run.setStyleSheet(
            "font-weight: bold; background-color: #3498db; color: white; padding: 8px; font-size: 12px;"
        )
        self.btn_run.clicked.connect(self.generate_nurbs_surface)
        layout.addWidget(self.btn_run)
        
        # Geri Al Butonu
        self.btn_undo = QtWidgets.QPushButton("Geri Al (Undo)")
        self.btn_undo.setStyleSheet(
            "font-weight: bold; background-color: #95a5a6; color: white; padding: 8px; font-size: 12px;"
        )
        self.btn_undo.clicked.connect(self.undo_operation)
        layout.addWidget(self.btn_undo)
        
        # Kaydet Butonu
        self.btn_save = QtWidgets.QPushButton("Kaydet")
        self.btn_save.setStyleSheet(
            "font-weight: bold; background-color: #27ae60; color: white; padding: 8px; font-size: 12px;"
        )
        self.btn_save.clicked.connect(self.save_document)
        layout.addWidget(self.btn_save)
        
        return group
    
    def _get_axis_params(self, axis: SliceAxis) -> Tuple[float, float, float]:
        """Eksen parametrelerini al"""
        if axis == SliceAxis.X:
            return self.bbox.XMin, self.bbox.XMax, self.bbox.XLength
        elif axis == SliceAxis.Y:
            return self.bbox.YMin, self.bbox.YMax, self.bbox.YLength
        else:
            return self.bbox.ZMin, self.bbox.ZMax, self.bbox.ZLength
    
    def _get_distance_squared(self, p: App.Vector, current: App.Vector, 
                             axis: SliceAxis) -> float:
        """Eksen bağlı 2D mesafe karesi hesapla"""
        if axis == SliceAxis.X:
            return (p.y - current.y)**2 + (p.z - current.z)**2
        elif axis == SliceAxis.Y:
            return (p.x - current.x)**2 + (p.z - current.z)**2
        else:
            return (p.x - current.x)**2 + (p.y - current.y)**2
    
    def _get_direction_vector(self, from_p: App.Vector, to_p: App.Vector, 
                             axis: SliceAxis) -> App.Vector:
        """Eksen bağlı yön vektörü hesapla"""
        if axis == SliceAxis.X:
            return App.Vector(0, to_p.y - from_p.y, to_p.z - from_p.z)
        elif axis == SliceAxis.Y:
            return App.Vector(to_p.x - from_p.x, 0, to_p.z - from_p.z)
        else:
            return App.Vector(to_p.x - from_p.x, to_p.y - from_p.y, 0)
    
    def _get_start_node(self, points: List[App.Vector], 
                       axis: SliceAxis) -> App.Vector:
        """Başlangıç düğümünü seç"""
        if axis == SliceAxis.X:
            return min(points, key=lambda p: (p.y, p.z))
        elif axis == SliceAxis.Y:
            return min(points, key=lambda p: (p.x, p.z))
        else:
            return min(points, key=lambda p: (p.x, p.y))
    
    def _filter_points_by_distance(self, points: List[App.Vector], 
                                   reference: App.Vector, min_dist_sq: float, 
                                   axis: SliceAxis) -> List[App.Vector]:
        """Mesafe kontrolüne göre noktaları filtrele"""
        return [
            p for p in points
            if self._get_distance_squared(p, reference, axis) >= min_dist_sq
        ]
    
    def _project_to_plane(self, v: App.Vector, target_val: float, 
                         axis: SliceAxis) -> App.Vector:
        """Noktayı kesit düzlemine project et"""
        if axis == SliceAxis.X:
            return App.Vector(target_val, v.y, v.z)
        elif axis == SliceAxis.Y:
            return App.Vector(v.x, target_val, v.z)
        else:
            return App.Vector(v.x, v.y, target_val)
    
    def _is_in_corridor(self, v: App.Vector, target_val: float, 
                       tolerance: float, axis: SliceAxis) -> bool:
        """Noktanın koridor içinde olup olmadığını kontrol et"""
        if axis == SliceAxis.X:
            return abs(v.x - target_val) <= tolerance
        elif axis == SliceAxis.Y:
            return abs(v.y - target_val) <= tolerance
        else:
            return abs(v.z - target_val) <= tolerance
    
    def _filter_outliers(self, points: List[App.Vector], axis: SliceAxis) -> List[App.Vector]:
        """Parazit ve izole noktaları filtrele"""
        if len(points) < 5:
            return points
        
        # Her nokta için komşu sayısını hesapla
        min_radius = max([
            self.bbox.XLength, 
            self.bbox.YLength, 
            self.bbox.ZLength
        ]) * 0.05
        
        filtered = []
        for p in points:
            # Minimum 2 komşu varsa noktayı tut
            neighbors = sum(1 for q in points if q.distanceToPoint(p) < min_radius and p != q)
            if neighbors >= 2 or len(points) < 10:
                filtered.append(p)
        
        return filtered if filtered else points
    
    def _create_spline_curve(self, points: List[App.Vector]) -> Optional[Part.BSplineCurve]:
        """Noktalardan B-spline eğrisi oluştur"""
        try:
            if len(points) < 3:
                return None
            
            # Parazit noktaları filtrele
            if self.filter_outliers_check.isChecked():
                points = self._filter_outliers(points, self._get_current_axis())
            
            if len(points) < 3:
                return None
            
            bspline = Part.BSplineCurve()
            bspline.interpolate(points)
            return bspline
            
        except Exception as e:
            App.Console.PrintWarning(f"Spline oluşturulamadı: {str(e)}\n")
            return None
    
    def _create_nurbs_surface_from_curves(self, curves: List[Part.BSplineCurve], 
                                         doc: App.Document) -> Optional[object]:
        """B-spline eğrilerinden NURBS yüzey oluştur"""
        try:
            if len(curves) < 3:
                return None
            
            # Eğrileri yüzeye dönüştür
            u_degree = min(self.u_degree_spin.value(), len(curves) - 1)
            v_degree = self.v_degree_spin.value()
            
            nurbs_surface = Part.BSplineSurface()
            
            # Tüm eğrilerin noktalarını al
            all_points = []
            for curve in curves:
                points = []
                for i in range(self.v_count_spin.value()):
                    param = i / (self.v_count_spin.value() - 1) if self.v_count_spin.value() > 1 else 0
                    points.append(curve.valueAt(param))
                all_points.append(points)
            
            # NURBS yüzey oluştur
            nurbs_surface.interpolate(all_points, u_degree, v_degree)
            
            # Yüzey nesnesini belgede oluştur
            surface_obj = doc.addObject("Part::Feature", "KCI_NURBS_Surface")
            surface_obj.Shape = nurbs_surface.toShape()
            
            return surface_obj
            
        except Exception as e:
            App.Console.PrintWarning(f"NURBS yüzey oluşturulamadı: {str(e)}\n")
            return None
    
    def _select_best_candidate(self, candidates: List[Tuple[App.Vector, float]], 
                              current_node: App.Vector, prev_dir: Optional[App.Vector],
                              axis: SliceAxis) -> Optional[App.Vector]:
        """En iyi adayı seç"""
        if prev_dir is None:
            return min(candidates, key=lambda item: item[1])[0]
        
        best_score = -2.0
        best_cand = None
        
        for cand, _ in candidates:
            v_cand = self._get_direction_vector(current_node, cand, axis)
            if v_cand.Length == 0:
                continue
            
            v_cand.normalize()
            dot = prev_dir.dot(v_cand)
            
            if dot > best_score and dot > 0.1:
                best_score = dot
                best_cand = cand
        
        return best_cand
    
    def _get_current_axis(self) -> SliceAxis:
        """Mevcut eksen seçimini al"""
        axis_text = self.axis_combo.currentText()
        return SliceAxis[axis_text.split("-")[0]]
    
    def save_document(self):
        """Belgesi kaydet - güvenli şekilde"""
        try:
            doc = App.ActiveDocument
            if doc is None:
                QtWidgets.QMessageBox.warning(None, "Uyarı", "Aktif belge bulunamadı!")
                return
            
            doc.save()
            App.Console.PrintMessage(f"Belge kaydedildi: {doc.FileName}\n")
            QtWidgets.QMessageBox.information(None, "Başarılı", "Belge başarıyla kaydedildi!")
            
        except Exception as e:
            App.Console.PrintError(f"Kaydetme hatası: {str(e)}\n")
            QtWidgets.QMessageBox.critical(None, "Hata", f"Kaydetme başarısız:\n{str(e)}")
    
    def undo_operation(self):
        """Son işlemi geri al"""
        try:
            doc = App.ActiveDocument
            if doc:
                doc.undo()
                App.Console.PrintMessage("Son işlem geri alındı\n")
        except Exception as e:
            App.Console.PrintError(f"Geri alma hatası: {str(e)}\n")
            QtWidgets.QMessageBox.warning(None, "Uyarı", f"Geri alma başarısız:\n{str(e)}")
    
    def generate_nurbs_surface(self):
        """Ana NURBS yüzey oluşturma fonksiyonu"""
        try:
            axis = self._get_current_axis()
            
            num_sections = self.u_count_spin.value()
            strip_width = self.tol_spin.value()
            search_radius = self.radius_spin.value()
            min_step = self.step_spin.value()
            
            r_squared = search_radius ** 2
            min_step_squared = min_step ** 2
            
            doc = App.ActiveDocument
            doc.openTransaction(self.transaction_name)
            
            vertices = [v.Vector for v in self.mesh_data.Points]
            dim_min, dim_max, dim_length = self._get_axis_params(axis)
            
            pad = dim_length * 0.02
            start_pos = dim_min + pad
            end_pos = dim_max - pad
            step_pos = (end_pos - start_pos) / (num_sections - 1) if num_sections > 1 else 0
            
            all_spline_curves = []
            
            # Her kesit düzlemi için spline eğrisi oluştur
            for idx in range(num_sections):
                target_val = start_pos + (idx * step_pos)
                
                # Adım 1: Koridor filtrelemesi
                projected_pool = [
                    self._project_to_plane(v, target_val, axis)
                    for v in vertices
                    if self._is_in_corridor(v, target_val, strip_width, axis)
                ]
                
                if len(projected_pool) < 3:
                    continue
                
                unvisited = list(projected_pool)
                
                # Adım 2: En büyük eğriyi bul
                best_curve_points = []
                best_curve_length = 0
                
                while len(unvisited) >= 3:
                    initial_pool_size = len(unvisited)
                    start_node = self._get_start_node(unvisited, axis)
                    curve_points = [start_node]
                    
                    unvisited = self._filter_points_by_distance(
                        unvisited, start_node, min_step_squared, axis
                    )
                    
                    current_node = start_node
                    prev_dir = None
                    
                    # Adım 3: Zincir takibi
                    while len(unvisited) > 0:
                        candidates = [
                            (p, self._get_distance_squared(p, current_node, axis))
                            for p in unvisited
                            if self._get_distance_squared(p, current_node, axis) <= r_squared
                        ]
                        
                        if not candidates:
                            break
                        
                        best_cand = self._select_best_candidate(
                            candidates, current_node, prev_dir, axis
                        )
                        
                        if best_cand is None:
                            break
                        
                        new_dir = self._get_direction_vector(current_node, best_cand, axis)
                        if new_dir.Length > 0:
                            new_dir.normalize()
                            prev_dir = new_dir
                        
                        curve_points.append(best_cand)
                        current_node = best_cand
                        
                        unvisited = self._filter_points_by_distance(
                            unvisited, current_node, min_step_squared, axis
                        )
                    
                    # En uzun eğriyi seç
                    if len(curve_points) > len(best_curve_points):
                        best_curve_points = curve_points
                    
                    if len(unvisited) == initial_pool_size and start_node in unvisited:
                        unvisited.remove(start_node)
                
                # Eğri yeterli nokta içeriyorsa spline oluştur
                if len(best_curve_points) >= 3:
                    spline = self._create_spline_curve(best_curve_points)
                    if spline:
                        all_spline_curves.append(spline)
            
            # Adım 4: NURBS yüzey oluştur
            if len(all_spline_curves) >= 3:
                surface = self._create_nurbs_surface_from_curves(all_spline_curves, doc)
                
                if surface:
                    # Yüzey düzeltmesi uygula
                    if self.smooth_check.isChecked():
                        try:
                            # Mesh'e dönüştür ve geri dönüştür (düzeltme işlemi)
                            mesh = surface.Shape.toMesh(0.5)
                            surface.Shape = mesh.toShape()
                        except:
                            pass
                    
                    doc.recompute()
                    doc.commitTransaction()
                    
                    # Otomatik kaydet
                    if self.auto_save_check.isChecked():
                        self.save_document()
                    
                    Gui.Control.closeDialog()
                    
                    QtWidgets.QMessageBox.information(
                        None, "KCI Başarılı",
                        f"İşlem tamamlandı!\n"
                        f"{len(all_spline_curves)} kesit eğrisinden\n"
                        f"NURBS yüzeyi oluşturuldu."
                    )
                else:
                    doc.abortTransaction()
                    QtWidgets.QMessageBox.warning(
                        None, "Uyarı", "NURBS yüzey oluşturulamadı"
                    )
            else:
                doc.abortTransaction()
                QtWidgets.QMessageBox.warning(
                    None, "Uyarı", f"Yeterli kesit eğrisi bulunamadı ({len(all_spline_curves)})"
                )
            
        except Exception as e:
            try:
                doc = App.ActiveDocument
                if doc:
                    doc.abortTransaction()
            except:
                pass
            
            App.Console.PrintError(f"KCI Hata: {str(e)}\n")
            QtWidgets.QMessageBox.critical(None, "Hata", f"İşlem başarısız:\n{str(e)}")
    
    def getStandardButtons(self):
        """Dialog butonlarını döndür"""
        return int(QtWidgets.QDialogButtonBox.Close)


# Makroyu çalıştır
if doc := App.ActiveDocument:
    panel = KCIParametricNURBSSurface()
    if hasattr(panel, 'form') and panel.form:
        Gui.Control.showDialog(panel)
