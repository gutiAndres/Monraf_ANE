import pyvisa
import numpy as np
import matplotlib.pyplot as plt
import time
import os

# ==========================
# CONFIGURACIÓN BÁSICA N9000B
# ==========================

VISA_TIMEOUT = 10000          # ms
SPAN = 20.0e6                     # Span común (Hz)

# Número de veces que promedias la traza



def get_unique_path(base_path: str) -> str:
    """
    Devuelve una ruta única sin sobreescribir archivos existentes.
    Si base_path existe, genera base_path_1, base_path_2, etc.
    """
    if not os.path.exists(base_path):
        return base_path

    root, ext = os.path.splitext(base_path)
    idx = 1
    new_path = f"{root}_{idx}{ext}"
    while os.path.exists(new_path):
        idx += 1
        new_path = f"{root}_{idx}{ext}"
    return new_path


def connect_n9000b(ip: str, timeout_ms: int):
    """
    Abre conexión VISA con el N9000B y devuelve el handle.
    """
    rm = pyvisa.ResourceManager('@py')
    inst = rm.open_resource(f'TCPIP::{ip}::INSTR')
    inst.timeout = timeout_ms
    inst.write('*CLS')       # Limpia estados
    inst.write(':FORM ASC')  # Respuestas en ASCII
    idn = inst.query('*IDN?').strip()
    print(f"✅ Conectado N9000B: {idn}")
    return inst


def average_with_self(y: np.ndarray, n_times: int = 1) -> np.ndarray:
    """
    Promedia el vector 'y' consigo mismo 'n_times' veces.
    Útil para suavizar o replicar un efecto de averaging sin hacer nuevas adquisiciones.
    """
    if n_times <= 1:
        return y

    acc = np.zeros_like(y, dtype=float)

    for _ in range(n_times):
        acc += y

    return acc / n_times


def acquire_trace_n9000b(inst, center_freq_hz: float, span_hz: float,
                         n_averages: int = 1, sleep_after_config: float = 1.0):
    """
    Configura el N9000B a una frecuencia central y span, y devuelve:

      freqs_hz, y_avg

    donde y_avg es la traza única adquirida, promediada consigo misma n_averages veces.
    """

    # Configurar frecuencia central y span
    inst.write(f':SENSe:FREQuency:CENTer {center_freq_hz}')
    inst.write(f':SENSe:FREQuency:SPAN {span_hz}')

    # Espera para que el barrido se estabilice
    time.sleep(sleep_after_config)

    # Lee datos de la traza 1 (una sola adquisición real)
    y_k = np.array(inst.query_ascii_values(':TRACe:DATA? TRACE1'))

    # Promediar consigo misma n_averages veces
    y_avg = average_with_self(y=y_k, n_times=n_averages)

    # Construir eje de frecuencia lineal entre start y end del span
    n_points = len(y_k)
    start_f = center_freq_hz - span_hz / 2
    end_f = center_freq_hz + span_hz / 2
    freqs_hz = np.linspace(start_f, end_f, n_points)

    return freqs_hz, y_avg


def extract_trace_keisight(
    OUTPUT_DIR: str = "n900_traces1",
    center_freq_hz: float = 78e6,
    N9000B_IP: str = '192.168.0.110',
    n_averages: int = 100
):
    """
    Adquiere UNA sola traza del N9000B para una frecuencia central dada,
    la guarda en CSV y PNG, y devuelve (y_avg, freqs_hz).
    """

    inst = None
    y_avg = None
    freqs_hz = None

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    try:
        # 1) Conectar al N9000B
        inst = connect_n9000b(N9000B_IP, VISA_TIMEOUT)

        print(f"\n--- Captura para fc = {center_freq_hz/1e6:.2f} MHz ---")

        # 2) Adquirir UNA traza
        freqs_hz, y_avg = acquire_trace_n9000b(
            inst=inst,
            center_freq_hz=center_freq_hz,
            span_hz=SPAN,
            n_averages=n_averages,
            sleep_after_config=1.0
        )

        # 3) Guardar CSV
        base_csv = os.path.join(OUTPUT_DIR, f'n9000_trace_{int(center_freq_hz)}.csv')
        csv_name = get_unique_path(base_csv)

        data_stack = np.column_stack((freqs_hz, y_avg))
        np.savetxt(
            csv_name,
            data_stack,
            delimiter=',',
            header='Freq_Hz,Amplitude_dB',
            comments=''
        )
        print(f"💾 CSV guardado: {csv_name}")

        # 4) Guardar PNG
        base_png = os.path.join(OUTPUT_DIR, f'n9000_trace_{int(center_freq_hz)}.png')
        png_name = get_unique_path(base_png)

        plt.figure(figsize=(10, 5))
        plt.plot(freqs_hz, y_avg, linewidth=1)
        plt.title(f"N9000B - Trace promedio, fc={center_freq_hz/1e6:.2f} MHz")
        plt.xlabel("Frecuencia (Hz)")
        plt.ylabel("Amplitud (dB / dBm)")
        plt.grid(True, linestyle='--', alpha=0.7)
        plt.tight_layout()
        plt.savefig(png_name)
        plt.close()
        print(f"🖼️ PNG guardado: {png_name}")

        print("\n✅ Proceso de adquisición completado.")

    except KeyboardInterrupt:
        print("\n🚨 Interrupción de teclado. Saliendo...")

    except Exception as e:
        print(f"\n❌ Error durante la adquisición: {e}")

    finally:
        if inst is not None:
            print("🔌 Cerrando conexión PyVISA con N9000B...")
            try:
                inst.close()
                print("✅ Conexión cerrada.")
            except Exception as e_close:
                print(f"⚠️ Error al cerrar el instrumento: {e_close}")

    if y_avg is not None and freqs_hz is not None:
        print(f"Tamaño de vector de potencias: {len(y_avg)} y frecuencias {len(freqs_hz)}")

    return y_avg, freqs_hz


#if __name__ == '__main__':
#   pxx,f = extract_trace_keisight(OUTPUT_DIR="n9000_traces",center_freq_hz = 98e6, N9000B_IP = '192.168.0.110', n_averages=100)
   

