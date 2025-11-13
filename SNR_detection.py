import csv
import numpy as np
import matplotlib.pyplot as plt
import os
import re
from pathlib import Path

def load_psd_csv(filepath, RBW=None):
    """
    Carga archivo CSV con columnas: Frequency (Hz), PSD (dB*, V²/Hz, etc.).
    Tolera encabezados diferentes (dBm, dBFS, etc.) y filas inválidas.

    Parámetros:
    ------------
    filepath : str
        Ruta del archivo CSV a cargar.
    RBW : float o None, opcional
        Ancho de banda de resolución (Hz). Si se pasa, ajusta la PSD sumando 10*log10(RBW).

    Retorna:
    --------
    freqs : np.ndarray
        Frecuencias (Hz)
    psd   : np.ndarray
        PSD (ajustada si RBW != None)
    """

    freqs, psd = [], []

    if not os.path.exists(filepath):
        print(f"[ERROR] Archivo no encontrado: {filepath}")
        return np.array([]), np.array([])

    with open(filepath, 'r', newline='') as f_csv:
        reader = csv.reader(f_csv)
        try:
            header = next(reader)  # leer encabezado
        except StopIteration:
            print(f"[WARN] Archivo vacío: {filepath}")
            return np.array([]), np.array([])

        for row in reader:
            if len(row) < 2:
                continue
            try:
                freq = float(row[0].strip())
                val = float(row[1].strip())
                freqs.append(freq)
                psd.append(val)
            except ValueError:
                # Ignorar filas no numéricas o mal formateadas
                continue

    if len(freqs) == 0 or len(psd) == 0:
        print(f"[WARN] Sin datos válidos en {filepath}")
        return np.array([]), np.array([])

    freqs = np.array(freqs)
    psd = np.array(psd)

    # --- Ajuste por RBW (si aplica) ---
    if RBW is not None and RBW > 0:
        psd = psd + 10 * np.log10(RBW)
        print(f"[INFO] PSD ajustada a DANL con RBW = {RBW:.2f} Hz")

    # --- Reemplazar NaN o infinitos ---
    psd = np.nan_to_num(psd, nan=-200, posinf=-200, neginf=-200)

    return freqs, psd


def detect_noise_floor_from_psd(Pxx, delta_dB=2.0):
    """Detecta el piso de ruido en un vector PSD (en dB)."""
    if len(Pxx) == 0:
        raise ValueError("PSD vacía, no se puede detectar piso de ruido.")

    Pmin = np.min(Pxx)
    Pmax = np.max(Pxx)
    centers = np.arange(Pmin + delta_dB/2, Pmax, delta_dB/2)
    results = []

    for c in centers:
        lower = c - delta_dB/2
        upper = c + delta_dB/2
        segment = Pxx[(Pxx >= lower) & (Pxx < upper)]
        if len(segment) == 0:
            continue
        count = len(segment)
        results.append({"center_dB": c, "count": count})

    if not results:
        raise RuntimeError("No se generaron histogramas válidos en detect_noise_floor_from_psd().")

    best_segment = max(results, key=lambda x: x["count"])
    return best_segment["center_dB"]


def analyze_noise_floor_all(folder_path, delta_dB=0.5, plot=True):
    """Analiza todos los archivos CSV de PSD en la carpeta dada."""

    # Buscar archivos válidos sin depender del tipo de escala (dBm o dBFS)
    all_files = [
        f for f in os.listdir(folder_path)
        if f.lower().startswith("psd_output_") and f.lower().endswith(".csv")
    ]

    if not all_files:
        print(f"[ERROR] No se encontraron archivos CSV válidos en {folder_path}")
        return None

    # Extraer la frecuencia central de cada nombre (por ejemplo psd_output_dbfs_98.csv)
    def extract_fc(filename):
        match = re.search(r"psd_output_[a-zA-Z]+_(\d+)", filename)
        return int(match.group(1)) if match else None

    files_with_fc = [(extract_fc(f), f) for f in all_files if extract_fc(f) is not None]
    files_with_fc.sort(key=lambda x: x[0])

    if not files_with_fc:
        print("[ERROR] No se pudieron extraer frecuencias centrales de los nombres de archivo.")
        return None

    frecs_MHz, pisos_dB = [], []

    print("🔎 Iniciando análisis de piso de ruido...\n")

    for fc, fname in files_with_fc:
        filepath = os.path.join(folder_path, fname)
        f, Pxx = load_psd_csv(filepath, RBW=None)
        if len(Pxx) == 0:
            print(f"[WARN] Saltando {fname}: sin datos válidos.")
            continue
        try:
            piso_dB = detect_noise_floor_from_psd(Pxx, delta_dB=delta_dB)
            frecs_MHz.append(fc)
            pisos_dB.append(piso_dB)
            print(f"  • {fname:<30} → Piso de ruido = {piso_dB:.2f} dB")
        except Exception as e:
            print(f"[WARN] No se pudo analizar {fname}: {e}")
            continue

    if len(pisos_dB) == 0:
        print("[ERROR] No se pudieron obtener pisos de ruido válidos.")
        return None

    frecs_MHz = np.array(frecs_MHz)
    pisos_dB = np.array(pisos_dB)

    # Cálculos estadísticos
    piso_prom = np.mean(pisos_dB)
    piso_min = np.min(pisos_dB)
    piso_max = np.max(pisos_dB)
    fc_min = frecs_MHz[np.argmin(pisos_dB)]
    fc_max = frecs_MHz[np.argmax(pisos_dB)]

    print("\n📊 Resultados globales:")
    print(f"  Promedio piso de DANL: {piso_prom:.2f} dB")
    print(f"  Mínimo: {piso_min:.2f} dBFS en {fc_min} MHz")
    print(f"  Máximo: {piso_max:.2f} dBFS en {fc_max} MHz")

    # Gráfica global
    if plot and len(frecs_MHz) > 0:
        plt.figure(figsize=(9, 5))
        plt.plot(frecs_MHz, pisos_dB, marker='o', lw=1.5)
        plt.axhline(piso_prom, color='r', linestyle='--', lw=1.2,
                    label=f"Promedio DANL = {piso_prom:.2f} dB")
        plt.title("Evolución DANL vs frecuencia central")
        plt.xlabel("Frecuencia central [MHz]")
        plt.ylabel("DANL [dBFS]")
        plt.grid(True)
        plt.legend()
        plt.tight_layout()
        plt.show()

    return {
        "frecs_MHz": frecs_MHz,
        "pisos_dB": pisos_dB,
        "piso_prom": piso_prom,
        "piso_min": piso_min,
        "piso_max": piso_max,
        "fc_min": fc_min,
        "fc_max": fc_max,
    }


# === Ejemplo de uso ===
if __name__ == "__main__":
        # Obtiene el directorio donde está este script Python actual
    base_dir = Path(__file__).resolve().parent
    ruta_outputs = base_dir/"Output_DANL_dbfs2"
    resultados = analyze_noise_floor_all(ruta_outputs, delta_dB=0.5)
