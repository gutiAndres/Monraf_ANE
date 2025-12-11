import cfg
import os
import csv
import json
import time
import asyncio
from datetime import datetime

import numpy as np
import matplotlib.pyplot as plt

from utils import ZmqPub, ZmqSub, RequestClient  # RequestClient se mantiene por compatibilidad

log = cfg.set_logger()

topic_data = "data"
topic_sub = "acquire"

# --- LOCAL ACQUISITION PARAMETERS ---
LOCAL_ACQUISITION_CFG = {
    "center_freq_hz": 98000000,
    "rbw_hz": 10000,
    "overlap": 0.5,
    "window": 1,
    "sample_rate_hz": 20000000.0,
    "span": 20000000,       # 20 MHz
    "lna_gain": 0,
    "vga_gain": 0,
    "antenna_amp": 1,
    "port": None,
}
# ------------------------------------


# --- METRICS MANAGER ---------------------------------------------------------
class MetricsManager:
    def __init__(self, mac):
        self.mac = mac
        self.folder = "CSV_metrics_service"
        self.max_files = 100
        self.ensure_folder()

    def ensure_folder(self):
        if not os.path.exists(self.folder):
            os.makedirs(self.folder)

    def get_size_metrics(self, data_dict, prefix=""):
        """Calculates payload size in various units based on JSON string length."""
        try:
            json_str = json.dumps(data_dict)
            size_bytes = len(json_str.encode('utf-8'))
        except Exception:
            size_bytes = 0

        return {
            f"{prefix}_bytes": size_bytes,
            f"{prefix}_Kb": round((size_bytes * 8) / 1000, 4),       # Kilobits
            f"{prefix}_KB": round(size_bytes / 1024, 4),             # Kilobytes
            f"{prefix}_Mb": round((size_bytes * 8) / 1000000, 6),    # Megabits
            f"{prefix}_MB": round(size_bytes / (1024 * 1024), 6),    # Megabytes
        }

    def rotate_files(self):
        files = [
            os.path.join(self.folder, f)
            for f in os.listdir(self.folder)
            if f.endswith(".csv")
        ]
        if len(files) >= self.max_files:
            files.sort(key=os.path.getctime)
            while len(files) >= self.max_files:
                try:
                    os.remove(files[0])
                    files.pop(0)
                except OSError as e:
                    log.error(f"Error rotating CSV files: {e}")

    def save_metrics(self, server_params, sent_params, metrics):
        self.rotate_files()
        human_time = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"{human_time}_{self.mac}.csv"
        filepath = os.path.join(self.folder, filename)

        row_data = {
            "timestamp_ms": cfg.get_time_ms(),
            "mac_address": self.mac,
        }
        row_data.update(metrics)

        # Prefijo cfg_ para parámetros de configuración enviados al motor
        for k, v in server_params.items():
            row_data[f"cfg_{k}"] = v

        # Prefijo sent_ para lo que “sale” (Pxx no se guarda por tamaño)
        for k, v in sent_params.items():
            if k != "Pxx":
                row_data[f"sent_{k}"] = v

        try:
            with open(filepath, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=row_data.keys())
                writer.writeheader()
                writer.writerow(row_data)
            log.info(f"Metrics saved to {filepath}")
        except Exception as e:
            log.error(f"Failed to save CSV: {e}")
# -----------------------------------------------------------------------------


def fetch_data(payload):
    """
    Normaliza el payload recibido del motor C.
    Espera al menos:
        - Pxx
        - start_freq_hz
        - end_freq_hz
    """
    Pxx = payload.get("Pxx", [])
    start_freq_hz = payload.get("start_freq_hz")
    end_freq_hz = payload.get("end_freq_hz")

    if start_freq_hz is not None and end_freq_hz is not None:
        center_freq_hz = (float(start_freq_hz) + float(end_freq_hz)) / 2.0
    else:
        center_freq_hz = LOCAL_ACQUISITION_CFG.get("center_freq_hz")

    timestamp_iso = datetime.utcnow().isoformat(timespec="milliseconds")

    return {
        "start_freq_hz": start_freq_hz,
        "end_freq_hz": end_freq_hz,
        "center_freq_hz": center_freq_hz,
        "timestamp": timestamp_iso,
        "Pxx": Pxx,
    }


