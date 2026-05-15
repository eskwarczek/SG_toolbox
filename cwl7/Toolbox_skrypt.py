import os
import zipfile
import shutil
from datetime import datetime
import arcpy
from arcgis.gis import GIS

def utworz_nazwe_backupu():
    data = datetime.now().strftime("%Y-%m-%d")
    return f"Backup_AGOL_{data}"

def utworz_geobaze(folder_docelowy, nazwa_gdb):
    sciezka_gdb = os.path.join(folder_docelowy, nazwa_gdb)
    if not arcpy.Exists(sciezka_gdb):
        arcpy.AddMessage(f"Tworzenie geobazy: {nazwa_gdb}")
        arcpy.CreateFileGDB_management(folder_docelowy, nazwa_gdb)
    return sciezka_gdb

def pobierz_hosted_layers(gis):
    user = gis.users.me
    items = user.items(max_items=1000)
    hosted_layers = []
    for item in items:
        if item.type == "Feature Service" and "Hosted Service" in item.typeKeywords:
            hosted_layers.append(item)
    
    # Ograniczenie do 2 warstw zgodnie z Twoim kodem
    return hosted_layers[:2]

def eksportuj_warstwy_do_gdb(hosted_layers, sciezka_gdb):
    folder_roboczy = os.path.dirname(sciezka_gdb)
    
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
                            nowa_nazwa = arcpy.ValidateTableName(f"{layer.title}_{fc}", sciezka_gdb)
                            arcpy.FeatureClassToFeatureClass_conversion(fc, sciezka_gdb, nowa_nazwa)
                            arcpy.AddMessage(f"  ✔ Dodano do bazy: {nowa_nazwa}")

            # 5. Sprzątanie
            export_item.delete()
            os.remove(zip_path)
            shutil.rmtree(temp_extract_dir)
            arcpy.AddMessage(f"  🗑 Wyczyszczono pliki tymczasowe")

        except Exception as e:
            arcpy.AddError(f"  ❌ Błąd podczas importu {layer.title}: {str(e)}")

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
    # PARAMETR WEJŚCIOWY Z TOOLBOXA
    # W ustawieniach narzędzia ustaw typ na "Folder"
    folder_backupu = arcpy.GetParameterAsText(0)

    # Inicjalizacja GIS (używa aktywnego połączenia w ArcGIS Pro)
    gis = GIS("home")
    arcpy.AddMessage(f"Zalogowano jako: {gis.users.me.username}")

    # Przygotowanie nazw
    nazwa_backupu = utworz_nazwe_backupu()
    nazwa_gdb = f"{nazwa_backupu}.gdb"
    sciezka_gdb = utworz_geobaze(folder_backupu, nazwa_gdb)
    sciezka_zip = os.path.join(folder_backupu, f"{nazwa_backupu}.zip")

    # Logika główna
    layers = pobierz_hosted_layers(gis)
    arcpy.AddMessage(f"Znaleziono {len(layers)} hosted feature layers do pobrania.")
    
    eksportuj_warstwy_do_gdb(layers, sciezka_gdb)
    zipuj_geobaze(sciezka_gdb, sciezka_zip)

    arcpy.AddMessage(f"PROCES ZAKOŃCZONY!")
    arcpy.AddMessage(f"Plik wynikowy: {sciezka_zip}")