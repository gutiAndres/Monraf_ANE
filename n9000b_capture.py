import pyvisa
import numpy as np
import matplotlib.pyplot as plt
import time
import os


class N9000BCapture:
    """
    Clase para manejar la adquisición de espectros con un Keysight N9000B.

    Parámetros configurables principales (atributos de instancia):

    - ip:              IP del N9000B (str)
    - center_freqs_hz: lista o array de frecuencias centrales en Hz
    - span_hz:         span de frecuencia en Hz (float)
    - n_averages:      número de promedios por traza (int)
    - wait_time_s:     tiempo de espera tras configurar frecuencia/span (float, s)
    - output_dir:      carpeta donde se guardan CSV/PNG (str)
    - visa_timeout:    timeout VISA en ms (int)
    - visa_backend:    backend VISA, por defecto '@py' (str)
    """

    def __init__(
        self,
        ip: str ='192.168.0.110',
        center_freqs_hz=None,
        span_hz: float = 20e6,
        n_averages: int = 500,
        wait_time_s: float = 0.8,
        output_dir: str = "n9000b_only",
        visa_timeout: int = 10_000,
        visa_backend: str = "@py",
    ):
        # ---- Parámetros de instrumento / conexión ----
        self.ip = ip
        self.visa_timeout = visa_timeout
        self.visa_backend = visa_backend

        # ---- Parámetros de adquisición ----
        if center_freqs_hz is None:
            # Por defecto: 40, 50, 60 MHz (3 capturas por cada uno)
            self.center_freqs_hz = np.repeat(
                np.arange(40e6, 61e6 + 1, 10e6), 3
            )
        else:
            self.center_freqs_hz = np.array(center_freqs_hz, dtype=float)

        self.span_hz = float(span_hz)
        self.n_averages = int(n_averages)
        self.wait_time_s = float(wait_time_s)

        # ---- Salidas ----
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

        # ---- Handles VISA ----
        self.rm = None
        self.inst = None

    # ==========================================================
    # ------------------- MANEJO DE ARCHIVOS -------------------
    # ==========================================================
    @staticmethod
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

    # ==========================================================
    # ---------------- CONEXIÓN Y CONFIGURACIÓN ----------------
    # ==========================================================
    def connect(self):
        """Conecta al N9000B vía PyVISA usando los parámetros de la instancia."""
        try:
            self.rm = pyvisa.ResourceManager(self.visa_backend)
            self.inst = self.rm.open_resource(f"TCPIP::{self.ip}::INSTR")
            self.inst.timeout = self.visa_timeout
            self.inst.write("*CLS")
            self.inst.write(":FORM ASC")

            idn = self.inst.query("*IDN?").strip()
            print(f"✅ Conectado a N9000B: {idn}")

        except Exception as e:
            raise RuntimeError(f"❌ Error conectando al N9000B: {e}")

    def configure_frequency(self, center_freq_hz: float, span_hz: float):
        """Configura frecuencia central y span en el analizador."""
        center_freq_hz *= 10e6
        self.inst.write(f":SENSe:FREQuency:CENTer {center_freq_hz}")
        self.inst.write(f":SENSe:FREQuency:SPAN {span_hz}")
        time.sleep(self.wait_time_s)

    # ==========================================================
    # ---------------------- ADQUISICIÓN ------------------------
    # ==========================================================
    def acquire_average_trace(self, n_averages: int = None) -> np.ndarray:
        """
        Obtiene un trazo promediado con n_averages repeticiones.
        Si n_averages es None, se usa self.n_averages.
        """
        if n_averages is None:
            n_averages = self.n_averages

        accumulator = None

        for i in range(n_averages):
            trace = np.array(self.inst.query_ascii_values(":TRACe:DATA? TRACE1"))

            if accumulator is None:
                accumulator = trace.copy()
            else:
                accumulator += trace

        return accumulator / n_averages

    # ==========================================================
    # ------------------------ GUARDADOS ------------------------
    # ==========================================================
    def save_csv(self, freqs_hz: np.ndarray, powers_dbm: np.ndarray, center_freq_hz: float):
        """Guarda CSV con frecuencia y amplitud."""
        base_name = os.path.join(
            self.output_dir,
            f"n9000b_{int(center_freq_hz)}.csv"
        )
        csv_path = self.get_unique_path(base_name)

        data = np.column_stack((freqs_hz, powers_dbm))
        np.savetxt(
            csv_path,
            data,
            delimiter=",",
            header="Freq_Hz,N9000B_dBm",
            comments=""
        )

        print(f"💾 CSV guardado: {csv_path}")
        return csv_path

    def save_plot(self, freqs_hz: np.ndarray, powers_dbm: np.ndarray, center_freq_hz: float):
        """Guarda PNG con el espectro medido."""
        base_png = os.path.join(
            self.output_dir,
            f"n9000b_plot_{int(center_freq_hz)}.png"
        )
        png_path = self.get_unique_path(base_png)

        plt.figure(figsize=(10, 6))
        plt.plot(freqs_hz, powers_dbm, label="N9000B", linewidth=1)
        plt.title(f"N9000B - Espectro Promediado ({center_freq_hz / 1e6:.2f} MHz)")
        plt.xlabel("Frecuencia (Hz)")
        plt.ylabel("Amplitud (dBm)")
        plt.grid(True, linestyle="--", alpha=0.7)
        plt.legend()
        plt.tight_layout()
        plt.savefig(png_path)
        plt.close()

        print(f"🖼️ PNG guardado: {png_path}")
        return png_path

    # ==========================================================
    # ------------------------- FLUJO ---------------------------
    # ==========================================================
    def run_capture(
            self,
            center_freq_hz: float = None,
            span_hz: float = None,
            n_averages: int = None,
        ):
        """
        Ejecuta UNA sola adquisición en una frecuencia central.

        - center_freq_hz: frecuencia central en Hz. Si es None, se toma de la instancia.
        - span_hz: span en Hz. Si es None, se usa self.span_hz.
        - n_averages: número de promedios. Si es None, se usa self.n_averages.

        Devuelve:
            freqs_hz, avg_trace  (ambos np.ndarray)
        """

        # 1) Resolver parámetros por defecto
        if center_freq_hz is None:
            # aquí puedes decidir de dónde sacar la frecuencia por defecto:
            # opción A: primer elemento de self.center_freqs_hz
            center_freq_hz = float(self.center_freqs_hz[0])
            # opción B (si prefieres un atributo escalar): center_freq_hz = self.center_freq_hz

        if span_hz is None:
            span_hz = self.span_hz

        if n_averages is None:
            n_averages = self.n_averages

        fc = float(center_freq_hz)
        span_hz = float(span_hz)

        print("📡 Iniciando adquisición N9000B (modo frecuencia única)...\n")
        print(f"--- Captura Keysight: {fc / 1e6:.2f} MHz ---")

        # 2) Configurar analizador
        self.configure_frequency(fc, span_hz)

        # 3) Captura promediada
        avg_trace = self.acquire_average_trace(n_averages=n_averages)

        # 4) Eje de frecuencias asociado
        f_start = fc - span_hz / 2
        f_end = fc + span_hz / 2
        freqs_hz = np.linspace(f_start, f_end, len(avg_trace))

        # 5) Guardar resultados en disco
        self.save_csv(freqs_hz, avg_trace, fc)
        self.save_plot(freqs_hz, avg_trace, fc)

        print("\n🏁 Proceso de captura completado.")

        # Muy útil para sincronizar con HackRF: devolvemos los datos
        return freqs_hz, avg_trace


    # ==========================================================
    # ------------------------- LIMPIEZA ------------------------
    # ==========================================================
    def close(self):
        """Cierra la conexión VISA."""
        if self.inst:
            print("🔌 Cerrando conexión VISA...")
            try:
                self.inst.close()
                print("✅ Conexión VISA cerrada.")
            except Exception as e:
                print(f"⚠️ Error al cerrar VISA: {e}")


# =====================================================================
# ---------------------------- EJEMPLO USO -----------------------------
# =====================================================================
"""
if __name__ == "__main__":
    # Ejemplo 1: usar parámetros por defecto
    capt = N9000BCapture(
        ip="192.168.0.110",
        # center_freqs_hz=None → usa [40, 40, 40, 50, 50, 50, 60, 60, 60] MHz
        span_hz=20e6,
        n_averages=500,
        output_dir="n9000b_capturas",
    )

    try:
        capt.connect()
        capt.run_capture()  # usa los parámetros de la instancia

        # Ejemplo 2: en la misma instancia, hacer otra corrida con otros params:
        # nuevas_fcs = [100e6, 150e6]
        # capt.run_capture(center_freqs_hz=nuevas_fcs, span_hz=10e6, n_averages=200)

    finally:
        capt.close()
"""