def plot_psd(data_dict, config):
    """Grafica la PSD a partir del diccionario recibido."""
    pxx = np.array(data_dict.get("Pxx", []), dtype=float)
    start_freq = data_dict.get("start_freq_hz")
    end_freq = data_dict.get("end_freq_hz")
    center_freq = data_dict.get("center_freq_hz", config.get("center_freq_hz"))
    if center_freq is None:
        center_freq = 0.0

    if len(pxx) == 0 or start_freq is None or end_freq is None:
        log.error("Cannot plot: Pxx array is empty or frequency bounds are missing.")
        return

    bin_count = len(pxx)
    freqs = np.linspace(float(start_freq), float(end_freq), bin_count)
    scale = config.get("scale", "dB")  # etiqueta

    plt.figure(figsize=(12, 6))
    plt.plot(freqs / 1e6, pxx)

    plt.title(f"Power Spectral Density (PSD) at {center_freq / 1e6:.2f} MHz")
    plt.xlabel("Frequency (MHz)")
    plt.ylabel(f"Power ({scale})")
    plt.grid(True, alpha=0.5)
    plt.minorticks_on()
    plt.grid(which='minor', linestyle=':', alpha=0.3)
    plt.tight_layout()
    plt.show()


# === FUNCIÓN REUTILIZABLE PRINCIPAL =========================================
async def acquire_psd_once(
    cfg_overrides: dict | None = None,
    timeout_s: float = 5.0,
    save_metrics: bool = True,
    do_plot: bool = False,
):
    """
    Realiza UNA adquisición vía ZMQ y devuelve:

        freqs_hz : np.ndarray  -> eje de frecuencias en Hz
        pxx      : np.ndarray  -> PSD asociada a freqs_hz
        data_dict: dict        -> payload final utilizado (incluye Pxx, start/end/center_freq_hz, timestamp)
        metrics  : dict        -> snapshot de métricas calculadas

    Parámetros
    ----------
    cfg_overrides : dict | None
        Diccionario con campos para sobreescribir LOCAL_ACQUISITION_CFG.
        Ej: {"center_freq_hz": 937e6, "span": 10e6}
    timeout_s : float
        Tiempo máximo de espera por la respuesta del motor C.
    save_metrics : bool
        Si True, guarda un CSV con las métricas.
    do_plot : bool
        Si True, llama a plot_psd() al final.

    Lanza asyncio.TimeoutError si no llega respuesta en 'timeout_s'.
    Lanza otras excepciones si hay errores de ZMQ u otros.
    """
    # 1) Construir configuración efectiva
    cfg_to_use = dict(LOCAL_ACQUISITION_CFG)
    if cfg_overrides:
        cfg_to_use.update(cfg_overrides)

    metrics_mgr = MetricsManager(cfg.get_mac())
    pub = ZmqPub(addr=cfg.IPC_CMD_ADDR)
    sub = ZmqSub(addr=cfg.IPC_DATA_ADDR, topic=topic_data)

    # No hay fetch a API, así que lo fijamos a 0
    fetch_time_ms = 0.0

    try:
        await asyncio.sleep(0.5)  # tiempo para establecer sockets ZMQ

        desired_span = int(cfg_to_use.get("span", 0))
        if desired_span <= 0:
            raise ValueError(f"Span inválido en config ({desired_span}).")

        log.info("---- EFFECTIVE LOCAL PARAMS ----")
        for key, val in cfg_to_use.items():
            log.info(f"{key:<18}: {val}")
        log.info("--------------------------------")

        # 2) Enviar comando al motor C
        t_before_zmq = time.perf_counter()
        pub.public_client(topic_sub, cfg_to_use)
        t_after_zmq = time.perf_counter()
        log.info(f"Command sent. Waiting for PSD data ({timeout_s:.1f}s Timeout)...")

        # 3) Esperar por la respuesta en el tópico 'data'
        raw_data = await asyncio.wait_for(sub.wait_msg(), timeout=timeout_s)
        t_zmq_response = time.perf_counter()

        # 4) Normalizar payload
        data_dict = fetch_data(raw_data)

        # 5) Lógica de recorte de span (si el motor devuelve más ancho que 'desired_span')
        raw_pxx = data_dict.get("Pxx")
        if raw_pxx and len(raw_pxx) > 0:
            current_start = float(data_dict.get("start_freq_hz"))
            current_end = float(data_dict.get("end_freq_hz"))
            current_bw = current_end - current_start
            len_Pxx = len(raw_pxx)

            if current_bw > 0 and desired_span < current_bw:
                center_freq = current_start + (current_bw / 2.0)
                ratio = desired_span / current_bw
                bins_to_keep = int(len_Pxx * ratio)
                bins_to_keep = max(1, min(bins_to_keep, len_Pxx))
                start_idx = int((len_Pxx - bins_to_keep) // 2)
                end_idx = start_idx + bins_to_keep

                data_dict["Pxx"] = raw_pxx[start_idx:end_idx]
                data_dict["start_freq_hz"] = center_freq - (desired_span / 2.0)
                data_dict["end_freq_hz"] = center_freq + (desired_span / 2.0)
                data_dict["center_freq_hz"] = center_freq

                log.info(f"Chopped Pxx: {len_Pxx} -> {len(data_dict['Pxx'])} bins")

        # 6) Construir vectores freqs y pxx finales
        final_pxx_list = data_dict.get("Pxx", [])
        if not final_pxx_list:
            raise RuntimeError("Motor C devolvió Pxx vacío o None.")

        final_start = float(data_dict["start_freq_hz"])
        final_end = float(data_dict["end_freq_hz"])
        N = len(final_pxx_list)

        freqs_hz = np.linspace(final_start, final_end, N)
        pxx = np.array(final_pxx_list, dtype=float)

        # 7) Métricas
        config_size_metrics = metrics_mgr.get_size_metrics(cfg_to_use, prefix="server_pkg")
        outgoing_size_metrics = metrics_mgr.get_size_metrics(data_dict, prefix="outgoing_pkg")

        zmq_send_duration_ms = (t_after_zmq - t_before_zmq) * 1000.0
        c_engine_response_ms = (t_zmq_response - t_after_zmq) * 1000.0

        metrics_snapshot = {
            "fetch_duration_ms": round(fetch_time_ms, 2),
            "zmq_send_duration_ms": round(zmq_send_duration_ms, 2),
            "c_engine_response_ms": round(c_engine_response_ms, 2),
            "upload_duration_ms": 0.0,  # no hay upload a API aquí
            "pxx_len": int(N),
            "pxx_type": type(final_pxx_list).__name__,
        }
        metrics_snapshot.update(config_size_metrics)
        metrics_snapshot.update(outgoing_size_metrics)

        # 8) Guardar métricas si corresponde
        if save_metrics:
            metrics_mgr.save_metrics(cfg_to_use, data_dict, metrics_snapshot)

        # 9) Graficar si corresponde
        if do_plot:
            plot_psd(data_dict, cfg_to_use)

        # 10) Devolver resultados útiles para otros scripts
        return freqs_hz, pxx, data_dict, metrics_snapshot

    except asyncio.TimeoutError:
        log.warning("TIMEOUT: No data received from C engine. Check ZMQ addresses and C program status.")
        raise
    except Exception as e:
        log.error(f"Unexpected error during acquisition: {e}")
        raise
    finally:
        # 11) Cerrar sockets
        log.info("Acquisition complete. Closing ZMQ sockets.")
        try:
            pub.close()
        except Exception:
            pass
        try:
            sub.close()
        except Exception:
            pass
# ============================================================================


# === WRAPPER SÍNCRONO PARA USAR DESDE OTROS SCRIPTS =========================
def acquire_psd(
    cfg_overrides: dict | None = None,
    timeout_s: float = 5.0,
    save_metrics: bool = True,
    do_plot: bool = False,
):
    """
    Versión bloqueante (no-async) de acquire_psd_once, pensada para
    llamar directamente desde otros scripts Python:

        freqs_hz, pxx = acquire_psd(...)

    Devuelve:
        freqs_hz : np.ndarray
        pxx      : np.ndarray

    Si necesitas también data_dict y metrics_snapshot, puedes adaptar
    esta función o llamar directamente a acquire_psd_once desde un
    contexto async.
    """
    freqs_hz, pxx, _, _ = asyncio.run(
        acquire_psd_once(
            cfg_overrides=cfg_overrides,
            timeout_s=timeout_s,
            save_metrics=save_metrics,
            do_plot=do_plot,
        )
    )
    return freqs_hz, pxx
# ============================================================================


# === MODO STANDALONE (SI SE EJECUTA DIRECTAMENTE ESTE SCRIPT) ==============
async def acquire_single_shot():
    """
    Se mantiene por compatibilidad: hace una adquisición, grafica y sale.
    Internamente usa acquire_psd_once().
    """
    await acquire_psd_once(cfg_overrides=None, timeout_s=5.0, save_metrics=True, do_plot=True)


if __name__ == "__main__":
    try:
        asyncio.run(acquire_single_shot())
    except KeyboardInterrupt:
        log.info("Program interrupted by user.")
