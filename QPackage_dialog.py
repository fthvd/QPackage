# -*- coding: utf-8 -*-
"""
*****************************************************************************************
 *                                                                                     *
*   Ce programme est un logiciel libre ; vous pouvez le redistribuer et/ou le modifier  *
*   selon les termes de la Licence Publique Générale GNU telle que publiée par          *
*   la Free Software Foundation ; soit la version 2 de la Licence, ou                   *
*   (à votre choix) toute version ultérieure.                                           *
 *                                                                                     *
*****************************************************************************************
"""
import ctypes # Pour la résolution des chemins subst ou net use avec def query_dos_device(self, drive_letter):
import codecs
import subprocess
import zipfile
import tempfile
import shutil
import os
from pathlib import *
import xml.etree.ElementTree as ET
from qgis.core import *
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtWidgets import *
from qgis.PyQt import uic
from osgeo import gdal

from .ModeleListeCouches import ModeleListeCouches


FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'QPackage_dialog_base.ui'))


class LayerInfo:
    def __init__(self, crs_origin):
        self.crs_origin = crs_origin

class QPackageDialog(QDialog, FORM_CLASS):
    new_project_root: None
    copierCouchesTerminee = pyqtSignal()  # Signal pour indiquer la fin de copierCouches

    def __init__(self, iface, parent=None):

        # Liste des variables utilisables dans toute la classe
        self.forms_dir = None
        self.symbols_dir = None
        self.chemin = None
        self.not_checked_layers = None
        self.qgs_base_header = None
        self.checked_layers = None
        self.uri_source = None
        self.driver_name = None
        self.driver_map = None
        self.end_copy = None
        self.ordered_layers = None
        self.extensions_fichiers = None
        self.base_project = None
        self.base_project_path = None
        self.base_project_root = None
        self.base_project_name = None
        self.base_project_name_with_ext = None
        self.base_project_name_ext = None
        self.base_project_crs = None
        self.new_project = None
        self.new_project_path = None
        self.new_project_root = None
        self.new_project_name = None
        self.new_project_name_with_ext = None
        self.new_project_name_ext = None
        self.new_project_crs = None
        self.gpkg = None
        self.list_layers = []
        self.list_gpkg_layers = []
        self.gpkg_layer = None
        self.dirNameQgs = None
        self.dirNameQgz = None
        self.dirNameGpkg = None
        self.qgs_base_file_path = None
        self.tree_base = None
        self.root_base = None
        self.qgs_new_file_path = None
        self.tree_new = None
        self.root_new = None



        self.iface = iface
        """Constructor."""
        super(QPackageDialog, self).__init__(parent)
        # self.crs_origin = None  # Initialise crs_origin à None
        # uic.loadUi(os.path.join(os.path.dirname(__file__), 'QPackage_dialog_base.ui'), self)
        ui_path = os.path.join(os.path.dirname(__file__), 'QPackage_dialog_base.ui')
        uic.loadUi(ui_path, self)
        # self.setupUi(self)

        self.transform_context = QgsCoordinateTransformContext()

    def tr(self, message):
        return QCoreApplication.translate('QPackage_Dialog', message)

    # Conversion en chemin réel des chemins virtuels subst ou net use (Optionnel dans ce plugin)
    def query_dos_device(self, drive_letter):
        # Ajout d'un backslash pour le format correct (e.g. 'X:')
        drive = f"{drive_letter}:"

        # Taille initiale du buffer
        buffer_size = 1024
        buffer = ctypes.create_string_buffer(buffer_size)

        # Appel à la fonction QueryDosDevice
        result = ctypes.windll.kernel32.QueryDosDeviceA(drive.encode(), buffer, buffer_size)

        if result != 0:
            # Conversion du buffer en string Python
            real_path = buffer.value.decode()

            # Si le chemin contient le préfixe \??\, le retirer
            if real_path.startswith(r'\??\\'):
                real_path = real_path[4:]  # Supprimer les 4 premiers caractères (\??\)

            return real_path
        else:
            raise ctypes.WinError()

    def chercherRepertoire(self):
        filename = QFileDialog.getExistingDirectory(
            self,
            caption=self.tr("Select directory to Fling from..."),
            directory=QDir.currentPath()
        )
        if filename:
            self._repertoire.setText(filename)

    def chargerCouches(self):
        # Créez le dictionnaire de mappage des extensions
        # Récupérer le CRS du projet
        crs = QgsProject.instance().crs()
        self.crs_origin = crs.authid()  # Définit crs_origin sur l'instance
        # self._listeprojections.clear()
        data = []
        for layer in QgsProject.instance().mapLayers().values():
            casecocher = QCheckBox(layer.name())
            if layer.type() == QgsMapLayer.VectorLayer:
                casecocher.setChecked(True)
            data.append(casecocher)
        self._tableau.setModel(ModeleListeCouches(data))
        # Réinitialiser la barre de progression après l'opération
        self._progression.setRange(0, 100)
        self._progression.setValue(0)

    def on_copy_clicked(self):
        """Méthode appelée lorsque le bouton _copy est cliqué."""
        # Démarre l'animation de la barre de progression
        self._progression.setRange(0, 0)  # Met la QProgressBar en mode indéterminé

        # Lance la copie des couches
        self.copierCouches()

        # Réinitialise la barre de progression après l'opération
        self._progression.setRange(100)

    def copierCouches(self):
        # Save the current project

        if not self._repertoire.text():
            QMessageBox.critical(self, self.tr("QPackage"), self.tr("You must choose the destination directory"),
                                 QMessageBox.Ok)
            return  # Arrêter l'exécution si le répertoire n'est pas choisi

        QgsProject.instance().write()
        model = self._tableau.model()
        data = []
        layers = QgsProject.instance().mapLayers()

        #  Utilisation de Path pour les noms et chemins de fichiers
        self.base_project = QgsProject.instance()
        # Chemin absolu mode binaire
        self.base_project_path = Path(self.base_project.fileName())
        # QgsMessageLog.logMessage(self.tr(f"self.base_project_path {str(self.base_project_path)}"), level=Qgis.Info)
        # Chemin racine
        self.base_project_root = self.base_project_path.parent
        # QgsMessageLog.logMessage(self.tr(f"self.base_project_root {str(self.base_project_root)}"), level=Qgis.Info)
        # Nom seul sans l'extension
        self.base_project_name = self.base_project_path.stem
        # QgsMessageLog.logMessage(self.tr(f"self.base_project_name {str(self.base_project_name)}"), level=Qgis.Info)
        # Nom avec l'extention
        self.base_project_name_with_ext = self.base_project_path.name
        # QgsMessageLog.logMessage(self.tr(f"self.base_project_name_with_ext {str(self.base_project_name_with_ext)}"), level=Qgis.Info)
        # Extension avec le .
        self.base_project_name_ext = self.base_project_path.suffix
        # QgsMessageLog.logMessage(self.tr(f"self.base_project_name_ext {str(self.base_project_name_ext)}"), level=Qgis.Info)

        # # Création d'un dossier temporaire dans le nouveau dossier de copie
        # extracted_folder = self.create_temp_folder()

        # Crée une nouvelle instance de projet
        self.new_project = QgsProject.instance()

        # Détermine le chemin du projet en fonction de son extension
        if self.base_project_name_ext == '.qgz':
            if self._projectname.text() == self.base_project_name:
                self.new_project_path = Path(str(os.path.join(self._repertoire.text(), self._projectname.text()) + '_pack.qgs'))
                # print('self.base_project_name_ext == ".qgz" - self._projectname.text() == self.base_project_name' + str(self.new_project_path))
            else:
                self.new_project_path = Path(str(os.path.join(self._repertoire.text(), self._projectname.text()) + '.qgs'))
                # print('self.base_project_name_ext == ".qgz" - self._projectname.text() != self.base_project_name' + str(self.new_project_path))
        elif self.base_project_name_ext == '.qgs':
            if self._projectname.text() == self.base_project_name:
                self.new_project_path = Path(str(os.path.join(self._repertoire.text(), self._projectname.text()) + '_pack.qgs'))
                # print('self.base_project_name_ext == ".qgs" - self._projectname.text() == self.base_project_name' + str(self.new_project_path))
            else:
                self.new_project_path = Path(str(os.path.join(self._repertoire.text(), self._projectname.text()) + '.qgs'))
                # print('self.base_project_name_ext == ".qgs" - self._projectname.text() != self.base_project_name' + str(self.new_project_path))

        # Log des informations
        # QgsMessageLog.logMessage(self.tr(f"self.new_project_path {self.new_project_path}"), level=Qgis.Info)

        if self.new_project_path != None:
            self.new_project_root = self.new_project_path.parent
        # Chemin racine
        else:
            self.new_project_path = self._repertoire.text()
        # QgsMessageLog.logMessage(self.tr(f"self.new_project_root : {str(self.new_project_root)}"), level=Qgis.Info)

        # Nom seul sans l'extension
        self.new_project_name = self.new_project_path.stem
        # QgsMessageLog.logMessage(self.tr(f"self.new_project_name {str(self.new_project_name)}"), level=Qgis.Info)

        # Nom avec l'extension
        self.new_project_name_with_ext = self.new_project_path.name
        # QgsMessageLog.logMessage(self.tr(f"self.new_project_name_with_ext {str(self.new_project_name_with_ext)}"), level=Qgis.Info)

        # Extension avec le point
        self.new_project_name_ext = self.new_project_path.suffix
        # QgsMessageLog.logMessage(self.tr(f"self.new_project_name_ext {str(self.new_project_name_ext)}"), level=Qgis.Info)

        # Définit le chemin du projet pour le sauvegarder dans le dossier self.new_project_root
        if self.new_project_name_ext == '.qgz':
            # Appel à la fonction unzip_project dans le cas d'un projet compressé
            self.unzip_project(str(self.new_project_path), self.new_project_root)
        else:
            # Sauvegarde directe pour les projets non compressés (.qgs)
            self.new_project.write(str(os.path.join(self.new_project_root, self.new_project_name) + '.qgs'))

        # Associe le fichier de projet temporaire à l'instance du projet
        self.new_project.setFileName(str(self.new_project_path))
        # QgsMessageLog.logMessage(self.tr(f"self.new_project.fileName() {self.new_project.fileName()}"), level=Qgis.Info)

        self.base_project_crs = self.base_project.crs()
        self.new_project.setCrs(self.base_project_crs)
        self.new_project_crs = self.new_project.crs()

        # Initialise the progress bar and the steps
        self._progression.setValue(0)
        nbrecouches = 0;
        for row in model.getDonnees():
            if (row.isChecked()):
                nbrecouches += 1
        pas = float(100 / nbrecouches)
        progression = float(0)
        messageerreuraffiche = False
        # Création des listes des couches cochées et non cochées
        self.checked_layers = []
        self.not_checked_layers = []

        # Récupération des couches du projet
        project_layers = QgsProject.instance().mapLayers()

        # Itération sur les lignes du modèle de données (couches dans l'interface)
        for row in model.getDonnees():
            # Comparaison avec les items de l'arbre des couches du projet
            for layer_id, layer in project_layers.items():
                # Si le nom de la couche correspond à celui de la ligne du modèle
                if layer.name() == row.text():
                    if row.isChecked():
                        # Ajouter aux couches cochées
                        self.checked_layers.append(layer)
                    else:
                        # Ajouter à la liste le nom des couches non cochées
                        self.not_checked_layers.append(layer.name())

        # print(f"couches cochées: {str(self.checked_layers)}")
        # print(f"couches à supprimer: {str(self.not_checked_layers)}")

        # Parcourir chaque couche non cochée dans le nouveau projet et la supprimer
        for layer_name in self.not_checked_layers:
            layer = QgsProject.instance().mapLayersByName(layer_name)
            if layer:
                self.new_project.removeMapLayer(layer[0])
                # print(f"La couche '{layer_name}' a été supprimée.")
            else:
                # print(f"La couche '{layer_name}' n'a pas été trouvée.")
                pass

        for layer in self.checked_layers:
            self.chemin = Path(layer.source())
            # print('Chemin de la couche à traiter : ' + str(self.chemin))
            if layer.type() == QgsMapLayer.VectorLayer:
                layer.__class__ = QgsVectorLayer
                if (self._repertoire != ""):
                    # load the destination projection. if the selected item of the gui list is empty, we use the layer's one
                    projection = self.crs_origin

                    # for layer in self.ordered_layers:

                    # Vérification si la couche est une couche en mémoire
                    if layer.isTemporary() or not self.chemin.suffixes:
                        # Gérer les couches en mémoire
                        # print(f"La couche '{layer.name()}' est une couche en mémoire.")
                        self.driver_name = 'MEMORY'  # Utilisation d'un nom de driver fictif ou adapté
                        file_extension = self.tr('Temporary layer')
                    else:
                        file_extension = self.chemin.suffixes[-1].lstrip('.')
                        if file_extension == 'vrt':
                            self.copy_vrt_file(layer)
                            continue
                        else:
                            self.driver_name = QgsVectorFileWriter.driverForExtension(file_extension)

                    # print(f"Le driver pour l'extension '{file_extension}' est : {self.driver_name}")

                    destination_path = os.path.join(self._repertoire.text(), layer.name())

                    # Enregistrer le style de la couche source dans un fichier temporaire
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.qml') as temp_file:
                        layer.saveNamedStyle(temp_file.name)
                        temp_file_path = temp_file.name

                    self.copy_vector_layer(layer)

                    # # Ancien code de gestion du choix de la projection
                    # # projection = layer.crs().authid()
                    # # if self._listeprojections.currentText() != QApplication.translate(
                    # #         "select crs", "- Select CRS -"):
                    # #     projection = self._listeprojections.itemData(
                    # #         self._listeprojections.currentIndex())
                    # # write the qgis layer to the destination directory
                    # if os.name == 'nt':
                    #     QgsVectorFileWriter.writeAsVectorFormat(layer,
                    #                                             self._repertoire.text() + "\\" + layer.name() + ".shp",
                    #                                             "utf-8", QgsCoordinateReferenceSystem(
                    #             projection), "ESRI Shapefile")
                    # else:
                    #     QgsVectorFileWriter.writeAsVectorFormat(layer,
                    #                                             self._repertoire.text() + "/" + layer.name() + ".shp",
                    #                                             "utf-8", QgsCoordinateReferenceSystem(
                    #             projection), "ESRI Shapefile")

                    # Change the projections of the layer in the project with project projection
                    layer.setCrs(QgsCoordinateReferenceSystem(projection));
                    progression += float(pas)
                    self._progression.setValue(progression)
                else:
                    # Error message if no directory has been selected
                    if (False == messageerreuraffiche):
                        QMessageBox.critical(self,
                                             QApplication.translate("QPackage", "QPackage"),
                                             QApplication.translate("choosedestination",
                                                                              "You must choose the destination directory"),
                                             QMessageBox.Ok);
                        messageerreuraffiche = True

            # if the layer is a raster, the plugin must copy the file
            elif layer.type() == QgsMapLayer.RasterLayer:
                layer.__class__ = QgsRasterLayer
                if (self._repertoire.text() != ""):
                    if os.name == 'nt':
                        shutil.copy2(layer.publicSource(),
                                     self._repertoire.text() + "\\" + os.path.basename(
                                         layer.publicSource()))
                    else:
                        shutil.copy2(layer.publicSource(),
                                     self._repertoire.text() + "/" + os.path.basename(
                                         layer.publicSource()))

                    progression += float(pas)
                    self._progression.setValue(progression)
                else:
                    if (False == messageerreuraffiche):
                        QMessageBox.critical(self,
                                             QApplication.translate("QPackage", "QPackage"),
                                             QApplication.translate("choosedestination",
                                                                              "You must choose the destination directory"),
                                             QMessageBox.Ok);
                        messageerreuraffiche = True

        if messageerreuraffiche == False:
            # Change current project CRS before saving it
            srcCrs = self.iface.mapCanvas().mapSettings().destinationCrs()
            dstCrs = QgsCoordinateReferenceSystem(projection)
            self.iface.mapCanvas().setDestinationCrs(dstCrs)
            ext = self.iface.mapCanvas().extent()
            # trCrs = QgsCoordinateTransform(srcCrs, dstCrs)
            # self.iface.mapCanvas().setExtent(trCrs.transformBoundingBox(ext))

            # if no error
            if os.name == 'nt':
                fichierprojet = self._repertoire.text() + "\\" + (
                    os.path.basename(QgsProject.instance().fileName()))
            else:
                fichierprojet = self._repertoire.text() + "/" + (os.path.basename(QgsProject.instance().fileName()))
            # if the project exist we save it to a new directory
            QgsMessageLog.logMessage(QgsProject.instance().fileName())
            if not os.path.isfile(QgsProject.instance().fileName()):
                if self._projectname.text() != "":
                    strproject = self._projectname.text()
                    if os.name == 'nt':
                        if strproject[-4:] == ".qgs":
                            fichierprojet = self._repertoire.text() + "\\" + strproject
                        else:
                            fichierprojet = self._repertoire.text() + "\\" + strproject + ".qgs"
                    else:
                        if strproject[-4:] == ".qgs":
                            fichierprojet = self._repertoire.text() + "/" + strproject
                        else:
                            fichierprojet = self._repertoire.text() + "/" + strproject + ".qgs"
                else:
                    if os.name == 'nt':
                        fichierprojet = self._repertoire.text() + "\\project.qgs"
                    else:
                        fichierprojet = self._repertoire.text() + "/project.qgs"

            # Save the project to the new directory
            # QgsProject.instance().write(fichierprojet)
            # we change the path of the layers

            # Charger le fichier .qgs (XML)
            self.qgstree = ET.parse(str(os.path.join(self.new_project_root, self.new_project_name) + '.qgs'))
            self.qgsroot = self.qgstree.getroot()

            # Trouver tous les éléments "maplayer"
            maplayers = self.qgsroot.findall(".//maplayer")

            # Itération sur les lignes du modèle de données
            for row in model.getDonnees():
                #  Sélection des lignes avec cases cochées
                if row.isChecked():
                    # Comparaison avec les items de l'arbre des couches du projet
                    for name in QgsProject.instance().mapLayers():
                        layer = QgsProject.instance().mapLayer(name)
                        if (layer.name() == row.text()):
                            self.checked_layers.append(layer)
                            if self._repertoire.text() != "":
                                if layer.type() == QgsMapLayer.VectorLayer:
                                    for coucheprojet in maplayers:
                                        # Extraire le nom de la couche dans le fichier .qgs
                                        coucheprojetnom = coucheprojet.find('.//layername').text
                                        if coucheprojetnom == layer.name():
                                            # Gérer la projection
                                            projection = self.crs_origin
                                            # if self._listeprojections.currentText() != "":
                                            #     projection = self._listeprojections.currentText()

                                            # Construire les informations de projection
                                            pr = ET.Element("spatialrefsys")
                                            ET.SubElement(pr, "proj4").text = QgsCoordinateReferenceSystem(
                                                projection).toProj4()
                                            ET.SubElement(pr, "srsid").text = str(
                                                QgsCoordinateReferenceSystem(projection).srsid())
                                            ET.SubElement(pr, "srid").text = str(
                                                QgsCoordinateReferenceSystem(projection).postgisSrid())
                                            ET.SubElement(pr, "epsg").text = QgsCoordinateReferenceSystem(
                                                projection).authid()
                                            ET.SubElement(pr, "description").text = QgsCoordinateReferenceSystem(
                                                projection).description()
                                            ET.SubElement(pr, "projectionacronym").text = QgsCoordinateReferenceSystem(
                                                projection).projectionAcronym()
                                            ET.SubElement(pr, "ellipsoidacronym").text = QgsCoordinateReferenceSystem(
                                                projection).ellipsoidAcronym()
                                            # Remplacer l'élément 'srs'
                                            srs_element = coucheprojet.find('srs')
                                            if srs_element is not None:
                                                srs_element.clear()
                                                srs_element.append(pr)

                                            self.copy_annex_files(layer)

                                elif layer.type() == QgsMapLayer.RasterLayer:
                                    for coucheprojet in maplayers:
                                        coucheprojetnom = coucheprojet.find('layername').text
                                        if coucheprojetnom == layer.name():
                                            self.replaceText(coucheprojet.find('datasource'),
                                                             os.path.basename(layer.publicSource()))


            # Sauvegarder les modifications dans le fichier .qgs
            with codecs.open(fichierprojet, "w", encoding="utf_8") as file_handle:
                file_handle.write(ET.tostring(self.qgsroot, encoding="unicode"))

            # Mise à jour de la barre de progression
            self._progression.setValue(100)

        # Sauvegarde des modifications dans le fichier qgs
        self.new_project.write(str(self.new_project_path))

        # Modifier les chemins des couches
        for layer in self.new_project.mapLayers().values():
            if isinstance(layer, QgsVectorLayer):
                if layer.dataProvider().name() == 'memory':
                    continue
                # Obtenir le chemin actuel
                chemin_actuel = Path(layer.dataProvider().dataSourceUri())
                # print('Chemin actuel couche ' + layer.name() + ' : ' + str(chemin_actuel))
                # print('layer.dataProvider().name() : ' + str(layer.dataProvider().name()))
                if chemin_actuel != self.new_project_root:
                    # if chemin_actuel.suffix in ['.vrt', '.csv', '.odt', '.xls', '.xlsx']:
                    #     pass
                    # else:
                    nouveau_chemin = str(chemin_actuel.parent).replace(str(chemin_actuel.parent), str(self.new_project_root))
                    nouveau_chemin_complet = str(os.path.join(nouveau_chemin, chemin_actuel.stem) + str(chemin_actuel.suffix))
                    layer.setDataSource(nouveau_chemin_complet, layer.name(), layer.dataProvider().name())
                    # print('nouveau_chemin_complet : ' + str(nouveau_chemin_complet))

        # Sauvegarder les modifications dans le projet
        self.new_project.write(str(self.new_project_path))
        # Sauvegarder le nouveau projet au format qgz
        new_project_qgz_path = Path(str(os.path.join(self.new_project_root, self.new_project_name) + '.qgz'))
        self.zip_project(self.new_project_path, str(new_project_qgz_path))
        self.new_project.write(str(new_project_qgz_path))

        QgsMessageLog.logMessage(self.tr("Operation completed successfully"), level=Qgis.Info)

        self.copierCouchesTerminee.emit()


    def replaceText(self, node, newText):
        if node is None or node.text is None:
            raise Exception(self.tr("Node not contain text"))
        # Remplacer le texte directement
        node.text = newText


    def copy_vrt_file(self, layer):
        vrt_file_path = str(self.chemin)
        # Création du chemin du fichier VRT mis à jour
        new_vrt_file_path = Path(self.new_project_root) / self.chemin.name
        shutil.copy(vrt_file_path, new_vrt_file_path)
        # Ouvrir le fichier VRT avec GDAL pour vérifier s'il s'agit d'un raster ou d'un vecteur
        vrt_dataset = gdal.Open(vrt_file_path)
        if vrt_dataset is not None:
            # print("Ouvert en tant que fichier raster.")
            layer_type = "raster"
        else:
            # print(f"Ouvrir {vrt_file_path} en tant que fichier vectoriel.")
            vrt_dataset = gdal.OpenEx(vrt_file_path, gdal.OF_VECTOR)
            if vrt_dataset is None:
                # print(f"Impossible d'ouvrir le fichier VRT : {vrt_file_path}")
                return
            layer_type = "vector"

        # Analyse du fichier VRT pour identifier les fichiers sources
        tree = ET.parse(vrt_file_path)
        root = tree.getroot()
        vrt_dir = Path(vrt_file_path).parent

        for datasource in root.findall(".//SrcDataSource"):
            src_file_rel = datasource.text
            src_file_abs = (vrt_dir / src_file_rel).resolve()  # Chemin absolu du fichier source
            src_file_name = os.path.basename(src_file_abs)
            new_src_file_path = Path(self.new_project_root) / src_file_name

            # print('src_file_rel : ' + str(src_file_rel))
            # print('src_file_abs : ' + str(src_file_abs))
            # print('src_file_name : ' + str(src_file_name))
            # print('new_src_file_path : ' + str(new_src_file_path))


            # Copier le fichier source vers le répertoire de destination
            if src_file_abs.exists():
                try:
                    shutil.copy(src_file_abs, new_src_file_path)
                    # Mettre à jour le chemin dans le VRT avec le nouveau chemin relatif
                    datasource.text = new_src_file_path.name

                except Exception as e:
                    QgsMessageLog.logMessage(self.tr(f"Error copying source file {src_file_abs} : {e}"), level=Qgis.Info)
            else:
                QgsMessageLog.logMessage(self.tr(f"Source file {src_file_abs} was not copied."), level=Qgis.Info)


    def copy_vector_layer(self, layer):
        """Copier une couche vectorielle vers le répertoire de destination en remplaçant l'existante si nécessaire et l'ajouter au projet."""

        # Vérifier si la couche est une couche en mémoire
        if layer.isTemporary() or not layer.source():
            # Si la couche est en mémoire, elle doit être directement ajoutée au nouveau projet
            # print(self.tr(f"The '{layer.name()}' layer is in memory. It will be added to the new project directly."))
            # Ajouter la couche en mémoire au nouveau projet
            self.new_project.addMapLayer(layer)
            QgsMessageLog.logMessage(self.tr(f"Memory layer {layer.name()} added to the project."), level=Qgis.Info)
        else:
            chemin = Path(layer.source())

            # Construction du chemin absolu
            new_path = os.path.join(self.new_project_root, chemin.name)
            new_path = os.path.abspath(new_path)  # S'assurer que le chemin est absolu

            # Supprimer le fichier existant si présent
            if os.path.exists(new_path):
                os.remove(new_path)
                # print(f"Le fichier existant {new_path} a été supprimé.")

            # Supprimer les fichiers auxiliaires (si format Shapefile ou autre)
            base_name = os.path.splitext(new_path)[0]
            for ext in ['.shx', '.dbf', '.prj', '.cpg', '.qpj']:
                aux_file = base_name + ext
                if os.path.exists(aux_file):
                    os.remove(aux_file)
                    # print(f"Le fichier auxiliaire existant {aux_file} a été supprimé.")

            # Vérifier si le fichier source existe
            if not os.path.exists(layer.source()):
                self.show_warning_popup(f"The source file {layer.source()} does not exist.")
                return

            # Configurer les options de sauvegarde
            options = QgsVectorFileWriter.SaveVectorOptions()

            options.driverName = self.driver_name
            options.fileEncoding = "UTF-8"
            options.layerOptions = ["ENCODING=UTF-8"]

            # Contexte de transformation des coordonnées basé sur le CRS de la couche source
            context = QgsCoordinateTransformContext()

            # Copier la couche avec writeAsVectorFormatV3
            error = QgsVectorFileWriter.writeAsVectorFormatV3(
                layer,
                new_path,
                context,
                options
            )

            if error[0] != QgsVectorFileWriter.NoError:
                self.show_warning_popup(self.tr(
                    f"Error writing file from {layer.source()} to {new_path} : {error[1]}"))
                return
            else:
                QgsMessageLog.logMessage(self.tr(f"File successfully created in: {new_path}"), level=Qgis.Info)
            # Vérifier si le fichier a été créé
            if not os.path.exists(new_path):
                self.show_warning_popup(self.tr(f"The file {new_path} was not created."))
                return

    def create_temp_folder(self):
        """Créer un dossier temporaire dans un sous-dossier 'temp' à la base_path donnée."""
        temp_folder = os.path.join(self._repertoire.text(), 'temp')
       # Vérifie si le dossier existe déjà
        if os.path.exists(temp_folder):
            # Supprime le dossier temporaire existant et son contenu
            shutil.rmtree(temp_folder)
        # Crée le dossier temporaire
        os.makedirs(temp_folder)
        return temp_folder

    # Décompresser le fichier QGIS
    def unzip_project(self, qgz_path, extract_to):
        with zipfile.ZipFile(qgz_path, 'r') as zip_ref:
            zip_ref.extractall(extract_to)

    # Recompresser le fichier QGIS
    def zip_project(self, folder_path, qgz_path):
        with zipfile.ZipFile(qgz_path, 'w') as zip_ref:
            for root, dirs, files in os.walk(folder_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    zip_ref.write(file_path, os.path.relpath(file_path, folder_path))

    def copy_raster_layer(self, layer, destination_path):
        """Copier une couche raster vers le répertoire de destination."""
        raster_path = layer.publicSource()
        # Test existence du dossier
        if not os.path.exists(raster_path):
            self.show_warning_popup(raster_path)
            return

        file_size = os.path.getsize(raster_path)

        destination_full_path = os.path.normpath(
            os.path.join(self._repertoire.text(), layer.name() + os.path.splitext(raster_path)[1]))
        if os.path.normpath(raster_path) == destination_full_path:
            QgsMessageLog.logMessage(self.tr(f"Source and destination for {layer.name()} are the same, skipping copy."),
                                     level=Qgis.Warning)
        else:
            if file_size > 1e9:
                QMessageBox.warning(self, self.tr("QPackage"),
                                    self.tr(
                                        f"The file {os.path.basename(raster_path)} is large and may take a long time to copy."))

            shutil.copy2(raster_path, destination_full_path)

            new_layer = QgsRasterLayer(destination_full_path, layer.name())
            if new_layer.isValid():
                self.new_project.addMapLayer(new_layer)
            else:
                QgsMessageLog.logMessage(self.tr(f"Raster layer {layer.name()} is not valid"), level=Qgis.Warning)


    def copy_various_annex_files(self, layer):
        """Copier les fichiers SVG et le fichier editform référencés dans un fichier QML de style vers le répertoire du nouveau projet."""
        with tempfile.NamedTemporaryFile(delete=False, suffix='.qml') as temp_file:
            layer.saveNamedStyle(temp_file.name)  # Sauvegarder le style de la couche dans un fichier temporaire
            qml_path = temp_file.name
        tree = ET.parse(qml_path)
        root = tree.getroot()

        self.symbols_dir = os.path.join(self.new_project_root, 'symbols')
        self.forms_dir = os.path.join(self.new_project_root, 'forms')

        # Rechercher les balises <Option> ayant l'attribut name="name" et vérifier si la valeur se termine par .svg
        option_elements = root.findall(".//Option[@name='name']")
        for option in option_elements:
            svg_path = option.attrib.get('value')
            if svg_path and svg_path.lower().endswith('.svg') and os.path.exists(svg_path):
                # Créer le sous-dossier symbols s'il n'existe pas
                os.makedirs(self.symbols_dir, exist_ok=True)
                # Copier le fichier SVG vers le sous-dossier symbols
                svg_file_name = os.path.basename(svg_path)
                new_svg_path = os.path.join(self.symbols_dir, svg_file_name)
                shutil.copy2(svg_path, new_svg_path)
                # Mettre à jour le chemin SVG dans le fichier XML
                option.set('value', new_svg_path)

        qgs_path = os.path.join(self.new_project_root, self.new_project_name + '.qgs')
        tree.write(qgs_path)
        self.qgstree.write(qgs_path)


    def is_subst_drive(self, path):
        """Vérifie si le lecteur du chemin est mappé via la commande SUBST."""
        try:
            # Exécute la commande `subst` pour obtenir la liste des lecteurs mappés
            result = subprocess.run(['subst'], stdout=subprocess.PIPE, text=True)
            subst_output = result.stdout.strip()

            # Si le chemin commence par une lettre de lecteur mappé via subst
            for line in subst_output.splitlines():
                if line:
                    virtual_drive, actual_path = line.split(': => ')
                    if path.drive.upper() == f"{virtual_drive.upper()}:":
                        return True
            return False
        except Exception as e:
            QgsMessageLog.logMessage(f"Error checking subst drives: {str(e)}", level=Qgis.Warning)
            return False

    def is_net_use_drive(self, path):
        """Vérifie si le lecteur du chemin est mappé via la commande NET USE."""
        try:
            # Exécute la commande `net use` pour obtenir la liste des lecteurs réseau mappés
            result = subprocess.run(['net', 'use'], stdout=subprocess.PIPE, text=True)
            net_use_output = result.stdout.strip()

            # Si le chemin commence par une lettre de lecteur mappé via net use
            for line in net_use_output.splitlines():
                if line.startswith(path.drive.upper()):
                    return True
            return False
        except Exception as e:
            QgsMessageLog.logMessage(f"Error checking net use drives: {str(e)}", level=Qgis.Warning)
            return False

    def is_system_svg_path(self, svg_path):
        """Vérifie si le chemin SVG relatif appartient aux répertoires des symboles SVG intégrés à QGIS."""
        svg_paths = QgsApplication.svgPaths()  # Obtenir les répertoires système des SVG
        for base_svg_path in svg_paths:
            potential_svg_path = Path(base_svg_path) / svg_path
            if potential_svg_path.exists():
                return potential_svg_path
            return None


    def copy_annex_files(self, layer):
        """Copier les fichiers SVG référencés dans un fichier QML de style vers un sous-dossier 'symbols' dans le répertoire du nouveau projet."""
        self.copy_various_annex_files(layer)

        # Mise à jour des chemins dans le renderer QGIS
        def update_svg_paths_in_renderer(renderer):
            """Mise à jour des chemins SVG pour les renderers."""
            if isinstance(renderer, QgsCategorizedSymbolRenderer):
                QgsMessageLog.logMessage(self.tr("Updating Categorized Renderer"), level=Qgis.Info)
                for category in renderer.categories():
                    symbol = category.symbol()
                    update_symbol_svg_paths(symbol, self.symbols_dir)
            elif isinstance(renderer, QgsRuleBasedRenderer):
                QgsMessageLog.logMessage(self.tr("Updating Rule-Based Renderer"), level=Qgis.Info)
                root_rule = renderer.rootRule()
                process_rule(root_rule, self.symbols_dir)
            elif isinstance(renderer, QgsSingleSymbolRenderer):
                symbol = renderer.symbol()
                update_symbol_svg_paths(symbol, self.symbols_dir)
            else:
                QgsMessageLog.logMessage(self.tr("Noting to made"), level=Qgis.Info)
                # QgsMessageLog.logMessage(self.tr("Updating Single Symbol Renderer"), level=Qgis.Info)
                # symbol = renderer.symbol()
                # update_symbol_svg_paths(symbol, self.symbols_dir)


        def update_symbol_svg_paths(symbol, symbols_dir):
            """Mise à jour des chemins SVG dans les symboles."""
            for i in range(symbol.symbolLayerCount()):
                svg_symbol_layer = symbol.symbolLayer(i)
                if isinstance(svg_symbol_layer, QgsSvgMarkerSymbolLayer):
                    svg_name = Path(svg_symbol_layer.path()).name
                    new_svg_path = os.path.join(symbols_dir, svg_name)
                    svg_symbol_layer.setPath(new_svg_path)

        def process_rule(rule, symbols_dir, visited_rules=None):
            """Fonction récursive pour traiter les règles imbriquées."""
            if visited_rules is None:
                visited_rules = set()
            if rule in visited_rules:
                return  # Évite la boucle infinie si on revisite la même règle
            visited_rules.add(rule)

            QgsMessageLog.logMessage(self.tr(f"Processing rule: {rule}"), level=Qgis.Info)

            symbol = rule.symbol()
            if symbol is None:
                QgsMessageLog.logMessage(self.tr(f"No symbol found for rule: {rule}"), level=Qgis.Warning)
            else:
                update_symbol_svg_paths(symbol, symbols_dir)

            # Récursion pour les règles enfants
            for child_rule in rule.children():
                process_rule(child_rule, symbols_dir, visited_rules)

        # Appliquer les mises à jour aux renderers
        renderer = layer.renderer()
        update_svg_paths_in_renderer(renderer)

        # Lire la configuration du formulaire d'édition
        form_config = layer.editFormConfig()

        # Obtenir le chemin du fichier du formulaire d'édition
        origin_form_path = Path(form_config.uiForm())

        # Lire et modifier la balise editforminitfilepath
        init_file_path = form_config.initFilePath()
        origin_init_file_path = Path(init_file_path)

        # Vérifier si le chemin du fichier du formulaire d'édition est valide
        if origin_form_path.is_file():
            # Créer le sous-dossier forms s'il n'existe pas
            os.makedirs(self.forms_dir, exist_ok=True)

            # Copier le fichier du formulaire UI vers le sous-dossier forms
            form_file_name = os.path.basename(origin_form_path)
            new_form_path = os.path.join(self.forms_dir, form_file_name)
            print(f"Le chemin d'origine du formulaire est : {str(origin_form_path)}")
            print(f"Le nouveau chemin du formulaire est : {str(new_form_path)}")

            try:
                # Copier le fichier de formulaire d'édition
                shutil.copy2(origin_form_path, new_form_path)
                form_config.setUiForm(str(new_form_path))  # Modifier le chemin du formulaire d'édition
                print(f"Chemin modifié pour le formulaire : {str(new_form_path)}")
            except PermissionError as e:
                print(f"Erreur de permission lors de la copie de {origin_form_path} vers {new_form_path}: {e}")
        else:
            print(f"Le chemin {str(origin_form_path)} n'est pas un fichier valide.")

        # Vérifier si le chemin du fichier initForm est valide
        if origin_init_file_path.is_file():
            # Copier le fichier editforminitfilepath vers le sous-dossier forms
            init_file_name = os.path.basename(origin_init_file_path)
            new_init_file_path = os.path.join(self.forms_dir, init_file_name)
            print(f"Le chemin d'origine du fichier init est : {str(origin_init_file_path)}")
            print(f"Le nouveau chemin du fichier init est : {str(new_init_file_path)}")

            try:
                # Copier le fichier d'initialisation
                shutil.copy2(origin_init_file_path, new_init_file_path)
                form_config.setInitFilePath(str(new_init_file_path))  # Modifier le chemin du fichier init
                print(f"Chemin modifié pour le fichier init : {str(new_init_file_path)}")
            except PermissionError as e:
                print(
                    f"Erreur de permission lors de la copie de {origin_init_file_path} vers {new_init_file_path}: {e}")
        else:
            print(f"Le chemin {str(origin_init_file_path)} n'est pas un fichier valide.")

        # Appliquer les modifications de la configuration à la couche (si nécessaire)
        layer.setEditFormConfig(form_config)  # Appliquer la nouvelle configuration du formulaire et init

        # Facultatif : Si votre couche nécessite une validation/sauvegarde explicite
        # layer.commitChanges()

        # Assurez-vous que la mise à jour n'est appelée qu'une seule fois
        if not hasattr(layer, 'is_updated'):
            layer.is_updated = True
            # Rafraîchir la couche pour appliquer les changements
            layer.triggerRepaint()
        QgsMessageLog.logMessage(self.tr("All SVG symbols updated successfully."), level=Qgis.Info)


    def update_svg_paths(self, layer, new_project_dir):
        """Mettre à jour les chemins des fichiers SVG dans les propriétés des couches."""
        symbols_dir = os.path.join(new_project_dir, 'symbols')
        symbols = layer.renderer().symbols(QgsRenderContext())
        for symbol in symbols:
            for symbol_layer in symbol.symbolLayers():
                if isinstance(symbol_layer, QgsSvgMarkerSymbolLayer):
                    svg_path = symbol_layer.path()
                    if os.path.exists(svg_path):
                        svg_file_name = os.path.basename(svg_path)
                        new_svg_path = os.path.join(symbols_dir, svg_file_name)
                        shutil.copy2(svg_path, new_svg_path)
                        symbol_layer.setPath(new_svg_path.replace(os.path.sep, '/'))
                    else:
                        self.show_warning_popup(svg_path)

    def update_ui_py_paths(self, layer, new_project_dir):
        """Mettre à jour les chemins des fichiers UI et PY dans les propriétés des couches."""
        if layer.type() == QgsMapLayer.VectorLayer:
            # Accéder directement aux propriétés personnalisées de la couche
            ui_path = layer.customProperty('ui_path', '')
            py_path = layer.customProperty('py_path', '')

            # Mettre à jour les chemins des fichiers .ui et .py
            new_ui_path = self.update_path_in_url(ui_path, new_project_dir, '.ui', 'forms')
            new_py_path = self.update_path_in_url(py_path, new_project_dir, '.py', 'pyfiles')

            # Définir de nouvelles valeurs pour les propriétés personnalisées
            layer.setCustomProperty('ui_path', new_ui_path)
            layer.setCustomProperty('py_path', new_py_path)

            QgsMessageLog.logMessage(
                self.tr(f"Updated UI/PY paths for {layer.name()}: UI={new_ui_path}, PY={new_py_path}"),
                level=Qgis.Info
            )

    def update_path_in_url(self, original_path, new_project_dir, extension, subdir):
        """Mettre à jour un chemin de fichier dans une URL vers un sous-dossier spécifique dans le nouveau répertoire."""
        if original_path and os.path.exists(original_path):
            new_path = os.path.join(new_project_dir, subdir, os.path.basename(original_path))
            shutil.copy2(original_path, new_path)
            return new_path
        elif original_path:
            self.show_warning_popup(original_path)
        return ''

    def show_warning_popup(self, missing_path):
        """Afficher une fenêtre d'alerte pour les chemins manquants."""
        message = self.tr(
            f"{missing_path}' was not found. Please check the file path or the drive letter.")
        # Inscription du fichier non trouvé dans le journal :
        QgsMessageLog.logMessage(message, level=Qgis.Info)
        # Fenêtre surgissante remplacée :
        # QMessageBox.warning(self, self.tr("QPackage"), message)


    def read_xml_header(self, file_path):
        header = ""
        # Ouvrir le fichier XML en mode lecture
        with open(file_path, 'r', encoding='utf-8') as file:
            # Lire ligne par ligne jusqu'à la première balise XML non déclarative
            for line in file:
                # Vérifier si la ligne contient l'entête XML ou DOCTYPE
                if line.strip().startswith('<?xml') or line.strip().startswith('<!DOCTYPE'):
                    header += line.strip() + "\n"
                else:
                    # Sortir dès qu'on atteint le début du contenu XML (par exemple, <root>)
                    break
        return header


    def modify_path_in_qgz_file(self, new_csv_path):
        # Répertoire temporaire pour l'extraction
        temp_dir = 'temp_extraction'
        # Créer le répertoire d'extraction s'il n'existe pas
        os.makedirs(temp_dir, exist_ok=True)
        # Extraire le contenu du fichier .qgz
        with zipfile.ZipFile(self.new_project_path, 'r') as zip_ref:
            zip_ref.extractall(temp_dir)
        qgs_file_path = self.new_project_path.stem + '.qgs'
        # Charger le fichier .qgs en tant qu'arbre XML
        tree = ET.parse(qgs_file_path)
        root = tree.getroot()
        # Modification du chemin
        options = root.findall(".//Option[@name='LayerSource']")
        # Parcours des éléments trouvés pour mettre à jour le chemin
        for option in options:
            ancien_chemin = option.get('value')
            # ancien_chemin = self.uri_source
            message = self.tr(
                f"Path to replace : {ancien_chemin}. To replace by {new_csv_path} if {ancien_chemin} == {self.uri_source}")
            QgsMessageLog.logMessage(message, level=Qgis.Info)
            if ancien_chemin == self.uri_source:
                option.set('value', new_csv_path)
                # print(f"Chemin remplacé : {ancien_chemin} par {new_csv_path}")
        # Recompresser le répertoire d'extraction en un fichier .qgz
        with zipfile.ZipFile(self.new_project_path, 'w') as zip_ref:
            for foldername, subfolders, filenames in os.walk(temp_dir):
                for filename in filenames:
                    file_path = os.path.join(foldername, filename)
                    zip_ref.write(file_path, os.path.relpath(file_path, temp_dir))

        # Supprimer le répertoire temporaire
        shutil.rmtree(temp_dir)
