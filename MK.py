
# -*- coding: utf-8 -*-
"""
ISeD orodja – glavna skripta MK.py (stabilna izdaja)

Vključeno:
- Dialog + Dock (GURS, Urejanje grafike, Simbologija, Izvoz)
- Prenesi parcele GURS (standard)
- Prenesi stavbe GURS
- Izdelava praznega ISeD sloja, edit_type
- Kopiranje izbranih parcel/stavb v ISeD
- Union, Buffer, obrezovanje vplivnega območja
- Izbor/obrezovanje cone VOD
- Simbologija ISeD/OPN_PNRP_OZN
- Izvoz v SHP + ZIP
- Uvoz WMS
"""

import os
import zipfile
import requests

import urllib.parse
# Lokalni varen XML parser
from .xml_safe import safe_fromstring

# QGIS
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsRasterLayer,
    QgsPrintLayout, QgsLayoutItemMap, QgsReadWriteContext,
    QgsVectorFileWriter, QgsField, QgsFeature,
    QgsGeometry, QgsFields
)
from qgis.utils import iface

# PyQt
from qgis.PyQt.QtCore import QVariant, Qt, QSize, QRect, QPoint
from qgis.PyQt.QtGui import QIcon, QPixmap, QPainter, QImage, QColor
from qgis.PyQt.QtSvg import QSvgRenderer
from qgis.PyQt.QtWidgets import (
    QAction, QInputDialog, QFileDialog, QMessageBox,
    QProgressDialog, QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QGroupBox, QLayout, QStyle,
    QSizePolicy, QSpacerItem, QDockWidget, QWidget, QScrollArea,
    QRadioButton, QLineEdit, QTextEdit, QFormLayout, QComboBox
)

# ---------------- FlowLayout ----------------
class FlowLayout(QLayout):
    """Postavitev, ki razporedi gumbe v tok (kot besede v vrstici)."""
    def __init__(self, parent=None, margin=0, spacing=-1):
        super().__init__(parent)
        if parent is not None:
            self.setContentsMargins(margin, margin, margin, margin)
        self._items = []
        self.setSpacing(spacing if spacing >= 0 else self.spacing())

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientations(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self.doLayout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self.doLayout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        left, top, right, bottom = self.getContentsMargins()
        size += QSize(left + right, top + bottom)
        return size

    def doLayout(self, rect, testOnly):
        x = rect.x()
        y = rect.y()
        lineHeight = 0
        left, top, right, bottom = self.getContentsMargins()
        effectiveRect = rect.adjusted(+left, +top, -right, -bottom)
        x = effectiveRect.x()
        y = effectiveRect.y()
        for item in self._items:
            spaceX = self.spacing()
            spaceY = self.spacing()
            nextX = x + item.sizeHint().width() + spaceX
            if nextX - spaceX > effectiveRect.right() and lineHeight > 0:
                x = effectiveRect.x()
                y = y + lineHeight + spaceY
                nextX = x + item.sizeHint().width() + spaceX
                lineHeight = 0
            if not testOnly:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))
            x = nextX
            lineHeight = max(lineHeight, item.sizeHint().height())
        return y + lineHeight - rect.y() + bottom

