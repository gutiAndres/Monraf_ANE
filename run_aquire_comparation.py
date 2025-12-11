import sys
import os
import time
import subprocess
from pathlib import Path

import numpy as np  # si lo necesitas en otro lado
from psd_welch_hackrf_exec import procesar_archivo_psd

from n9000b_capture import N9000BCapture  # <-- integración N9000B


import os
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt

from test_acquire import acquire_psd

def compare_and_save_psd(
    pwr_n9000: np.ndarray,
    f_psd: np.ndarray,
    freqs_n9000: np.ndarray,
    Pxx_psd: np.ndarray,
    output_path
):
    """
    Compara la PSD del N9000B y la PSD del HackRF:

    - Interpola la PSD del HackRF (Pxx_psd) al eje de freqs del N9000B (freqs_n9000),
      de modo que ambas tengan el mismo tamaño.
    - Guarda un CSV con tres columnas: [Freq_Hz, N9000B_PSD, HackRF_PSD_interp]
    - Guarda un PNG con la comparación de las dos PSD.
    - Usa output_path como carpeta de salida.

    Parámetros
    ----------
    pwr_n9000 : array-like
        PSD medida por el N9000B (en dBm o dBfs, según tu configuración).
    f_psd : array-like
        Eje de frecuencias de la PSD del HackRF (en Hz).
    freqs_n9000 : array-like
        Eje de frecuencias de la PSD del N9000B (en Hz).
    Pxx_psd : array-like
        PSD medida por el HackRF (en dBm o dBfs, misma unidad que pwr_n9000).
    output_path : str o Path
        Directorio donde se guardarán el CSV y la imagen.
    """

    # Asegurar tipos numpy
    pwr_n9000 = np.asarray(pwr_n9000)
    f_psd = np.asarray(f_psd)
    freqs_n9000 = np.asarray(freqs_n9000)
    Pxx_psd = np.asarray(Pxx_psd)

    # Asegurar que la ruta existe
    output_path = Path(output_path)
    output_path.mkdir(parents=True, exist_ok=True)

    # ---- Interpolación: llevar HackRF al eje de frecuencias del N9000B ----
    # np.interp extrapola usando los valores de borde; para comparación rápida es suficiente.
    Pxx_psd_interp = np.interp(freqs_n9000, f_psd, Pxx_psd)

    # ---- Helper para evitar sobreescritura de archivos ----
    def get_unique_path(base: Path, ext: str) -> Path:
        """
        Dado un Path base (sin extensión fija) y una extensión, genera
        un path único evitando sobrescrituras:
        base.ext, base_1.ext, base_2.ext, ...
        """
        candidate = base.with_suffix(ext)
        if not candidate.exists():
            return candidate

        idx = 1
        while True:
            candidate = base.with_name(f"{base.name}_{idx}").with_suffix(ext)
            if not candidate.exists():
                return candidate
            idx += 1

    # Nombre base genérico para comparación
    base_name = output_path / "psd_comparison"

    # ---- Guardar CSV ----
    csv_path = get_unique_path(base_name, ".csv")
    data = np.column_stack((freqs_n9000, pwr_n9000, Pxx_psd_interp))
    np.savetxt(
        csv_path,
        data,
        delimiter=",",
        header="Freq_Hz,N9000B_PSD,HackRF_PSD_interp",
        comments="",
    )
    print(f"💾 CSV comparación PSD guardado: {csv_path}")

    # ---- Guardar plot ----
    img_path = get_unique_path(base_name, ".png")

    plt.figure(figsize=(10, 6))
    plt.plot(freqs_n9000 / 1e6, pwr_n9000, label="N9000B", linewidth=1)
    plt.plot(freqs_n9000 / 1e6, Pxx_psd_interp, label="HackRF (interp)", linewidth=1)
    plt.title("Comparación PSD N9000B vs HackRF")
    plt.xlabel("Frecuencia (MHz)")
    plt.ylabel("PSD (dBm / dBfs)")
    plt.grid(True, linestyle="--", alpha=0.7)
    plt.legend()
    plt.tight_layout()
    plt.savefig(img_path)
    plt.close()

    print(f"🖼️ Imagen comparación PSD guardada: {img_path}")

    # Devuelvo también el vector interpolado por si quieres seguir procesando
    return csv_path, img_path, freqs_n9000, pwr_n9000, Pxx_psd_interp



