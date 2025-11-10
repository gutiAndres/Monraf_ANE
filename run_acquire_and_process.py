
import subprocess
import time
from pathlib import Path
import numpy as np 
import csv
import os
from psd_welch_hackrf_exec import procesar_archivo_psd
import os, time
import sys


# ==============================
# Configuración general
# ==============================

def main():
    f_in = sys.argv[1]
    f_fin = sys.argv[2]
    step = sys.argv[3]
    exe_path = "./test_capture"
    samples = 20000000
    frecuencias = list(range(int(f_in), int(f_fin) + 1, int(step)))  # MHz 

    # === Ruta automática ===
    # Obtiene el directorio donde está este script Python actual
    base_dir = Path(__file__).resolve().parent

    iq_base_path = base_dir /"Samples"
    output_path = base_dir /"Output_DANL_dbfs2"
    scale = 'dBfs'
    R_ant = 50
    corrige_impedancia = False
    nperseg = 2000
    overlap = 0.5

    print(frecuencias)
    t_inicio_total = time.perf_counter()

    for i, freq in enumerate(frecuencias, start=1):
        print(f"\n=== [CICLO {i}] Ejecutando captura y procesamiento para {freq} MHz ===")
        t_inicio_ciclo = time.perf_counter()

        # --- Ejecutar captura C ---
        print(f"[INFO] Ejecutando captura: {exe_path} {samples} {freq}")
        subprocess.run([exe_path, str(samples), str(freq)], check=True)
        print(f"[OK] Captura completada para {freq} MHz")

        # --- Construir ruta del archivo IQ generado ---
        iq_path = os.path.join(iq_base_path, str(0))  # por ejemplo: Samples/5680
        print(f"[INFO] Procesando archivo IQ: {iq_path}")

        # --- Llamar directamente a la función Python ---
        f, Pxx, csv_filename = procesar_archivo_psd(
            iq_path=iq_path,
            output_path=output_path,
            fs=samples,
            indice=freq,
            scale=scale,
            R_ant=R_ant,
            corrige_impedancia=corrige_impedancia,
            nperseg=nperseg,
            overlap=overlap,
            plot=False
        )

        print(f"[OK] PSD procesada para {freq} MHz. Archivo: {csv_filename}")

        t_fin_ciclo = time.perf_counter()
        print(f"⏱ Duración ciclo {freq} MHz: {t_fin_ciclo - t_inicio_ciclo:.2f} s")

        print("Esperando para la siguiente ...")
        time.sleep(1)

    t_fin_total = time.perf_counter()
    print(f"\n🏁 Duración total del proceso: {t_fin_total - t_inicio_total:.2f} s")

if __name__ == "__main__":
    main()
