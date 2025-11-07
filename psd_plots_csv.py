import os
import csv
import numpy as np
import matplotlib.pyplot as plt

def load_psd_csv(filepath):
    """Carga archivo CSV con columnas: Frequency (Hz), PSD (dBm)."""
    freqs, psd = [], []
    with open(filepath, 'r') as f_csv:
        reader = csv.reader(f_csv)
        next(reader)  # saltar encabezado
        for row in reader:
            try:
                freqs.append(float(row[0]))
                psd.append(float(row[1]))
            except ValueError:
                continue
    return np.array(freqs), np.array(psd)


def remove_dc_spike(Pxx, n_dc=10):
    """
    Elimina el pico DC (centro) reemplazando ±n_dc puntos alrededor del centro
    con los valores vecinos (de n_dc a 2*n_dc de distancia).
    """
    N = len(Pxx)
    center = N // 2

    # Copia para no modificar original
    Pxx_clean = Pxx.copy()

    left_ref = Pxx[center - 2*n_dc:center - n_dc]
    right_ref = Pxx[center + n_dc:center + 2*n_dc]

    # Verifica longitudes iguales
    if len(left_ref) == len(right_ref) == n_dc:
        Pxx_clean[center - n_dc:center] = left_ref
        Pxx_clean[center:center + n_dc] = right_ref
    else:
        print("[WARN] Segmentos insuficientes para limpiar DC spike.")
    
    return Pxx_clean


def concat_and_plot_psd(base_path, n_psd, points_to_trim=3, n_dc=10):
    """
    Concatena y grafica las primeras `n_psd` PSDs desde CSVs.
    Elimina bordes y el pico DC antes de concatenar.
    """
    frecuencias_centrales = list(range(10, 5990, 20))[:n_psd]  # MHz

    all_freqs = []
    all_psd = []

    for fc in frecuencias_centrales:
        filename = f"psd_output_dBm_{fc}.csv"
        filepath = os.path.join(base_path, filename)

        if not os.path.exists(filepath):
            print(f"[WARN] No se encontró: {filepath}")
            continue

        f, Pxx = load_psd_csv(filepath)

        # --- Eliminar bordes ---
        if len(f) > 2 * points_to_trim:
            f = f[points_to_trim:-points_to_trim]
            Pxx = Pxx[points_to_trim:-points_to_trim]
        else:
            print(f"[WARN] Archivo {filename} demasiado corto para recortar bordes.")
            continue

        # --- Eliminar el DC spike ---
        Pxx = remove_dc_spike(Pxx, n_dc=n_dc)

        # --- Desplazar eje de frecuencia según frecuencia central ---
        f_total = f + fc * 1e6  # desplazar al rango absoluto

        all_freqs.append(f_total)
        all_psd.append(Pxx)

    if not all_freqs:
        raise RuntimeError("No se cargaron archivos CSV válidos.")

    freq_concat = np.concatenate(all_freqs)
    psd_concat = np.concatenate(all_psd)

    # === Graficar ===
    plt.figure(figsize=(12, 6))
    plt.plot(freq_concat / 1e6, psd_concat, lw=0.8)
    plt.title(f"PSD concatenada ({n_psd} archivos, DC spike eliminado)")
    plt.xlabel("Frecuencia [MHz]")
    plt.ylabel("PSD [dBm/Hz]")
    plt.grid(True)
    plt.tight_layout()
    plt.show()

    return freq_concat, psd_concat


# === Ejemplo de uso ===
if __name__ == "__main__":
    base_path = "/home/ogutierreze/GPDS_Proyects/Test_ANE/ANE2_Procesamiento/ANE2_procesamiento/MonRaF-ANE1/Output2"

    # Concatenar las primeras 5 PSD y eliminar el DC spike
    concat_and_plot_psd(base_path, n_psd=2)