# ---------------- Glavni razred vtičnika ----------------
class MK:
    def __init__(self, iface_):
        self.iface = iface_
        self.action = None
        self.dock = None
        self._icons_dir = os.path.join(os.path.dirname(__file__), 'Resources', 'icons')

    def _resources(self, *parts):
        base_dir = os.path.dirname(__file__)
        return os.path.join(base_dir, 'Resources', *parts)

    def initGui(self):
        # Ikona za toolbar - okrogla verzija
        icon_path = os.path.join(os.path.dirname(__file__), 'Resources', 'ised_logo_round.png')
        if os.path.exists(icon_path):
            self.action = QAction(QIcon(icon_path), "", self.iface.mainWindow())
        else:
            self.action = QAction("ISeD", self.iface.mainWindow())
        self.action.setToolTip("ISeD orodja")
        self.action.triggered.connect(self.toggle_dock)
        self.iface.addPluginToMenu("&ISeD", self.action)
        self.iface.addToolBarIcon(self.action)

    def _set_button_icon(self, btn, name, fallback=QStyle.SP_FileIcon):
        icon_size = QSize(16, 16)
        target_color = QColor('#143845')  # definiran, da ne povzroča napak
        try:
            png_path = os.path.join(self._icons_dir, name + ".png")
            if os.path.exists(png_path):
                btn.setIcon(QIcon(png_path))
                btn.setIconSize(icon_size)
                return
            svg_path = os.path.join(self._icons_dir, name + ".svg")
            if os.path.exists(svg_path):
                try:
                    renderer = QSvgRenderer(svg_path)
                    pix = QPixmap(icon_size)
                    pix.fill(Qt.transparent)
                    painter = QPainter(pix)
                    renderer.render(painter)
                    painter.end()
                    img = pix.toImage().convertToFormat(QImage.Format_ARGB32)
                    res = QImage(img.size(), QImage.Format_ARGB32)
                    res.fill(Qt.transparent)
                    h = img.height()
                    w = img.width()
                    for yy in range(h):
                        for xx in range(w):
                            col = img.pixelColor(xx, yy)
                            a = col.alpha()
                            if a > 0:
                                c = QColor(target_color)
                                c.setAlpha(a)
                                res.setPixelColor(xx, yy, c)
                    final_pix = QPixmap.fromImage(res)
                    btn.setIcon(QIcon(final_pix))
                    btn.setIconSize(icon_size)
                    return
                except Exception:
                    btn.setIcon(QIcon(svg_path))
                    btn.setIconSize(icon_size)
                    return
            ico_path = os.path.join(self._icons_dir, name + ".ico")
            if os.path.exists(ico_path):
                btn.setIcon(QIcon(ico_path))
                btn.setIconSize(icon_size)
                return
        except Exception:
            pass
        try:
            std_icon = self.iface.mainWindow().style().standardIcon(fallback)
            btn.setIcon(std_icon)
            btn.setIconSize(icon_size)
        except Exception:
            pass

    def unload(self):
        self.iface.removePluginMenu("&ISeD", self.action)
        self.iface.removeToolBarIcon(self.action)
        try:
            if self.dock is not None:
                self.iface.mainWindow().removeDockWidget(self.dock)
                self.dock.deleteLater()
                self.dock = None
        except Exception:
            pass

    def run(self):
        self.toggle_dock()

    # ---------------- Dialog ----------------
    def show_tool_dialog(self):
        dlg = QDialog(self.iface.mainWindow())
        dlg.setWindowTitle("ISeD orodja")
        dlg.setMinimumWidth(520)

        desc = QLabel("ISeD vtičnik je namenjen uporabnikom aplikacije ISeD. Spodaj se nahajajo orodja za pripravo grafike.")
        desc.setWordWrap(True)

        main_layout = QVBoxLayout()
        main_layout.addWidget(desc)
        
        # URL link za pomoč
        help_link = QLabel('<a href="http://www.google.si">Pomoč in navodila</a>')
        help_link.setOpenExternalLinks(True)
        help_link.setAlignment(Qt.AlignLeft)
        main_layout.addWidget(help_link)

        # Group 1
        gb1 = QGroupBox("Izdelava novega sloja ali dodajanje 'edit_type' obstoječemu")
        gb1_layout = QHBoxLayout()
        btn_create = QPushButton("Ustvari prazen sloj za ISeD")
        btn_add_field = QPushButton("Dodaj polje 'edit_type' obstoječemu sloju")
        self._set_button_icon(btn_create, 'create')
        self._set_button_icon(btn_add_field, 'add_field')
        gb1_layout.addWidget(btn_create)
        gb1_layout.addWidget(btn_add_field)
        gb1.setLayout(gb1_layout)
        main_layout.addWidget(gb1)

        # Group 2: GURS
        gb2 = QGroupBox("GURS")
        gb2_layout = QHBoxLayout()
        btn_download = QPushButton("Prenesi aktualne parcele GURS")
        btn_download_buildings = QPushButton("Prenesi aktualne stavbe GURS")
        for b, n in [
            (btn_download, 'download'),
            (btn_download_buildings, 'download_buildings'),
        ]:
            self._set_button_icon(b, n)
        gb2_layout.addWidget(btn_download)
        gb2_layout.addWidget(btn_download_buildings)
        gb2.setLayout(gb2_layout)
        main_layout.addWidget(gb2)

        # Import
        btn_import = QPushButton("Uvozi GURS podlage")
        btn_import.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._set_button_icon(btn_import, 'import')
        main_layout.addWidget(btn_import)

        # Group 3: Urejanje grafike
        gb3 = QGroupBox("Urejanje grafike")
        
        
        main_gb3_layout = QVBoxLayout()

        opis_label = QLabel("Za uporabo spodnjih orodij morate imeti izbran sloj ISeD")
        opis_label.setWordWrap(True)
        main_gb3_layout.addWidget(opis_label)


        gb3_layout = FlowLayout()
        btn_select_area = QPushButton("Izberi območje")
        btn_select_area.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        gb3_layout.addWidget(btn_select_area)
        btn_copy = QPushButton("Kopiraj izbrane parcele v sloj ISeD in jih združi")
        btn_copy_buildings = QPushButton("Kopiraj izbrane stavbe v sloj ISeD")
        btn_clip = QPushButton("Obreži vplivno območje s spomenikom")
        btn_edit_graphics = QPushButton("Uredi grafiko")
        btn_select_vod = QPushButton("Izberi cono VOD")
        btn_clip_vod = QPushButton("Obreži izbrano cono VOD")
        btn_buffer = QPushButton("Dodaj buffer izbranemu poligonu v ISeD sloju")
        btn_union = QPushButton("Združi izbrane poligone parcel brez prenosa")
        for w, n in [
            (btn_select_area,'select'),
            (btn_copy,'copy'),
            (btn_copy_buildings,'copy_buildings'),
            (btn_clip,'clip'),
            (btn_edit_graphics,'edit'),
            (btn_select_vod,'select_vod'),
            (btn_clip_vod,'clip_vod'),
            (btn_buffer,'buffer'),
            (btn_union,'union'),
        ]:
            w.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
            gb3_layout.addWidget(w)
            self._set_button_icon(w, n)
        gb3.setLayout(gb3_layout)
        main_layout.addWidget(gb3)

        # Group 4: simbologija
        gb4 = QGroupBox("Simbologija slojev")
        gb4_layout = QHBoxLayout()
        btn_sym = QPushButton("Nastavi simbologijo ISeD")
        btn_sym_opn = QPushButton("Nastavi simbologijo OPN_PNRP_OZN")
        self._set_button_icon(btn_sym, 'sym')
        self._set_button_icon(btn_sym_opn, 'sym_opn')
        gb4_layout.addWidget(btn_sym)
        gb4_layout.addWidget(btn_sym_opn)
        gb4.setLayout(gb4_layout)
        main_layout.addWidget(gb4)

        # Group 5: izvoz
        gb5 = QGroupBox("Izvoz v SHP in ZIP")
        gb5_layout = QHBoxLayout()
        btn_export = QPushButton("Izvozi v shapefile + zip")
        self._set_button_icon(btn_export, 'export')
        gb5_layout.addWidget(btn_export)
        gb5.setLayout(gb5_layout)
        main_layout.addWidget(gb5)

        main_layout.addItem(QSpacerItem(20, 10, QSizePolicy.Minimum, QSizePolicy.Expanding))

        close_btn = QPushButton("Zapri")
        close_btn.clicked.connect(dlg.close)
        self._set_button_icon(close_btn, 'close')
        main_layout.addWidget(close_btn)

        dlg.setLayout(main_layout)

        # SIGNALI
        btn_create.clicked.connect(self.create_empty_ised_layer)
        btn_add_field.clicked.connect(self.add_edit_type_field)
        btn_download.clicked.connect(self.download_parcels_from_gurs)
        btn_download_buildings.clicked.connect(self.download_buildings_from_gurs)
        btn_select_area.clicked.connect(self.activate_select_area_tool)
        btn_copy.clicked.connect(self.copy_selected_parcels_to_ised)
        btn_copy_buildings.clicked.connect(self.copy_selected_buildings_to_ised)
        btn_clip.clicked.connect(self.clip_influence_area)
        btn_edit_graphics.clicked.connect(self.start_edit_and_vertex_tool)
        btn_select_vod.clicked.connect(self.select_vod_zone)
        btn_clip_vod.clicked.connect(self.clip_selected_vod_zone)
        btn_buffer.clicked.connect(self.add_buffer)
        btn_union.clicked.connect(self.union_selected_geometries)
        btn_sym.clicked.connect(self.apply_symbology)
        btn_sym_opn.clicked.connect(self.apply_opn_symbology)
        btn_export.clicked.connect(self.export_to_shp_zip)
        btn_import.clicked.connect(self.import_from_wms)

        dlg.exec_()

    # ---------------- Dock ----------------
    def toggle_dock(self):
        if self.dock is None:
            self.create_dock_widget()
        if self.dock.isVisible():
            self.dock.hide()
        else:
            self.dock.show()

    def create_dock_widget(self):
        mw = self.iface.mainWindow()
        self.dock = QDockWidget("ISeD orodja", mw)
        self.dock.setObjectName("MK_Tools_Dock")
        self.dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)

        container = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        main_widget = QWidget()
        main_layout = QVBoxLayout()
        
        # Slika na vrhu - kvadratna verzija
        logo_path = os.path.join(os.path.dirname(__file__), 'Resources', 'ised.png')
        if os.path.exists(logo_path):
            logo_label = QLabel()
            pixmap = QPixmap(logo_path)
            # Skaliraj sliko na primerno velikost (npr. 128x128)
            scaled_pixmap = pixmap.scaled(128, 128, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            logo_label.setPixmap(scaled_pixmap)
            logo_label.setAlignment(Qt.AlignCenter)
            main_layout.addWidget(logo_label)

        desc = QLabel("ISeD orodja so neuradni vtičnik za QGIS, razvit kot pomoč uporabnikom informacijskega sistema ISeD.")
        desc.setWordWrap(True)
        main_layout.addWidget(desc)
        
        # URL link za pomoč
        help_link = QLabel('<a href="http://www.google.si">Pomoč in navodila</a>')
        help_link.setOpenExternalLinks(True)
        help_link.setAlignment(Qt.AlignLeft)
        main_layout.addWidget(help_link)

        # Group 1
        gb1 = QGroupBox("Izdelava novega sloja ali dodajanje 'edit_type' obstoječemu")
        gb1_layout = QHBoxLayout()
        btn_create = QPushButton("Ustvari prazen sloj za ISeD")
        btn_add_field = QPushButton("Dodaj polje 'edit_type' obstoječemu sloju")
        gb1_layout.addWidget(btn_create)
        gb1_layout.addWidget(btn_add_field)
        gb1.setLayout(gb1_layout)
        main_layout.addWidget(gb1)

        # Group 2: GURS
        gb2 = QGroupBox("GURS")
        gb2_layout = QHBoxLayout()
        btn_download = QPushButton("Prenesi aktualne parcele GURS")
        btn_download_buildings = QPushButton("Prenesi aktualne stavbe GURS")
        for b, n in [
            (btn_download, 'download'),
            (btn_download_buildings, 'download_buildings'),
        ]:
            self._set_button_icon(b, n)
        gb2_layout.addWidget(btn_download)
        gb2_layout.addWidget(btn_download_buildings)
        gb2.setLayout(gb2_layout)
        main_layout.addWidget(gb2)

        # Group 3: Urejanje grafike
        gb3 = QGroupBox("Urejanje grafike")
        
        main_gb3_layout = QVBoxLayout()
        opis_label = QLabel("Za uporabo spodnjih orodij morate imeti izbran sloj ISeD")
        opis_label.setWordWrap(True)
        main_gb3_layout.addWidget(opis_label)
        
        gb3_layout = FlowLayout()
        btn_select_area = QPushButton("Izberi območje")
        btn_select_area.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        gb3_layout.addWidget(btn_select_area)
        btn_copy = QPushButton("Kopiraj izbrane parcele v sloj ISeD in jih združi")
        btn_copy_buildings = QPushButton("Kopiraj izbrane stavbe v sloj ISeD")
        btn_clip = QPushButton("Obreži vplivno območje s spomenikom")
        btn_edit_graphics = QPushButton("Uredi grafiko")
        btn_select_vod = QPushButton("Izberi cono VOD")
        btn_clip_vod = QPushButton("Obreži izbrano cono VOD")
        btn_buffer = QPushButton("Dodaj buffer izbranemu poligonu v ISeD sloju")
        btn_union = QPushButton("Združi izbrane poligone parcel brez prenosa")
        for w in [btn_copy, btn_copy_buildings, btn_clip, btn_edit_graphics, btn_select_vod, btn_clip_vod, btn_buffer, btn_union]:
            w.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
            gb3_layout.addWidget(w)
        main_gb3_layout.addLayout(gb3_layout)
        gb3.setLayout(main_gb3_layout)
        main_layout.addWidget(gb3)
        self._set_button_icon(btn_select_area, 'select')
        for w, n in [
            (btn_copy, 'copy'),
            (btn_copy_buildings, 'copy_buildings'),
            (btn_clip, 'clip'),
            (btn_edit_graphics, 'edit'),
            (btn_select_vod, 'select_vod'),
            (btn_clip_vod, 'clip_vod'),
            (btn_buffer, 'buffer'),
            (btn_union, 'union'),
        ]:
            self._set_button_icon(w, n)

        # Group 4: simbologija
        gb4 = QGroupBox("Simbologija slojev")
        gb4_layout = QHBoxLayout()
        btn_sym = QPushButton("Nastavi simbologijo ISeD")
        btn_sym_opn = QPushButton("Nastavi simbologijo OPN_PNRP_OZN")
        self._set_button_icon(btn_sym, 'sym')
        self._set_button_icon(btn_sym_opn, 'sym_opn')
        gb4_layout.addWidget(btn_sym)
        gb4_layout.addWidget(btn_sym_opn)
        gb4.setLayout(gb4_layout)
        main_layout.addWidget(gb4)

        # Group 5: izvoz
        gb5 = QGroupBox("Izvoz v SHP in ZIP")
        gb5_layout = QHBoxLayout()
        btn_export = QPushButton("Izvozi v shapefile + zip")
        self._set_button_icon(btn_export, 'export')
        gb5_layout.addWidget(btn_export)
        gb5.setLayout(gb5_layout)
        main_layout.addWidget(gb5)

        main_layout.addItem(QSpacerItem(20, 10, QSizePolicy.Minimum, QSizePolicy.Expanding))

        btn_import = QPushButton("Uvozi GURS podlage")
        btn_import.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._set_button_icon(btn_import, 'import')
        main_layout.addWidget(btn_import)

        hide_btn = QPushButton("Skrij panel")
        hide_btn.clicked.connect(self.dock.hide)
        self._set_button_icon(hide_btn, 'hide')
        main_layout.addWidget(hide_btn)

        main_widget.setLayout(main_layout)
        scroll.setWidget(main_widget)
        layout_wrapper = QVBoxLayout()
        layout_wrapper.addWidget(scroll)
        container.setLayout(layout_wrapper)
        self.dock.setWidget(container)
        mw.addDockWidget(Qt.RightDockWidgetArea, self.dock)

        # SIGNALI
        btn_create.clicked.connect(self.create_empty_ised_layer)
        btn_add_field.clicked.connect(self.add_edit_type_field)
        btn_download.clicked.connect(self.download_parcels_from_gurs)
        btn_download_buildings.clicked.connect(self.download_buildings_from_gurs)
        btn_select_area.clicked.connect(self.activate_select_area_tool)
        btn_copy.clicked.connect(self.copy_selected_parcels_to_ised)
        btn_copy_buildings.clicked.connect(self.copy_selected_buildings_to_ised)
        btn_clip.clicked.connect(self.clip_influence_area)
        btn_edit_graphics.clicked.connect(self.start_edit_and_vertex_tool)
        btn_select_vod.clicked.connect(self.select_vod_zone)
        btn_clip_vod.clicked.connect(self.clip_selected_vod_zone)
        btn_buffer.clicked.connect(self.add_buffer)
        btn_union.clicked.connect(self.union_selected_geometries)
        btn_sym.clicked.connect(self.apply_symbology)
        btn_sym_opn.clicked.connect(self.apply_opn_symbology)
        btn_export.clicked.connect(self.export_to_shp_zip)
        btn_import.clicked.connect(self.import_from_wms)

    # ---------------- Orodja ----------------
    def activate_select_area_tool(self):
        try:
            if hasattr(self.iface, 'actionSelect') and callable(self.iface.actionSelect):
                self.iface.actionSelect().trigger()
                return
            if hasattr(self.iface, 'actionSelectRectangle') and callable(self.iface.actionSelectRectangle):
                self.iface.actionSelectRectangle().trigger()
                return
            from qgis.gui import QgsMapToolSelectFeatures
            tool = QgsMapToolSelectFeatures(self.iface.mapCanvas())
            self.iface.mapCanvas().setMapTool(tool)
        except Exception as e:
            QMessageBox.warning(None, "ISeD orodja", "Ni bilo mogoče aktivirati orodja za izbiro: " + str(e))

    def open_search_parcels_dialog(self):
        # poišči (ali naloži) GURS parcele WFS
        layer = self._find_parcels_layer()
        if layer is None:
            self.download_parcels_from_gurs()
            layer = self._find_parcels_layer()
        if layer is None:
            QMessageBox.warning(None, "ISeD orodja", "Sloj parcel (GURS WFS) ni naložen.")
            return

        dlg = QDialog(self.iface.mainWindow())
        dlg.setWindowTitle("Iskanje parcel (GURS WFS)")
        dlg.setMinimumWidth(520)
        layout = QVBoxLayout(dlg)

        rb1 = QRadioButton("parcele z vejico in katastrska občina posebej")
        rb2 = QRadioButton("parcele in katastrska občina skupaj")
        rb1.setChecked(True)
        layout.addWidget(rb1)
        layout.addWidget(rb2)

        form1 = QGroupBox("Vnos: KO posebej, parcele z vejico")
        f1 = QFormLayout()
        ko_edit = QLineEdit()
        ko_edit.setPlaceholderText("npr. 1220 (samo številka)")
        parcels_edit = QTextEdit()
        parcels_edit.setPlaceholderText("npr. 500/1, 500/2, 505 ... (do 5000 znakov)")
        f1.addRow("Katastrska občina (KO):", ko_edit)
        f1.addRow("Parcele:", parcels_edit)
        form1.setLayout(f1)

        form2 = QGroupBox("Vnos: 'parcela-KO' skupaj, ločeno z vejico")
        f2 = QFormLayout()
        combo_edit = QTextEdit()
        combo_edit.setPlaceholderText("npr. 500/1-1220, 505-1220, 700-1221 ... (do 5000 znakov)")
        f2.addRow("Seznam:", combo_edit)
        form2.setLayout(f2)
        form2.setVisible(False)

        layout.addWidget(form1)
        layout.addWidget(form2)

        def toggle_forms():
            form1.setVisible(rb1.isChecked())
            form2.setVisible(rb2.isChecked())
        rb1.toggled.connect(toggle_forms)
        rb2.toggled.connect(toggle_forms)

        btn_search = QPushButton("Poišči parcele")
        self._set_button_icon(btn_search, 'search')
        btn_cancel = QPushButton("Zapri")
        self._set_button_icon(btn_cancel, 'close')
        btn_cancel.clicked.connect(dlg.reject)
        btn_row = QHBoxLayout()
        btn_row.addWidget(btn_search)
        btn_row.addStretch(1)
        btn_row.addWidget(btn_cancel)
        layout.addLayout(btn_row)

        def do_search():
            ko_field, parc_field = self._detect_parcel_fields(layer)
            if ko_field is None or parc_field is None:
                ko_field, parc_field = self._ask_fields(layer, ko_field, parc_field)
            if ko_field is None or parc_field is None:
                return
            pairs = []
            try:
                if rb1.isChecked():
                    ko_text = ko_edit.text().strip()
                    if not ko_text.isdigit():
                        QMessageBox.warning(dlg, "Iskanje parcel", "KO mora biti številka (npr. 1220).")
                        return
                    ko_val = int(ko_text)
                    raw = parcels_edit.toPlainText().strip()
                    if len(raw) == 0:
                        QMessageBox.warning(dlg, "Iskanje parcel", "Vnesi vsaj eno parcelo.")
                        return
                    if len(raw) > 5000:
                        QMessageBox.warning(dlg, "Iskanje parcel", "Vnos parcel presega 5000 znakov.")
                        return
                    tokens = [t.strip() for t in raw.split(",") if t.strip() != ""]
                    for t in tokens:
                        pairs.append((ko_val, t))
                else:
                    raw = combo_edit.toPlainText().strip()
                    if len(raw) == 0:
                        QMessageBox.warning(dlg, "Iskanje parcel", "Vnesi vsaj eno kombinacijo 'parcela-KO'.")
                        return
                    if len(raw) > 5000:
                        QMessageBox.warning(dlg, "Iskanje parcel", "Vnos presega 5000 znakov.")
                        return
                    tokens = [t.strip() for t in raw.split(",") if t.strip() != ""]
                    for t in tokens:
                        if "-" not in t:
                            QMessageBox.warning(dlg, "Iskanje parcel", "Nepravilna oblika vnosa: " + t)
                            return
                        p, k = t.split("-", 1)
                        p = p.strip()
                        k = k.strip()
                        if not k.isdigit():
                            QMessageBox.warning(dlg, "Iskanje parcel", "KO mora biti številka (najdeno '" + k + "').")
                            return
                        pairs.append((int(k), p))

                count = self._select_parcels_by_pairs(layer, ko_field, parc_field, pairs)
                if count == 0:
                    QMessageBox.information(dlg, "Iskanje parcel", "Ni zadetkov.")
                else:
                    try:
                        self.iface.mapCanvas().zoomToSelected(layer)
                    except Exception:
                        ext = layer.boundingBoxOfSelected()
                        if not ext.isEmpty():
                            c = self.iface.mapCanvas()
                            c.setExtent(ext)
                            c.refresh()
                    QMessageBox.information(dlg, "Iskanje parcel", "Označenih parcel: " + str(count))
                dlg.accept()
            except Exception as e:
                QMessageBox.critical(dlg, "Iskanje parcel", "Napaka pri iskanju:\n" + str(e))

        btn_search.clicked.connect(do_search)
        dlg.exec_()

    def _find_parcels_layer(self):
        for lyr in QgsProject.instance().mapLayers().values():
            try:
                if hasattr(lyr, 'providerType') and lyr.providerType().lower() == 'wfs' and 'parcele' in lyr.name().lower():
                    return lyr
                if 'parcele' in lyr.name().lower():
                    return lyr
            except Exception:
                continue
        return None

    def _detect_parcel_fields(self, layer):
        names = [f.name() for f in layer.fields()]
        low = [n.lower() for n in names]
        ko_candidates = []
        for i, n in enumerate(low):
            if n in ('ko', 'ko_sifra', 'ko__sifra', 'ko_sifko'):
                ko_candidates.append(names[i])
            elif ('ko' in n) and ('sifra' in n or 'id' in n or n.endswith('_ko') or n.startswith('ko_')):
                ko_candidates.append(names[i])
        parc_candidates = []
        for i, n in enumerate(low):
            if n in ('parcela', 'st_parcele', 'stparcele', 'id_parcele'):
                parc_candidates.append(names[i])
            elif ('parcel' in n) or ('parc' in n) or ('st_parc' in n):
                parc_candidates.append(names[i])
        ko_field = ko_candidates[0] if ko_candidates else None
        parc_field = parc_candidates[0] if parc_candidates else None
        return ko_field, parc_field

    def _ask_fields(self, layer, ko_default=None, parc_default=None):
        dlg = QDialog(self.iface.mainWindow())
        dlg.setWindowTitle("Izbor polj (KO / PARCELA)")
        form = QFormLayout(dlg)
        names = [f.name() for f in layer.fields()]
        cmb_ko = QComboBox()
        cmb_ko.addItems(names)
        if ko_default and ko_default in names:
            cmb_ko.setCurrentIndex(names.index(ko_default))
        cmb_parc = QComboBox()
        cmb_parc.addItems(names)
        if parc_default and parc_default in names:
            cmb_parc.setCurrentIndex(names.index(parc_default))
        form.addRow("Polje KO:", cmb_ko)
        form.addRow("Polje PARCELA:", cmb_parc)
        btn_ok = QPushButton("Potrdi")
        btn_cancel = QPushButton("Prekliči")
        btn_ok.clicked.connect(dlg.accept)
        btn_cancel.clicked.connect(dlg.reject)
        row = QHBoxLayout()
        row.addWidget(btn_ok)
        row.addStretch(1)
        row.addWidget(btn_cancel)
        form.addRow(row)
        if dlg.exec_() == QDialog.Accepted:
            return cmb_ko.currentText(), cmb_parc.currentText()
        return None, None

    def _select_parcels_by_pairs(self, layer, ko_field, parc_field, pairs):
        # grupiraj
        from collections import defaultdict
        grouped = defaultdict(list)
        for ko, p in pairs:
            grouped[str(ko)].append(str(p))

        clauses = []
        CHUNK = 500
        for ko_val, plist in grouped.items():
            for i in range(0, len(plist), CHUNK):
                chunk = plist[i:i + CHUNK]
                # zgradi varno seznam vrednosti, brez problematičnih escape-ov v f-string
                vals = []
                for v in chunk:
                    vals.append("'" + v.replace("'", "''") + "'")
                values = ",".join(vals)
                clause = "(" + "\"" + ko_field + "\"" + " = " + str(ko_val) + " AND " + "\"" + parc_field + "\"" + " IN (" + values + "))"
                clauses.append(clause)

        if not clauses:
            layer.removeSelection()
            return 0

        expr = " OR ".join(clauses)
        try:
            layer.selectByExpression(expr)
        except Exception as e:
            layer.removeSelection()
            target = set((str(ko), str(p)) for ko, p in pairs)
            idx_ko = layer.fields().indexOf(ko_field)
            idx_parc = layer.fields().indexOf(parc_field)
            if idx_ko < 0 or idx_parc < 0:
                raise e
            ids = []
            for feat in layer.getFeatures():
                try:
                    ko_val = str(feat.attribute(idx_ko))
                    p_val = str(feat.attribute(idx_parc))
                    if (ko_val, p_val) in target:
                        ids.append(feat.id())
                except Exception:
                    continue
            layer.selectByIds(ids)
        return layer.selectedFeatureCount()

    def select_vod_zone(self):
        layer = self.get_active_layer()
        if not layer:
            return
        QMessageBox.information(None, "ISeD orodja", "Kliknite na poligon cone VOD, da ga izberete.")
        from qgis.gui import QgsMapToolIdentifyFeature
        canvas = self.iface.mapCanvas()
        tool = QgsMapToolIdentifyFeature(canvas)
        tool.setLayer(layer)
        def on_feature_selected(feature):
            try:
                fid = feature.id()
            except Exception:
                fid = None
            layer.removeSelection()
            if fid is not None:
                layer.select(fid)
                QMessageBox.information(None, "ISeD orodja", "Cona VOD (ID: " + str(fid) + ") je bila izbrana.")
            else:
                QMessageBox.information(None, "ISeD orodja", "Cona VOD je bila izbrana.")
            canvas.unsetMapTool(tool)
        tool.featureIdentified.connect(on_feature_selected)
        canvas.setMapTool(tool)

    def clip_selected_vod_zone(self):
        layer = self.get_active_layer()
        if not layer:
            return
        selected = layer.selectedFeatures()
        if not selected or len(selected) != 1:
            QMessageBox.warning(None, "ISeD orodja", "Izberite natanko en poligon cone VOD.")
            return
        base_feat = selected[0]
        base_geom = base_feat.geometry()
        new_geoms = {}
        for feat in layer.getFeatures():
            if feat.id() == base_feat.id():
                continue
            geom = feat.geometry()
            if geom.intersects(base_geom):
                clipped = geom.difference(base_geom)
                if not clipped.isEmpty():
                    new_geoms[feat.id()] = clipped
        if not new_geoms:
            QMessageBox.information(None, "ISeD orodja", "Ni poligonov za obrezovanje.")
            return
        layer.startEditing()
        layer.dataProvider().changeGeometryValues(new_geoms)
        layer.commitChanges()
        layer.updateExtents()
        layer.triggerRepaint()
        QMessageBox.information(None, "ISeD orodja", "Obrezanih je bilo " + str(len(new_geoms)) + " poligonov.")

    def start_edit_and_vertex_tool(self):
        layer = self.get_active_layer()
        if not layer:
            return
        try:
            if not layer.isEditable():
                layer.startEditing()
        except Exception as e:
            QMessageBox.critical(None, "ISeD orodja", "Napaka pri zagonu urejanja sloja:\n" + str(e))
            return
        try:
            if hasattr(self.iface, 'actionVertexTool') and callable(getattr(self.iface, 'actionVertexTool')):
                self.iface.actionVertexTool().trigger()
                return
            act = getattr(self.iface, 'actionVertexTool', None)
            if act is not None and hasattr(act, 'trigger'):
                act.trigger()
                return
            QMessageBox.information(None, "ISeD orodja", "Urejanje je aktivirano. Prosim izberi 'Vertex tool' ročno.")
        except Exception:
            QMessageBox.information(None, "ISeD orodja", "Urejanje je aktivirano. Ne morem avtomatsko aktivirati Vertex orodja.")

    def get_active_layer(self):
        layer = self.iface.activeLayer()
        if not layer:
            QMessageBox.warning(None, "ISeD orodja", "Ni izbranega sloja.")
        return layer

    def add_edit_type_field(self):
        layer = self.get_active_layer()
        if not layer:
            return
        pr = layer.dataProvider()
        if "edit_type" in [f.name() for f in pr.fields()]:
            QMessageBox.information(None, "ISeD orodja", "Polje 'edit_type' že obstaja.")
            return
        pr.addAttributes([QgsField("edit_type", QVariant.Int)])
        layer.updateFields()
        QMessageBox.information(None, "ISeD orodja", "Polje 'edit_type' je bilo dodano v sloj.")

    def apply_symbology(self):
        layer = self.get_active_layer()
        if not layer:
            return
        qml_path = os.path.join(os.path.dirname(__file__), 'Resources', 'ised.qml')
        if os.path.exists(qml_path):
            result = layer.loadNamedStyle(qml_path)
            ok = bool(result[0]) if isinstance(result, tuple) and len(result) >= 1 else bool(result)
            if not ok and not (isinstance(result, tuple) and any((isinstance(r, bool) and r) or (not isinstance(r, bool) and r) for r in result)):
                QMessageBox.critical(None, "ISeD orodja", "Napaka pri nalaganju simbologije iz " + qml_path)
                return
            layer.triggerRepaint()
            QMessageBox.information(None, "ISeD orodja", "Simbologija ISeD je bila aplicirana.")
            return
        QMessageBox.information(None, "ISeD orodja", "Datoteka 'Resources/ised.qml' ni bila najdena; preskočeno.")

    def apply_opn_symbology(self):
        layer = self.get_active_layer()
        if not layer:
            return
        qml_path = os.path.join(os.path.dirname(__file__), 'Resources', 'OPN_PNRP_OZN.qml')
        if os.path.exists(qml_path):
            result = layer.loadNamedStyle(qml_path)
            ok = bool(result[0]) if isinstance(result, tuple) and len(result) >= 1 else bool(result)
            if not ok and not (isinstance(result, tuple) and any((isinstance(r, bool) and r) or (not isinstance(r, bool) and r) for r in result)):
                QMessageBox.critical(None, "ISeD orodja", "Napaka pri nalaganju simbologije iz " + qml_path)
                return
            layer.triggerRepaint()
            QMessageBox.information(None, "ISeD orodja", "Simbologija OPN_PNRP_OZN je bila aplicirana.")
            return
        QMessageBox.warning(None, "ISeD orodja", "Datoteka 'Resources/OPN_PNRP_OZN.qml' ni bila najdena.")

    def download_parcels_from_gurs(self):
        canvas = iface.mapCanvas()
        scale = canvas.scale()
        if scale > 10000:
            QMessageBox.warning(None, "ISeD orodja", "Preveliko območje – povečaj merilo (<= 1:10000).")
            return
        progress = QProgressDialog("Nalagam parcele iz GURS WFS...", "Prekliči", 0, 0, self.iface.mainWindow())
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)
        progress.show()
        uri = (
            "pagingEnabled='true' "
            "restrictToRequestBBOX='1' "
            "srsname='EPSG:3794' "
            "typename='SI.GURS.KN:PARCELE' "
            "url='https://ipi.eprostor.gov.si/wfs-si-gurs-kn/wfs' "
            "version='auto'"
        )
        layer = QgsVectorLayer(uri, "Parcele (GURS WFS)", "WFS")
        progress.close()
        if not layer.isValid():
            QMessageBox.critical(None, "ISeD orodja", "Napaka pri nalaganju parcel iz GURS WFS.")
            return
        qml_path = self._resources('parcele.qml')
        if os.path.exists(qml_path):
            try:
                result = layer.loadNamedStyle(qml_path)
                ok = bool(result[0]) if isinstance(result, tuple) and len(result) >= 1 else bool(result)
                if not ok and not (isinstance(result, tuple) and any((isinstance(r, bool) and r) or (not isinstance(r, bool) and r) for r in result)):
                    QMessageBox.warning(None, "ISeD orodja", "Slog iz 'parcele.qml' ni bil uporabljen.")
                layer.triggerRepaint()
            except Exception as e:
                QMessageBox.warning(None, "ISeD orodja", "Napaka pri nalaganju slogov parcel:\n" + str(e))
        layer.setMaximumScale(10000)
        layer.setMinimumScale(0)
        QgsProject.instance().addMapLayer(layer)
        QMessageBox.information(None, "ISeD orodja", "Parcele so bile naložene.")

    def download_buildings_from_gurs(self):
        canvas = iface.mapCanvas()
        scale = canvas.scale()
        if scale > 10000:
            QMessageBox.warning(None, "ISeD orodja", "Preveliko območje – povečaj merilo (<= 1:10000).")
            return
        progress = QProgressDialog("Nalagam stavbe iz GURS WFS...", "Prekliči", 0, 0, self.iface.mainWindow())
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)
        progress.show()
        uri = (
            "pagingEnabled='true' "
            "restrictToRequestBBOX='1' "
            "srsname='EPSG:3794' "
            "typename='SI.GURS.KN:STAVBE_OBRIS' "
            "url='https://ipi.eprostor.gov.si/wfs-si-gurs-kn/wfs' "
            "version='auto'"
        )
        layer = QgsVectorLayer(uri, "Stavbe obris (GURS WFS)", "WFS")
        progress.close()
        if not layer.isValid():
            QMessageBox.critical(None, "ISeD orodja", "Napaka pri nalaganju stavb iz GURS WFS.")
            return
        layer.setMaximumScale(10000)
        layer.setMinimumScale(0)
        QgsProject.instance().addMapLayer(layer)
        QMessageBox.information(None, "ISeD orodja", "Stavbe so bile naložene.")

    def union_selected_geometries(self):
        layer = self.get_active_layer()
        if not layer:
            return
        selected = layer.selectedFeatures()
        if not selected:
            QMessageBox.warning(None, "ISeD orodja", "Ni označenih geometrij.")
            return
        geoms = [f.geometry() for f in selected if f.hasGeometry()]
        union_geom = QgsGeometry.unaryUnion(geoms)
        if union_geom is None or union_geom.isEmpty():
            QMessageBox.warning(None, "ISeD orodja", "Združitev ni uspela.")
            return
        layer.startEditing()
        ids_to_delete = [f.id() for f in selected]
        layer.deleteFeatures(ids_to_delete)
        feat = QgsFeature(layer.fields())
        feat.setGeometry(union_geom)
        layer.addFeature(feat)
        layer.commitChanges()
        layer.updateExtents()
        layer.triggerRepaint()
        QMessageBox.information(None, "ISeD orodja", "Označene geometrije so bile združene v en poligon.")

    def export_to_shp_zip(self):
        layer = self.get_active_layer()
        if not layer:
            return
        out_path, _ = QFileDialog.getSaveFileName(None, "Shrani shapefile kot", layer.name() + ".shp", "Shapefile (*.shp)")
        if not out_path:
            return
        try:
            result = QgsVectorFileWriter.writeAsVectorFormat(layer, out_path, "UTF-8", layer.crs(), "ESRI Shapefile")
        except Exception as e:
            QMessageBox.critical(None, "ISeD orodja", "Napaka pri izvozu shapefile:\n" + str(e))
            return
        if not os.path.exists(out_path):
            QMessageBox.critical(None, "ISeD orodja", "Datoteka .shp ni nastala (izvoz ni uspel).")
            return
        shp_dir = os.path.dirname(out_path)
        shp_base = os.path.splitext(os.path.basename(out_path))[0]
        files_to_zip = []
        for ext in ["shp", "shx", "dbf", "prj", "cpg"]:
            f = os.path.join(shp_dir, shp_base + "." + ext)
            if os.path.exists(f):
                files_to_zip.append(f)
        if not files_to_zip:
            QMessageBox.warning(None, "ISeD orodja", "Ni izvoznih datotek za ZIP.")
            return
        zip_path = os.path.join(shp_dir, shp_base + ".zip")
        try:
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for file_path in files_to_zip:
                    zf.write(file_path, os.path.basename(file_path))
        except Exception as e:
            QMessageBox.critical(None, "ISeD orodja", "Napaka pri ZIP:\n" + str(e))
            return
        QMessageBox.information(None, "ISeD orodja", "ZIP je ustvarjen: " + zip_path)

    def create_empty_ised_layer(self):
        fields = QgsFields()
        fields.append(QgsField("edit_type", QVariant.Int))
        layer = QgsVectorLayer("Polygon?crs=EPSG:3794", "priprava_grafike_za_ISeD", "memory")
        pr = layer.dataProvider()
        pr.addAttributes(fields)
        layer.updateFields()
        QgsProject.instance().addMapLayer(layer)
        qml_path = os.path.join(os.path.dirname(__file__), 'Resources', 'ised.qml')
        if os.path.exists(qml_path):
            result = layer.loadNamedStyle(qml_path)
            ok = bool(result[0]) if isinstance(result, tuple) and len(result) >= 1 else bool(result)
            if ok or (isinstance(result, tuple) and any((isinstance(r, bool) and r) or (not isinstance(r, bool) and r) for r in result)):
                layer.triggerRepaint()
                QMessageBox.information(None, "ISeD orodja", "Ustvarjen sloj in uporabljena simbologija ISeD.")
                return
        QMessageBox.information(None, "ISeD orodja", "Ustvarjen sloj 'priprava_grafike_za_ISeD'.")

    def copy_selected_buildings_to_ised(self):
        buildings_layer = None
        for lyr in QgsProject.instance().mapLayers().values():
            if "stavbe" in lyr.name().lower():
                buildings_layer = lyr
                break
        if not buildings_layer:
            QMessageBox.warning(None, "ISeD orodja", "Sloj stavb ni najden.")
            return
        selected = buildings_layer.selectedFeatures()
        if not selected:
            QMessageBox.warning(None, "ISeD orodja", "Ni označenih stavb.")
            return
        geoms = [f.geometry() for f in selected if f.hasGeometry()]
        union_geom = QgsGeometry.unaryUnion(geoms)
        if union_geom is None or union_geom.isEmpty():
            QMessageBox.warning(None, "ISeD orodja", "Združitev stavb ni uspela.")
            return
        ised_layer = None
        for lyr in QgsProject.instance().mapLayers().values():
            if lyr.name() == "priprava_grafike_za_ISeD":
                ised_layer = lyr
                break
        if not ised_layer:
            QMessageBox.warning(None, "ISeD orodja", "Sloj 'priprava_grafike_za_ISeD' ne obstaja.")
            return
        options = [
            "1 - spomenik",
            "2 - podobmočje spomenika",
            "3 - vplivno območje",
            "4 - podobmočje vplivnega območja",
            "osnovno območje RNPD",
            "cona VOD"
        ]
        choice, ok = QInputDialog.getItem(None, "Izberi tip", "Dodaj v polje edit_type:", options, 0, False)
        if not ok:
            return
        edit_value = None
        if choice[0].isdigit():
            edit_value = int(choice.split(" ")[0])
        if not ised_layer.isEditable():
            ised_layer.startEditing()
        feat = QgsFeature()
        feat.setFields(ised_layer.fields())
        feat.setGeometry(union_geom)
        if edit_value is not None and "edit_type" in [f.name() for f in ised_layer.fields()]:
            feat.setAttribute("edit_type", edit_value)
        ised_layer.addFeature(feat)
        ised_layer.commitChanges()
        ised_layer.updateExtents()
        ised_layer.triggerRepaint()
        QMessageBox.information(None, "ISeD orodja", "Stavbe kopirane v ISeD.")

    def copy_selected_parcels_to_ised(self):
        parcel_layer = None
        for lyr in QgsProject.instance().mapLayers().values():
            if "parcele" in lyr.name().lower():
                parcel_layer = lyr
                break
        if not parcel_layer:
            QMessageBox.warning(None, "ISeD orodja", "Sloj parcel ni najden.")
            return
        selected = parcel_layer.selectedFeatures()
        if not selected:
            QMessageBox.warning(None, "ISeD orodja", "Ni označenih parcel.")
            return
        geoms = [f.geometry() for f in selected if f.hasGeometry()]
        union_geom = QgsGeometry.unaryUnion(geoms)
        if union_geom is None or union_geom.isEmpty():
            QMessageBox.warning(None, "ISeD orodja", "Združitev parcel ni uspela.")
            return
        ised_layer = None
        for lyr in QgsProject.instance().mapLayers().values():
            if lyr.name() == "priprava_grafike_za_ISeD":
                ised_layer = lyr
                break
        if not ised_layer:
            QMessageBox.warning(None, "ISeD orodja", "Sloj 'priprava_grafike_za_ISeD' ne obstaja.")
            return
        options = [
            "1 - spomenik",
            "2 - podobmočje spomenika",
            "3 - vplivno območje",
            "4 - podobmočje vplivnega območja",
            "osnovno območje RNPD",
            "cona VOD"
        ]
        choice, ok = QInputDialog.getItem(None, "Izberi tip", "Dodaj v polje edit_type:", options, 0, False)
        if not ok:
            return
        edit_value = None
        if choice[0].isdigit():
            edit_value = int(choice.split(" ")[0])
        if not ised_layer.isEditable():
            ised_layer.startEditing()
        feat = QgsFeature()
        feat.setFields(ised_layer.fields())
        feat.setGeometry(union_geom)
        if edit_value is not None and "edit_type" in [f.name() for f in ised_layer.fields()]:
            feat.setAttribute("edit_type", edit_value)
        ised_layer.addFeature(feat)
        ised_layer.commitChanges()
        ised_layer.updateExtents()
        ised_layer.triggerRepaint()
        QMessageBox.information(None, "ISeD orodja", "Parcele kopirane v ISeD.")

    def add_buffer(self):
        layer = self.get_active_layer()
        if not layer:
            return
        selected = layer.selectedFeatures()
        if not selected:
            QMessageBox.warning(None, "ISeD orodja", "Ni označenih geometrij.")
            return
        dist, ok = QInputDialog.getDouble(None, "Buffer", "Vnesi razdaljo v metrih", 10.0, 0.1, 10000.0, 1)
        if not ok:
            return
        layer.startEditing()
        for f in selected:
            geom = f.geometry()
            buf = geom.buffer(dist, 5)
            layer.changeGeometry(f.id(), buf)
        layer.commitChanges()
        layer.triggerRepaint()
        QMessageBox.information(None, "ISeD orodja", "Buffer dodan.")

    def clip_influence_area(self):
        layer = self.get_active_layer()
        if not layer:
            return
        if "edit_type" not in [fld.name() for fld in layer.fields()]:
            QMessageBox.warning(None, "ISeD orodja", "Sloj nima polja 'edit_type'.")
            return
        feat3 = None
        for f in layer.getFeatures():
            if f.attribute("edit_type") == 3:
                feat3 = f
                break
        if not feat3:
            QMessageBox.warning(None, "ISeD orodja", "Ni poligona z edit_type = 3 (vplivno območje).")
            return
        feat1 = None
        for f in layer.getFeatures():
            if f.attribute("edit_type") == 1:
                feat1 = f
                break
        if not feat1:
            QMessageBox.warning(None, "ISeD orodja", "Ni poligona z edit_type = 1 (osnovno območje).")
            return
        geom3 = feat3.geometry()
        geom1 = feat1.geometry()
        clipped = geom3.difference(geom1)
        if clipped.isEmpty():
            QMessageBox.warning(None, "ISeD orodja", "Rezultat obrezovanja je prazen.")
            return
        layer.dataProvider().changeGeometryValues({feat3.id(): clipped})
        layer.updateExtents()
        layer.triggerRepaint()
        QMessageBox.information(None, "ISeD orodja", "Vplivno območje je obrezano.")

    def import_from_wms(self):
        wms_url = "https://ipi.eprostor.gov.si/wms-si-gurs-dts/wms"
        try:
            response = requests.get(wms_url + "?SERVICE=WMS&REQUEST=GetCapabilities&VERSION=1.1.1", timeout=15)
            response.raise_for_status()
        except Exception as e:
            QMessageBox.warning(None, "Napaka", "Ne morem pridobiti GetCapabilities:\n" + str(e))
            return
        root = safe_fromstring(response.content, allow_doctype=True)
        layers = []
        for layer in root.findall(".//Layer"):
            name_el = layer.find("Name")
            title_el = layer.find("Title")
            if name_el is not None and title_el is not None:
                layers.append({"id": name_el.text, "title": title_el.text})
        if not layers:
            QMessageBox.warning(None, "Napaka", "V GetCapabilities ni slojev.")
            return
        items = [x["title"] + " (" + x["id"] + ")" for x in layers]
        chosen, ok = QInputDialog.getItem(None, "Izberi sloj", "Sloji:", items, 0, False)
        if not ok:
            return
        chosen_id = None
        chosen_title = None
        for layer in layers:
            if layer["id"] in chosen:
                chosen_id = layer["id"]
                chosen_title = layer["title"]
                break
        if not chosen_id:
            QMessageBox.warning(None, "Napaka", "Izbrani sloj ni najden.")
            return
        uri = "url=" + wms_url + "&layers=" + chosen_id + "&styles=&format=image/png&crs=EPSG:3794"
        rlayer = QgsRasterLayer(uri, chosen_title, "wms")
        if not rlayer.isValid():
            QMessageBox.warning(None, "Napaka", "Sloj ni veljaven ali ni dosegljiv.")
            return
        QgsProject.instance().addMapLayer(rlayer)
        QMessageBox.information(None, "Uspeh", "Sloj dodan v projekt.")

