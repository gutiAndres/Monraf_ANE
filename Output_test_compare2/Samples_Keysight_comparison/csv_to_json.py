import csv
import json
from pathlib import Path

# ============================
# Parámetros
# ============================

DEVICE_ID = 7  # mismo para todos los JSON
CSV_PATTERN = "psd_comparison_*.csv"  # patrón de búsqueda

# Directorio base: donde está este script
BASE_DIR = Path(__file__).resolve().parent

# Carpeta de salida para los JSON
JSON_DIR = BASE_DIR / "Jsons_samples"
JSON_DIR.mkdir(exist_ok=True)  # crea la carpeta si no existe

def procesar_csv_a_json(csv_path: Path, device_id: int = DEVICE_ID):
    """
    Lee un CSV con columnas:
        Freq_Hz, N9000B_PSD, HackRF_PSD_interp
    y genera un diccionario listo para guardarse como JSON.
    """
    freqs = []
    pxx_n9000b = []
    pxx_hack = []

    with csv_path.open("r", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            freq = float(row["Freq_Hz"])
            n9000_val = float(row["N9000B_PSD"])
            hack_val = float(row["HackRF_PSD_interp"])

            freqs.append(freq)
            pxx_n9000b.append(n9000_val)
            pxx_hack.append(hack_val)

    if not freqs:
        raise ValueError(f"El archivo {csv_path} no tiene datos.")

    # Frecuencias inicial y final
    start_freq_hz = int(round(min(freqs)))
    end_freq_hz = int(round(max(freqs)))

    json_data = {
        "device_id": device_id,
        "Pxx_hack": pxx_hack,
        "Pxx_n9000b": pxx_n9000b,
        "start_freq_hz": start_freq_hz,
        "end_freq_hz": end_freq_hz,
    }

    return json_data

def main():
    # Buscar todos los CSV
    csv_files = sorted(BASE_DIR.glob(CSV_PATTERN))

    if not csv_files:
        print(f"No se encontraron archivos con patrón {CSV_PATTERN} en {BASE_DIR}")
        return

    for csv_path in csv_files:
        print(f"Procesando {csv_path.name}...")

        json_data = procesar_csv_a_json(csv_path, device_id=DEVICE_ID)

        # Nombre del archivo JSON → usar misma base pero dentro de Jsons_samples
        json_filename = csv_path.stem + ".json"
        json_path = JSON_DIR / json_filename

        with json_path.open("w", encoding="utf-8") as f:
            json.dump(json_data, f, indent=4)

        print(f"  -> JSON guardado en {json_path}")

if __name__ == "__main__":
    main()
