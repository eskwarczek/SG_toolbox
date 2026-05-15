import os
import zipfile
import shutil
from datetime import datetime
import arcpy
from arcgis.gis import GIS

def utworz_nazwe_backupu(folder_docelowy):
    data = datetime.now().strftime("%Y-%m-%d")

    podstawowa_nazwa = f"Backup_AGOL_{data}"
    nazwa = podstawowa_nazwa

    licznik = 2

    while (
        arcpy.Exists(os.path.join(folder_docelowy, f"{nazwa}.gdb")) or
        os.path.exists(os.path.join(folder_docelowy, f"{nazwa}.zip"))
    ):
        nazwa = f"{podstawowa_nazwa}_{licznik}"
        licznik += 1

    return nazwa

CACHE_FILE = os.path.join(os.path.expanduser("~"), "agol_backup_last_path.txt")

def zapisz_ostatnia_sciezke(path):
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            f.write(path)
    except:
        pass

def wczytaj_ostatnia_sciezke():
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return f.read().strip()
    except:
        pass
    return None

def utworz_geobaze(folder_docelowy, nazwa_gdb):
    sciezka_gdb = os.path.join(folder_docelowy, nazwa_gdb)
    if not arcpy.Exists(sciezka_gdb):
        arcpy.AddMessage(f"Tworzenie geobazy: {nazwa_gdb}")
        arcpy.CreateFileGDB_management(folder_docelowy, nazwa_gdb)
    return sciezka_gdb

def pobierz_hosted_layers(gis, limit_warstw):
    user = gis.users.me
    items = user.items(max_items=1000)

    hosted_layers = []
    for item in items:
        if item.type == "Feature Service" and "Hosted Service" in item.typeKeywords:
            hosted_layers.append(item)

    # jeśli limit nie ustawiony → brak ograniczenia
    if limit_warstw is None:
        return hosted_layers

    # zabezpieczenie
    limit_warstw = int(limit_warstw)

    return hosted_layers[:limit_warstw]

def eksportuj_warstwy_do_gdb(hosted_layers, sciezka_gdb, dodaj_do_mapy):
    folder_roboczy = os.path.dirname(sciezka_gdb)
        
    if dodaj_do_mapy:
        aprx = arcpy.mp.ArcGISProject("CURRENT")
        mapa = aprx.activeMap
    
    for layer in hosted_layers:
        try:
            arcpy.AddMessage(f"--- Przetwarzanie: {layer.title} ---")

            # 1. Eksport do tymczasowego FGDB w chmurze
            export_item = layer.export(
                title=f"temp_export_{layer.id}",
                export_format="File Geodatabase"
            )

            # 2. Pobranie ZIPa na dysk
            zip_path = export_item.download(save_path=folder_roboczy)
            
            # 3. Rozpakowanie ZIPa
            temp_extract_dir = os.path.join(folder_roboczy, f"temp_{layer.id}")
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(temp_extract_dir)

            # 4. Import do wspólnej bazy
            for root, dirs, _ in os.walk(temp_extract_dir):
                for d in dirs:
                    if d.endswith(".gdb"):
                        gdb_tymczasowa = os.path.join(root, d)
                        arcpy.env.workspace = gdb_tymczasowa
                        fcs = arcpy.ListFeatureClasses()
                        
                        for fc in fcs:

                            nowa_nazwa = arcpy.ValidateTableName(
                                f"{layer.title}_{fc}",
                                sciezka_gdb
                            )

                            arcpy.FeatureClassToFeatureClass_conversion(
                                fc,
                                sciezka_gdb,
                                nowa_nazwa
                            )

                            fc_path = os.path.join(
                                sciezka_gdb,
                                nowa_nazwa
                            )

                            # Dodanie do mapy
                            if dodaj_do_mapy:
                                mapa.addDataFromPath(fc_path)

                            arcpy.AddMessage(
                                f"  Dodano do bazy: {nowa_nazwa}"
                            )

            # 5. Sprzątanie
            export_item.delete()
            os.remove(zip_path)
            shutil.rmtree(temp_extract_dir)
            arcpy.AddMessage(f"  Wyczyszczono pliki tymczasowe")

        except Exception as e:
            arcpy.AddError(f"  Błąd podczas importu {layer.title}: {str(e)}")

def zipuj_geobaze(sciezka_gdb, sciezka_zip):
    arcpy.AddMessage(f"Pakowanie geobazy do ZIP...")
    with zipfile.ZipFile(sciezka_zip, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(sciezka_gdb):
            for file in files:
                if file.endswith('.lock'):
                    continue
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, os.path.dirname(sciezka_gdb))
                zipf.write(full_path, rel_path)

if __name__ == "__main__":
    # Parametr wejściowy
    # Oczekuje się, że użytkownik wybierze folder docelowy dla backupu
    folder_backupu = arcpy.GetParameterAsText(0)

    if not folder_backupu:
        folder_backupu = wczytaj_ostatnia_sciezke()
    # Zabezpieczenie: jeśli nadal nie ma ścieżki, przerwij skrypt
    if not folder_backupu:
        arcpy.AddError("Brak zdefiniowanego folderu docelowego!")
        raise ValueError("Folder docelowy nie został określony.")
        
    # Normalizacja ścieżki systemowej
    folder_backupu = os.path.normpath(folder_backupu)

    zapisz_ostatnia_sciezke(folder_backupu)
    arcpy.AddMessage(f"Zapamiętano ścieżkę backupu: {folder_backupu}")
    
    dodaj_do_mapy = arcpy.GetParameter(1)
    # Jeśli parametr pusty -> False
    if dodaj_do_mapy is None:
        dodaj_do_mapy = False
    
    # Sterowanie dodawaniem wyników do projektu/mapy
    arcpy.env.addOutputsToMap = dodaj_do_mapy
    
    limit_warstw = arcpy.GetParameterAsText(2)

    if limit_warstw == "" or limit_warstw is None:
        limit_warstw = None

    # Inicjalizacja GIS (używa aktywnego połączenia w ArcGIS Pro)
    gis = GIS("home")
    arcpy.AddMessage(f"Zalogowano jako: {gis.users.me.username}")

    # Przygotowanie nazw
    nazwa_backupu = utworz_nazwe_backupu(folder_backupu)
    nazwa_gdb = f"{nazwa_backupu}.gdb"
    sciezka_gdb = utworz_geobaze(folder_backupu, nazwa_gdb)
    sciezka_zip = os.path.join(folder_backupu, f"{nazwa_backupu}.zip")

    # Logika główna
    layers = pobierz_hosted_layers(gis, limit_warstw)
    arcpy.AddMessage(f"Znaleziono {len(layers)} hosted feature layers do pobrania.")
    
    eksportuj_warstwy_do_gdb(layers, sciezka_gdb, dodaj_do_mapy)
    zipuj_geobaze(sciezka_gdb, sciezka_zip)

    arcpy.AddMessage(f"PROCES ZAKOŃCZONY!")
    arcpy.AddMessage(f"Plik wynikowy: {sciezka_zip}")