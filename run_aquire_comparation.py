import subprocess
import time
from pathlib import Path
import numpy as np
import csv
import os
import sys

from psd_welch_hackrf_exec import procesar_archivo_psd
from n9000b_capture import N9000BCapture   # Clase del Keysight


# ==============================
# Utilidad para evitar overwrite
# ==============================
def get_unique_path(base_path: str) -> str:
    """
    Evita sobrescritura de archivos.
    Si base_path existe → base_1.ext, base_2.ext, etc.
    """
    if not os.path.exists(base_path):
        return base_path

    root, ext = os.path.splitext(base_path)
    idx = 1
    while True:
        new_path = f"{root}_{idx}{ext}"
        if not os.path.exists(new_path):
            return new_path
        idx += 1


# ==============================
# Configuración general
# ==============================
def main():

    # Modos permitidos
    MODOS_VALIDOS = {
        "dinamic range",
        "power precision",
        "DANL",
        "frequency accuracy",
        None,
    }

    # ---------- Argumentos CLI ----------
    f_in = sys.argv[1]
    f_fin = sys.argv[2]
    step = sys.argv[3]
    n_cycles = sys.argv[4]
    try:
        test_mode = sys.argv[5]
    except IndexError:
        test_mode = None

    # === Ruta automática ===
    base_dir = Path(__file__).resolve().parent

    #### ------------- Parámetros generales ----------- ###
    TIME_SLEEP = 8    # tiempo entre ciclo de adquisición
    server_url = "http://172.20.30.81:5000/upload_csv"
    #### ------------------------------------ ###

    # Validar test_mode
    if test_mode not in MODOS_VALIDOS:
        raise ValueError(
            f"Modo inválido: '{test_mode}'. "
            f"Modos permitidos: {', '.join(str(m) for m in MODOS_VALIDOS)}"
        )

    # Directorio por defecto (luego se ajusta según modo)
    output_path = base_dir / "Output_dinamic_range"

    #------ parámetros fijos para testeo HackRF --------
    exe_path = "./test_capture"
    iq_base_path = base_dir / "Samples"
    corrige_impedancia = False
    R_ant = 50
    nperseg = 2048
    overlap = 0.5
    scale = 'dBm'
    samples = 20_000_000
    fs_hackrf = 20e6

    if test_mode == "DANL":
        samples = 10_000_000

    # ==============================
    #  Parámetros Keysight N9000B
    # ==============================
    N9000B_IP = "192.168.0.110"
    SPAN_HZ = 20e6             # span para el N9000B
    N_AVERAGES = 500

    # Instancia del Keysight
    ks = N9000BCapture(
        ip=N9000B_IP,
        span_hz=SPAN_HZ,
        n_averages=N_AVERAGES,
        output_dir="n9000b_sync_capture",
    )

    try:
        ks.connect()
    except Exception as e:
        print(f"⚠️ No se pudo conectar al Keysight N9000B: {e}")
        print("   Continuando solo con HackRF...\n")
        ks = None

    # Directorio para CSV/PNG de comparación (Keysight vs HackRF)
    compare_output_dir = base_dir / "Output_compare_keysight_hackrf"
    os.makedirs(compare_output_dir, exist_ok=True)

    # ===== Vector de frecuencias según el modo de test =====
    if test_mode == "DANL":
        output_path = base_dir / "Output_DANL"
        scale = 'dBfs'
        frecuencias = [
            freq for freq in range(int(50), int(5950) + 1, int(50))
            for _ in range(int(5))
        ]
    elif test_mode == "dinamic range":
        frecuencias = [
            freq for freq in range(int(98), int(118) + 1, int(20))
            for _ in range(int(1))
        ]
        output_path = base_dir / "Output_dinamic_range"
    elif test_mode == "power precision":
        frecuencias = [
            freq for freq in range(int(98), int(5898) + 1, int(100))
            for _ in range(int(1))
        ]
        output_path = base_dir / "Output_power_data"
    elif test_mode == "frequency accuracy":
        frecuencias = [
            freq for freq in range(int(1000), int(3000) + 1, int(1000))
            for _ in range(int(20))
        ]
        output_path = base_dir / "Output_frequency_error"
    elif test_mode is None:
        frecuencias = [
            freq for freq in range(int(f_in), int(f_fin) + 1, int(step))
            for _ in range(int(n_cycles))
        ]

    update_static = True
    if test_mode == "DANL":
        update_static = False

    #------- Amplitudes para rango dinámico ------------
    if test_mode == "dinamic range":
        dinamic_range = True
    else:
        dinamic_range = False

    amp_init = -60
    amp_fin = -10
    step_amp = 2

    amp = range(int(amp_init), int(amp_fin) + 1, int(step_amp))
    j = 0
    ifamp = amp[j]

    #----- Bucle de adquisición y procesamiento ------
    t_inicio_total = time.perf_counter()

    for i, freq in enumerate(frecuencias, start=1):
        # freq está en MHz
        if dinamic_range:
            ifamp = amp[j]
        else:
            ifamp = 1

        print(f"\n=== [CICLO {i}] Captura sincronizada para {freq} MHz, MODO {test_mode} ===")
        t_inicio_ciclo = time.perf_counter()

        # ==============================
        # 1) Captura HackRF (C + PSD)
        # ==============================
        print(f"[INFO] Ejecutando captura HackRF: {exe_path} {samples} {freq}")
        subprocess.run(
            [
                exe_path,
                str(samples),
                str(freq),  # MHz → tu binario debe convertir a Hz internamente
                str(0),
                str(0),
            ],
            check=True
        )
        print(f"[OK] Captura HackRF completada para {freq} MHz")

        print(f"[INFO] Iniciando captura Keysight en {freq/1e6:.2f} MHz")

        freqs_ks, psd_ks = ks.run_capture(
            center_freq_hz=freq,
            span_hz=SPAN_HZ,
            n_averages=N_AVERAGES,
        )


        # Archivo IQ HackRF
        iq_path = os.path.join(iq_base_path, str(0))  # Ajustar si usas otra convención
        print(f"[INFO] Procesando archivo IQ HackRF: {iq_path}")

        # Procesar PSD HackRF
        f_hackrf, Pxx_hackrf, csv_filename_hackrf = procesar_archivo_psd(
            iq_path=iq_path,
            output_path=output_path,
            fs=fs_hackrf,
            indice=freq,  # si tu función espera MHz como índice
            scale=scale,
            R_ant=R_ant,
            corrige_impedancia=corrige_impedancia,
            nperseg=nperseg,
            overlap=overlap,
            plot=False,
            save_csv=False,
            update_static=update_static,
            Amplitud=ifamp,
            dinamic_range=dinamic_range,
            server_url=server_url
        )

        print(f"[OK] PSD HackRF procesada para {freq} MHz. Archivo: {csv_filename_hackrf}")

        # ==============================
        # 2) Captura Keysight sincronizada
        # ==============================
        if ks is not None:
            # ============================================
            # 3) Interpolación HackRF → eje Keysight
            # ============================================
            # Asegurar que f_hackrf esté ordenado (por si acaso)
            sort_idx = np.argsort(f_hackrf)
            f_hackrf_sorted = f_hackrf[sort_idx]
            Pxx_hackrf_sorted = Pxx_hackrf[sort_idx]

            # Interpolamos la PSD del HackRF al eje de frecuencias del Keysight
            sensor_y_interp = np.interp(
                freqs_ks,
                f_hackrf_sorted,
                Pxx_hackrf_sorted
            )

            # ============================================
            # 4) Guardar CSV combinado: Freq_Hz,N9000B_dBm,Sensor_dBm
            # ============================================
            base_csv_cmp = compare_output_dir / f"compare_{int(fc_hz)}.csv"
            csv_cmp_path = get_unique_path(str(base_csv_cmp))

            data_cmp = np.column_stack((freqs_ks, psd_ks, sensor_y_interp))
            np.savetxt(
                csv_cmp_path,
                data_cmp,
                delimiter=",",
                header="Freq_Hz,N9000B_dBm,Sensor_dBm",
                comments=""
            )
            print(f"💾 CSV comparación guardado: {csv_cmp_path}")

            # ============================================
            # 5) Guardar plot de comparación
            # ============================================
            import matplotlib.pyplot as plt

            base_png_cmp = compare_output_dir / f"plot_compare_{int(fc_hz)}.png"
            png_cmp_path = get_unique_path(str(base_png_cmp))

            plt.figure(figsize=(10, 6))
            plt.plot(freqs_ks, psd_ks, label="N9000B", linewidth=1)
            plt.plot(freqs_ks, sensor_y_interp, label="HackRF (Interpolado)", linewidth=1)
            plt.title(f"Comparación PSD - {fc_hz/1e6:.2f} MHz")
            plt.xlabel("Frecuencia (Hz)")
            plt.ylabel("Amplitud (dBm)")
            plt.grid(True, which="both", linestyle="--", alpha=0.7)
            plt.legend()
            plt.tight_layout()
            plt.savefig(png_cmp_path)
            plt.close()

            print(f"🖼️ PNG comparación guardado: {png_cmp_path}")

        else:
            print("⚠️ Saltando captura Keysight (no conectado).")

        if dinamic_range:
            j += 1

        t_fin_ciclo = time.perf_counter()
        print(f"⏱ Duración ciclo {freq} MHz: {t_fin_ciclo - t_inicio_ciclo:.2f} s")

        print("Esperando para la siguiente ...")
        time.sleep(TIME_SLEEP)

    t_fin_total = time.perf_counter()
    print(f"\n🏁 Duración total del proceso: {t_fin_total - t_inicio_total:.2f} s")

    # Cerrar Keysight
    if ks is not None:
        ks.close()


if __name__ == "__main__":
    main()