def main():

    # Modos permitidos
    MODOS_VALIDOS = {
        "dinamic range",
        "power precision",
        "DANL",
        "frequency accuracy",
        None,
    }

    # ======== Parámetros CLI ========
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
    server_url = "http://192.168.0.102:5000/upload_csv"
    #### ------------------------------------ ###

    # Validar test_mode
    if test_mode not in MODOS_VALIDOS:
        raise ValueError(
            f"Modo inválido: '{test_mode}'. "
            f"Modos permitidos: {', '.join(str(m) for m in MODOS_VALIDOS)}"
        )

    #---------------solo si test_mode = None--------------------
    output_path = base_dir / "Output_test_compare2"
    #----------------------------------------------------------

    #------ parámetros fijos para testeo HackRF -------- 
    exe_path = "./test_capture"
    iq_base_path = base_dir / "Samples"
    corrige_impedancia = False
    R_ant = 50
    nperseg = 2048
    overlap = 0.5
    scale = 'dBm'
    samples = 20000000

    if test_mode == "DANL":
        samples = 10000000

    # ======== Vector de frecuencias según el modo de testeo ========
    if test_mode == "DANL":
        output_path = base_dir / "Output_DANL"
        scale = 'dBfs'
        frecuencias = [
            freq
            for freq in range(int(50), int(5950) + 1, int(50))
            for _ in range(int(5))
        ]
    elif test_mode == "dinamic range":
        frecuencias = [
            freq
            for freq in range(int(98), int(118) + 1, int(20))
            for _ in range(int(1))
        ]
        output_path = base_dir / "Output_dinamic_range"
    elif test_mode == "power precision":
        frecuencias = [
            freq
            for freq in range(int(98), int(5898) + 1, int(100))
            for _ in range(int(1))
        ]
        output_path = base_dir / "Output_power_data"
    elif test_mode == "frequency accuracy":
        frecuencias = [
            freq
            for freq in range(int(1000), int(3000) + 1, int(1000))
            for _ in range(int(20))
        ]
        output_path = base_dir / "Output_frequency_error"
    elif test_mode is None:
        frecuencias = [
            freq
            for freq in range(int(f_in), int(f_fin) + 1, int(step))
            for _ in range(int(n_cycles))
        ]

    # Asegurarse que el directorio de salida exista
    output_path.mkdir(parents=True, exist_ok=True)

    update_static = True
    if test_mode == "DANL":
        update_static = False

    #------- Amplitudes para rango dinámico (HackRF) ------------
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

    # ======== Parámetros N9000B ========
    N9000B_ENABLED = True      # desactiva poniéndolo en False si quieres sólo HackRF
    N9000B_IP = '192.168.46.127'
    N9000B_SPAN_HZ = 20e6      # mismo ancho de banda que usas en HackRF
    N9000B_N_AVERAGES = 400    # número de promedios de la traza

    n9000 = None
    if N9000B_ENABLED:
        # Importante: usar el mismo output_path para que guarde en la misma carpeta
        n9000 = N9000BCapture(
            ip=N9000B_IP,
            center_freqs_hz=None,    # no lo usamos aquí, llamamos run_single_capture directamente
            span_hz=N9000B_SPAN_HZ,
            n_averages=N9000B_N_AVERAGES,
            output_dir=str(output_path),
        )
        try:
            n9000.connect()
        except RuntimeError as e:
            print(f"[WARN] No se pudo conectar al N9000B: {e}")
            n9000 = None

    #----- Bucle de adquisición y procesamiento ------
    t_inicio_total = time.perf_counter()

    try:
        for i, freq in enumerate(frecuencias, start=1):
            if dinamic_range:
                ifamp = amp[j]
            else:
                ifamp = 1

            print(f"\n=== [CICLO {i}] Ejecutando captura y procesamiento para {freq} MHz, MODO {test_mode} ===")
            t_inicio_ciclo = time.perf_counter()



            # ------------------ HACKRF ------------------
            print(f"[INFO] Ejecutando captura HackRF: {exe_path} {samples} {freq}")

            # Sobrescribir parámetros si quieres (opcional)
            overrides = {
                "center_freq_hz": freq,   # 93.7 MHz
                "span": 20_000_000,             # 10 MHz
                "lna_gain": 0,
                "vga_gain": 0,
            }

            f_psd, Pxx_psd = acquire_psd(
                cfg_overrides=overrides,
                timeout_s=5.0,
                save_metrics=False,  # o True si quieres CSV
                do_plot=False        # puedes graficar tú mismo
            )



            # Aquí ya tienes los vectores para procesamiento adicional
            print("frequencies (Hz):", f_psd[:5], "...")
            print("PSD (first 5):", Pxx_psd[:5], "...")

            print(f"[OK] Captura HackRF completada para {freq} MHz")

            time.sleep(8)

            # ------------------ N9000B ------------------
            if n9000 is not None:
                print(f"[INFO] Iniciando captura N9000B para {freq} MHz")
                center_freq_hz = float(freq) * 1e6

                freqs_n9000, pwr_n9000 = n9000.run_single_capture(
                    center_freq_hz=center_freq_hz,
                    span_hz=N9000B_SPAN_HZ,
                    n_averages=N9000B_N_AVERAGES,
                )

                # Los CSV/PNG del N9000B se guardan dentro de output_path
                print(f"[OK] Captura N9000B completada para {freq} MHz. "
                      f"Frecs: {len(freqs_n9000)} puntos")
                
            time.sleep(10)

            # Ruta del archivo IQ generado
            iq_path = os.path.join(iq_base_path, str(0))
            print(f"[INFO] Procesando archivo IQ HackRF: {iq_path}")

            # Procesamiento PSD HackRF
            print(f"[OK] PSD HackRF procesada para {freq} MHz. ")
            

            csv_comp, img_comp, f_common, p_n9000, p_hackrf_interp = compare_and_save_psd(
                pwr_n9000=pwr_n9000,
                f_psd=f_psd,
                freqs_n9000=freqs_n9000,
                Pxx_psd=Pxx_psd,
                output_path=output_path,
            )

            # ------------------ Tiempo & espera ------------------
            t_fin_ciclo = time.perf_counter()
            print(f"⏱ Duración ciclo {freq} MHz: {t_fin_ciclo - t_inicio_ciclo:.2f} s")

            print("Esperando para la siguiente ...")
            time.sleep(TIME_SLEEP)

    finally:
        # Cerrar N9000B si está activo
        if n9000 is not None:
            n9000.close()

        t_fin_total = time.perf_counter()
        print(f"\n🏁 Duración total del proceso: {t_fin_total - t_inicio_total:.2f} s")


if __name__ == "__main__":
    main()
