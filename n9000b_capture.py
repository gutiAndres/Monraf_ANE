import pyvisa
import numpy as np
import matplotlib.pyplot as plt
import time
import os
from typing import List, Tuple, Dict, Any, Optional

class N9000BCapture:
    """
    Clase para manejar la adquisición de espectros con un Keysight N9000B
    a través de PyVISA. Modificada para enfocarse en la adquisición de un único
    espectro promediado.
    """

    def __init__(
        self,
        ip: str ='192.168.46.127',
        center_freqs_hz: Optional[List[float]] = None,
        span_hz: float = 20e6,
        n_averages: int = 500, # Valor por defecto, puede ser sobrescrito en run_batch_capture
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
            # Ahora solo importa la primera frecuencia para la captura única.
            self.center_freqs_hz = [103e6] # Frecuencia única por defecto (e.g., 103 MHz)
        else:
            self.center_freqs_hz = [float(f) for f in center_freqs_hz]

        self.span_hz = float(span_hz)
        self.n_averages = int(n_averages)
        self.wait_time_s = float(wait_time_s)

        # ---- Salidas ----
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

        # ---- Handles VISA ----
        self.rm: Optional[pyvisa.ResourceManager] = None
        self.inst: Optional[pyvisa.resources.MessageBasedResource] = None

    # ==========================================================
    # ------------------- MANEJO DE ARCHIVOS -------------------
    # ==========================================================
    @staticmethod
    def get_unique_path(base_path: str) -> str:
        """Evita sobrescritura de archivos."""
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
        """Conecta al N9000B vía PyVISA."""
        try:
            self.rm = pyvisa.ResourceManager(self.visa_backend)
            # La dirección es típicamente TCPIP::IP::INSTR para el N9000B
            self.inst = self.rm.open_resource(f"TCPIP::{self.ip}::INSTR")
            self.inst.timeout = self.visa_timeout
            
            # Limpiar y configurar formato de datos
            self.inst.write("*CLS")
            self.inst.write(":FORM ASC")

            idn = self.inst.query("*IDN?").strip()
            print(f"✅ Conectado a N9000B: {idn}")

        except Exception as e:
            raise RuntimeError(f"❌ Error conectando al N9000B ({self.ip}): {e}")

    def configure_frequency(self, center_freq_hz: float, span_hz: float):
        """Configura frecuencia central y span en el analizador."""
        if self.inst is None:
            raise ConnectionError("El instrumento no está conectado. Llame a 'connect()' primero.")
            
        self.inst.write(f":SENSe:FREQuency:CENTer {center_freq_hz}")
        self.inst.write(f":SENSe:FREQuency:SPAN {span_hz}")
        # Esperar un momento para que el barrido se estabilice
        time.sleep(self.wait_time_s) 

    # ==========================================================
    # ---------------------- ADQUISICIÓN ------------------------
    # ==========================================================
    def acquire_average_trace(self, n_averages: int) -> np.ndarray:
        """
        Obtiene un trazo promediado con n_averages repeticiones.
        """
        if self.inst is None:
            raise ConnectionError("El instrumento no está conectado.")
            
        accumulator = None

        # Nota: La implementación por software (`query_ascii_values` en loop) es robusta.
        
        for i in range(n_averages):
            # Adquirir los valores de amplitud del Trazo 1
            trace = np.array(self.inst.query_ascii_values(":TRACe:DATA? TRACE1"))

            if accumulator is None:
                accumulator = trace.copy()
            else:
                accumulator += trace

        return accumulator / n_averages

    # ==========================================================
    # ------------------------ GUARDADOS ------------------------
    # ==========================================================
    def _save_data(self, freqs_hz: np.ndarray, powers_dbm: np.ndarray, center_freq_hz: float):
        """Guarda CSV y PNG para una sola adquisición."""
        
        # 1. Guardar CSV
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

        # 2. Guardar PNG
        base_png = os.path.join(
            self.output_dir,
            f"n9000b_plot_{int(center_freq_hz)}.png"
        )
        png_path = self.get_unique_path(base_png)

        plt.figure(figsize=(10, 6))
        plt.plot(freqs_hz / 1e6, powers_dbm, label="N9000B", linewidth=1)
        plt.title(f"N9000B - Espectro Promediado (Centro: {center_freq_hz / 1e6:.2f} MHz)")
        plt.xlabel("Frecuencia (MHz)") # Usar MHz en el plot para mejor legibilidad
        plt.ylabel("Amplitud (dBm)")
        plt.grid(True, linestyle="--", alpha=0.7)
        plt.legend()
        plt.tight_layout()
        plt.savefig(png_path)
        plt.close()

        print(f"🖼️ PNG guardado: {png_path}")
        return csv_path, png_path

    # ==========================================================
    # ------------------------- FLUJO ---------------------------
    # ==========================================================
    def run_single_capture(
            self,
            center_freq_hz: float,
            span_hz: float,
            n_averages: int,
        ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Ejecuta UNA sola adquisición completa (configurar, capturar, guardar).
        """
        fc = float(center_freq_hz)
        span_hz = float(span_hz)

        print(f"\n--- Captura Única {fc / 1e6:.2f} MHz (Span: {span_hz / 1e6:.2f} MHz, Promedios: {n_averages}) ---")

        # 1) Configurar analizador
        self.configure_frequency(fc, span_hz)

        # 2) Captura promediada
        avg_trace = self.acquire_average_trace(n_averages=n_averages)

        # 3) Eje de frecuencias asociado
        f_start = fc - span_hz / 2
        f_end = fc + span_hz / 2
        # El N9000B usualmente devuelve 401, 801, 1601, etc. puntos.
        freqs_hz = np.linspace(f_start, f_end, len(avg_trace))

        # 4) Guardar resultados en disco
        self._save_data(freqs_hz, avg_trace, fc)

        # Devolvemos los datos
        return freqs_hz, avg_trace

    def run_batch_capture(self, n_averages: int):
        """
        Ejecuta una adquisición única, utilizando la primera frecuencia central
        definida y el número de promedios proporcionado.
        
        El parámetro n_averages ahora es el número entero que se pasa al método.
        """
        
        center_freq = self.center_freqs_hz[0] # Tomar solo la primera frecuencia
        
        print("🚀 Iniciando Captura Única Propinada en N9000B.")
        print(f"Frecuencia Central: {center_freq / 1e6:.2f} MHz")
        print(f"Número de Promedios Solicitados: {n_averages}")
        
        results: Dict[str, Any] = {}

        try:
            # Conectar una sola vez
            self.connect()

            # Ejecutar la adquisición única y obtener los datos
            freqs, powers = self.run_single_capture(
                center_freq_hz=center_freq,
                span_hz=self.span_hz,
                n_averages=n_averages # Usar el valor entero pasado como argumento
            )
                
            results = {
                "center_freq_hz": center_freq,
                "span_hz": self.span_hz,
                "n_averages": n_averages,
                "freqs": freqs,
                "powers": powers
            }

            print("\n🏁 Proceso de captura única completado exitosamente.")
            # Devuelve un diccionario (un resultado único) en lugar de una lista de diccionarios
            return results

        except RuntimeError as e:
            print(f"\n❌ Error fatal durante la ejecución: {e}")
            return None
            
        finally:
            self.close()


    # ==========================================================
    # ------------------------- LIMPIEZA ------------------------
    # ==========================================================
    def close(self):
        """Cierra la conexión VISA."""
        if self.inst:
            print("🔌 Cerrando conexión VISA...")
            try:
                self.inst.close()
                self.inst = None
                print("✅ Conexión VISA cerrada.")
            except Exception as e:
                print(f"⚠️ Error al cerrar VISA: {e}")


# =====================================================================
# ---------------------------- EJEMPLO USO -----------------------------
# =====================================================================

if __name__ == "__main__":
    
    # 1. Inicializar la clase con la configuración deseada
    # Nota: center_freqs_hz ahora toma solo el primer valor de la lista.
    captura_n9000b = N9000BCapture(
        ip="192.168.46.127",
        center_freqs_hz=[freq for freq in range(int(98), int(118)+1, int(20)) for _ in range(int(10))], # Solo se usará 95.1 MHz
        span_hz=5e6,
        n_averages=10, # Este valor es ignorado si se pasa un n_averages a run_batch_capture
        output_dir="n9000b_captura_unica_test11",
    )

    # El entero que pides: 200, que es el número de promedios (n_averages)
    NUM_PROMEDIOS_A_USAR = 500
    
    # 2. Ejecutar el flujo de captura única (llamada anteriormente 'batch')
    data_result = captura_n9000b.run_batch_capture(NUM_PROMEDIOS_A_USAR)

    if data_result:
        print(f"\nEspectro capturado en {data_result['center_freq_hz'] / 1e6:.2f} MHz.")
        print(f"Dimensiones de los datos de potencia: {data_result['powers'].shape}")
        # Aquí se podría continuar con el procesamiento del espectro único
