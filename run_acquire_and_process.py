
import subprocess
import time
from pathlib import Path
import numpy as np 
import csv
import os

# ==============================
# Configuración general
# ==============================

def main():
    exe_path = "./test_capture"
    python_cmd = "python"  # usa tu intérprete normal
    script_python = Path("/home/ogutierreze/GPDS_Proyects/Test_ANE/ANE2_Procesamiento/ANE2_procesamiento/MonRaF-ANE1/psd_welch_hackrf_exec.py")

    samples = 20000000
    frecuencias = list(range(5680, 5981, 20)) # MHz  
    print(frecuencias)
    

    t_inicio_total = time.perf_counter()

    for i, freq in enumerate(frecuencias, start=1):
        print(f"\n=== [CICLO {i}] Ejecutando captura y procesamiento para {freq} MHz ===")
        t_inicio_ciclo = time.perf_counter()

        # --- Ejecutar captura C ---
        print(f"[INFO] Ejecutando captura: {exe_path} {samples} {freq}")
        subprocess.run([exe_path, str(samples), str(freq)], check=True)
        print(f"[OK] Captura completada para {freq} MHz")

        # --- Ejecutar script Python ---
        print(f"[INFO] Ejecutando PSD con índice {i}")
        subprocess.run([python_cmd, str(script_python), "--fs", str(samples), "--indice", str(freq)], check=True)
        print(f"[OK] PSD procesada para {freq} MHz")

        t_fin_ciclo = time.perf_counter()
        print(f"⏱ Duración ciclo {freq} MHz: {t_fin_ciclo - t_inicio_ciclo:.2f} s")

        print("Esperando para la siguiente ...")

        time.sleep(1)

    t_fin_total = time.perf_counter()
    print(f"\n🏁 Duración total del proceso: {t_fin_total - t_inicio_total:.2f} s")



if __name__=="__main__":
    main()