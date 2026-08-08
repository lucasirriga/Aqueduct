import os
import math
from qgis.PyQt.QtWidgets import (
    QAction, QDialog, QVBoxLayout, QFormLayout, QComboBox, QDoubleSpinBox,
    QPushButton, QMessageBox, QLabel, QGroupBox
)
from qgis.PyQt.QtGui import QIcon
from qgis.core import (
    QgsMapLayerType, QgsProject, QgsWkbTypes, QgsVectorLayer, QgsFeature,
    QgsGeometry, QgsField
)
from qgis.PyQt.QtCore import QVariant

from .ferramenta_base import AqueductTool


class GradeObliquaPontosDialog(QDialog):
    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.setWindowTitle("Aqueduct - Grade Nao Ortogonal (Pontos)")
        self.resize(420, 380)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout()

        layout.addWidget(QLabel(
            "<b>1. Camada de Linhas (2 feicoes):</b><br>"
            "As duas linhas definem as direcoes da grade - nao precisam ser perpendiculares."
        ))
        self.combo_line = QComboBox()
        layout.addWidget(self.combo_line)
        self.lbl_line_info = QLabel("")
        self.lbl_line_info.setWordWrap(True)
        layout.addWidget(self.lbl_line_info)

        layout.addWidget(QLabel("<b>2. Poligono de Recorte:</b>"))
        self.combo_poly = QComboBox()
        layout.addWidget(self.combo_poly)

        self.populate_layers()
        self.combo_line.currentIndexChanged.connect(self.update_line_info)
        self.update_line_info()

        group_dims = QGroupBox("3. Espacamento entre linhas paralelas (m)")
        form_dims = QFormLayout()

        self.spin_spacing1 = QDoubleSpinBox()
        self.spin_spacing1.setRange(0.0001, 10000.0)
        self.spin_spacing1.setDecimals(4)
        self.spin_spacing1.setValue(10.0)
        self.spin_spacing1.setSuffix(" m")

        self.spin_spacing2 = QDoubleSpinBox()
        self.spin_spacing2.setRange(0.0001, 10000.0)
        self.spin_spacing2.setDecimals(4)
        self.spin_spacing2.setValue(10.0)
        self.spin_spacing2.setSuffix(" m")

        form_dims.addRow("Espacamento - Linha 1:", self.spin_spacing1)
        form_dims.addRow("Espacamento - Linha 2:", self.spin_spacing2)

        group_dims.setLayout(form_dims)
        layout.addWidget(group_dims)

        self.btn_run = QPushButton("Gerar Grade de Pontos")
        self.btn_run.clicked.connect(self.run_process)
        layout.addWidget(self.btn_run)

        self.setLayout(layout)

    def populate_layers(self):
        self.combo_line.clear()
        self.combo_poly.clear()

        layers = QgsProject.instance().mapLayers().values()
        for layer in layers:
            if layer.type() == QgsMapLayerType.VectorLayer:
                if layer.geometryType() == QgsWkbTypes.LineGeometry:
                    self.combo_line.addItem(layer.name(), layer)
                elif layer.geometryType() == QgsWkbTypes.PolygonGeometry:
                    self.combo_poly.addItem(layer.name(), layer)

    def update_line_info(self):
        layer = self.combo_line.currentData()
        if not layer:
            self.lbl_line_info.setText("")
            return

        feats = self.get_two_line_features(layer)
        if feats:
            self.lbl_line_info.setText(
                f"Linha 1 = feicao fid {feats[0].id()} | Linha 2 = feicao fid {feats[1].id()}"
            )
        else:
            self.lbl_line_info.setText(
                "⚠ A camada precisa ter exatamente 2 feicoes de linha "
                "(ou exatamente 2 selecionadas)."
            )

    @staticmethod
    def get_two_line_features(line_layer):
        feats = list(line_layer.selectedFeatures())
        if len(feats) != 2:
            if line_layer.featureCount() == 2:
                feats = list(line_layer.getFeatures())
            else:
                return None
        feats.sort(key=lambda f: f.id())
        return feats

    @staticmethod
    def _single_line_geom(geom):
        if geom.isMultipart():
            parts = geom.asMultiPolyline()
            if not parts:
                return None
            return QgsGeometry.fromPolylineXY(parts[0])
        return geom

    @staticmethod
    def _build_line_family(ref_geom, spacing, extension_len, max_lines_per_side):
        extended = QgsGeometry(ref_geom)
        extended.extendLine(extension_len, extension_len)

        lines = [extended]
        for i in range(1, max_lines_per_side):
            dist = i * spacing
            off_pos = extended.offsetCurve(dist, 1, QgsGeometry.JoinStyle.Miter, 5.0)
            if off_pos and not off_pos.isEmpty():
                lines.append(off_pos)
            off_neg = extended.offsetCurve(-dist, 1, QgsGeometry.JoinStyle.Miter, 5.0)
            if off_neg and not off_neg.isEmpty():
                lines.append(off_neg)
        return lines

    @staticmethod
    def _clip_lines_to_polygon(lines, limit_geom):
        out = []
        for line in lines:
            if not line.intersects(limit_geom):
                continue
            clipped = line.intersection(limit_geom)
            if clipped.isEmpty():
                continue
            if clipped.isMultipart():
                for part in clipped.asMultiPolyline():
                    if len(part) >= 2:
                        out.append(QgsGeometry.fromPolylineXY(part))
            elif clipped.type() == QgsWkbTypes.LineGeometry:
                out.append(clipped)
        return out

    @staticmethod
    def _make_line_memlayer(crs, geoms):
        vl = QgsVectorLayer(f"LineString?crs={crs.authid()}", "temp_family", "memory")
        pr = vl.dataProvider()
        feats = []
        for g in geoms:
            f = QgsFeature()
            f.setGeometry(g)
            feats.append(f)
        pr.addFeatures(feats)
        vl.updateExtents()
        return vl

    def compute_points(self):
        line_layer = self.combo_line.currentData()
        poly_layer = self.combo_poly.currentData()

        if not line_layer or not poly_layer:
            return None, "Selecione a camada de linhas e o poligono de recorte."

        feats = self.get_two_line_features(line_layer)
        if not feats:
            return None, "A camada de linhas precisa ter exatamente 2 feicoes (ou 2 selecionadas)."

        geom1 = self._single_line_geom(feats[0].geometry())
        geom2 = self._single_line_geom(feats[1].geometry())
        if geom1 is None or geom2 is None:
            return None, "Nao foi possivel ler a geometria das linhas."

        spacing1 = self.spin_spacing1.value()
        spacing2 = self.spin_spacing2.value()

        limit_features = poly_layer.selectedFeatures()
        if not limit_features:
            limit_features = list(poly_layer.getFeatures())
        if not limit_features:
            return None, "O poligono de recorte nao possui feicoes."

        import processing

        all_points = []
        seen = set()

        for limit_feat in limit_features:
            limit_geom = limit_feat.geometry()
            bbox = limit_geom.boundingBox()
            diag = math.sqrt(bbox.width() ** 2 + bbox.height() ** 2)
            extension_len = max(diag * 1.5, 1000)

            max_lines1 = int((diag / spacing1) * 1.5) + 5
            max_lines2 = int((diag / spacing2) * 1.5) + 5

            family1 = self._build_line_family(geom1, spacing1, extension_len, max_lines1)
            family2 = self._build_line_family(geom2, spacing2, extension_len, max_lines2)

            clipped1 = self._clip_lines_to_polygon(family1, limit_geom)
            clipped2 = self._clip_lines_to_polygon(family2, limit_geom)

            if not clipped1 or not clipped2:
                continue

            vlA = self._make_line_memlayer(poly_layer.crs(), clipped1)
            vlB = self._make_line_memlayer(poly_layer.crs(), clipped2)

            result = processing.run("native:lineintersections", {
                'INPUT': vlA,
                'INTERSECT': vlB,
                'INPUT_FIELDS': [],
                'INTERSECT_FIELDS': [],
                'INTERSECT_FIELDS_PREFIX': '',
                'OUTPUT': 'memory:'
            })
            inter_layer = result['OUTPUT']

            for f in inter_layer.getFeatures():
                g = f.geometry()
                if g is None or g.isEmpty():
                    continue
                pts = g.asMultiPoint() if g.isMultipart() else [g.asPoint()]
                for pt in pts:
                    key = (round(pt.x(), 6), round(pt.y(), 6))
                    if key in seen:
                        continue
                    seen.add(key)
                    all_points.append(pt)

        if not all_points:
            return None, "Nenhuma intersecao encontrada. Verifique as linhas, o poligono e os espacamentos."

        return all_points, None

    def run_process(self):
        points, error = self.compute_points()
        if error:
            QMessageBox.warning(self, "Aviso", error)
            return

        poly_layer = self.combo_poly.currentData()
        crs = poly_layer.crs()

        vl = QgsVectorLayer(f"Point?crs={crs.authid()}", "Grade Nao Ortogonal - Pontos", "memory")
        pr = vl.dataProvider()
        pr.addAttributes([QgsField("ID_Ponto", QVariant.Int)])
        vl.updateFields()

        feats = []
        for i, pt in enumerate(points):
            f = QgsFeature()
            f.setGeometry(QgsGeometry.fromPointXY(pt))
            f.setAttributes([i + 1])
            feats.append(f)

        pr.addFeatures(feats)
        vl.updateExtents()
        QgsProject.instance().addMapLayer(vl)
        self.accept()
        QMessageBox.information(self, "Sucesso", f"{len(feats)} pontos gerados.")


class GradeObliquaPontosTool(AqueductTool):
    def initGui(self):
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons', 'icone_grade_obliqua.svg')
        self.action = QAction(QIcon(icon_path), 'Grade Nao Ortogonal (Pontos)', self.iface.mainWindow())
        self.action.triggered.connect(self.run)

        self.iface.addPluginToMenu('&Aqueduct', self.action)

        if self.toolbar:
            self.toolbar.addAction(self.action)
        else:
            self.iface.addToolBarIcon(self.action)

    def run(self):
        dlg = GradeObliquaPontosDialog(self.iface, self.iface.mainWindow())
        dlg.exec_()
