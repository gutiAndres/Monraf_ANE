import numpy as np
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')  # backend sin GUI
from scipy.signal import welch
import os
import csv
import argparse
from pathlib import Path


def load_hackrf_cs8(filepath):
    """
    Carga archivo .cs8 (int8 interleaved IQ del HackRF)
    
    Parámetros:
    ------------
    filepath : str
        Ruta del archivo .cs8 a cargar.
    normalize : bool, opcional
        Si es True, normaliza las muestras a [-1, 1].

    Retorna:
    --------
    iq : np.ndarray (dtype=complex64)
        Vector de muestras IQ complejas normalizadas (si normalize=True)
    """
    # Cargar datos binarios intercalados I/Q de 8 bits con signo
    raw = np.fromfile(filepath, dtype=np.int8)

    # Separar componentes I y Q
    i_data = raw[0::2].astype(np.float32)
    q_data = raw[1::2].astype(np.float32)

    # Crear vector complejo IQ
    iq = i_data + 1j * q_data

    return iq


def compute_psd_welch(iq_samples, fs, scale='dB', R_ant=50, corrige_impedancia=True, nperseg=1024, overlap=0.5):
    """
    Calcula PSD usando el método de Welch, en varias escalas (V²/Hz, dB, dBm, dBFS).
    """
    from scipy.signal import welch
    import numpy as np
    scale = scale.lower()

    # Normalización (rango completo de int8 es [-128, 127])
    if scale == 'dbfs':
        # Extraer componentes I y Q desde el vector complejo
        i_data = np.real(iq_samples)
        q_data = np.imag(iq_samples)

        print(f"[INFO] Normalización DBFS: i_max={np.max(np.abs(i_data))}, q_max={np.max(np.abs(q_data))}")

        # Normalizar por el máximo absoluto de cada canal
        i_data /= np.max(np.abs(i_data))
        q_data /= np.max(np.abs(q_data))

        # Reconstruir el vector complejo normalizado
        iq_samples = i_data + 1j * q_data

        


    noverlap = int(nperseg * overlap)
    f, Pxx = welch(iq_samples, fs=fs, nperseg=nperseg, noverlap=noverlap, return_onesided=False)
    Pxx = np.fft.fftshift(Pxx)
    f = np.fft.fftshift(f)

    # --- Conversión de escala ---
    if corrige_impedancia==True:

        Pxx = Pxx / R_ant  # convertir V²/Hz -> W/Hz

    if scale == 'v2/hz':
        return f, Pxx

    elif scale == 'db':
        Pxx_dB = 10 * np.log10(Pxx + 1e-20)
        return f, Pxx_dB

    elif scale == 'dbm':
        if not corrige_impedancia:
            Pxx_W = Pxx / R_ant
        else:
            Pxx_W = Pxx
        Pxx_dBm = 10 * np.log10(Pxx_W * 1000 + 1e-20)
        return f, Pxx_dBm

    elif scale == 'dbfs':
        # Asumimos iq_samples normalizados a ±1 (full scale)
        # Potencia full-scale para una senoide: 0.5 (V²)
        if corrige_impedancia==True:
            Pxx = Pxx*R_ant  
                
        P_FS = 1
        Pxx_dBFS = 10 * np.log10(Pxx / P_FS + 1e-20)
        return f, Pxx_dBFS

    else:
        raise ValueError("Escala no válida. Use 'V2/Hz', 'dB', 'dBm' o 'dBFS'.")


def save_psd_to_csv(filepath, f, Pxx, scale):
    """
    Guarda resultados PSD en CSV dentro de /static/
    """
    save_dir = Path("static")
    save_dir.mkdir(exist_ok=True)

    # guardamos como "last_psd.csv" además de la ruta original
    filepath_static = save_dir / "last_psd.csv"

    with open(filepath_static, 'w', newline='') as f_csv:
        writer = csv.writer(f_csv)
        writer.writerow(['Frequency (Hz)', f'PSD ({scale})'])
        for freq, val in zip(f, Pxx):
            writer.writerow([freq, val])

    # si además quieres guardar el archivo original con nombre personalizado:
    with open(filepath, 'w', newline='') as f_csv:
        writer = csv.writer(f_csv)
        writer.writerow(['Frequency (Hz)', f'PSD ({scale})'])
        for freq, val in zip(f, Pxx):
            writer.writerow([freq, val])

    print(f"[OK] PSD guardada en {filepath_static} y {filepath}")


def plot_psd(f, Pxx, scale, save_path="static/last_plot.png"):
    """
    Genera el gráfico de la PSD y lo guarda en una imagen PNG.
    """
    Path(save_path).parent.mkdir(parents=True, exist_ok=True)
    
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(f, Pxx)
    ax.set_title(f"Densidad Espectral de Potencia (Escala: {scale})")
    ax.set_xlabel("Frecuencia [Hz]")
    ax.set_ylabel(f"PSD [{scale}]")
    ax.grid(True)
    fig.tight_layout()

    fig.savefig(save_path, format='png')
    plt.close(fig)
    print(f"[OK] Gráfico guardado en {save_path}")

def get_unique_filename(base_path, base_name, extension):
    """
    Genera un nombre de archivo único evitando sobreescritura.
    Ejemplo:
        si existe psd_output_dBm_10.csv → crea psd_output_dBm_10_1.csv
        si también existe → crea psd_output_dBm_10_2.csv, etc.
    """
    filename = f"{base_name}.{extension}"
    full_path = os.path.join(base_path, filename)
    counter = 1

    # Mientras el archivo exista, agrega un sufijo incremental
    while os.path.exists(full_path):
        filename = f"{base_name}_{counter}.{extension}"
        full_path = os.path.join(base_path, filename)
        counter += 1

    return full_path

#on7

def procesar_archivo_psd(iq_path, output_path, fs, indice, scale='dBfs', 
                         R_ant=50, corrige_impedancia=False, nperseg=2000, 
                         overlap=0.5, fc=None, plot=True
                         ):
    """
    Procesa un archivo IQ y calcula su PSD usando el método de Welch.
    
    Parámetros:
    -----------
    iq_path : str
        Ruta del archivo .cs8 a procesar
    output_path : str
        Directorio donde guardar los resultados
    fs : float
        Frecuencia de muestreo [Hz]
    indice : int
        Índice para el nombre del archivo de salida
    scale : str, opcional
        Escala de PSD: 'dBfs', 'dB', 'dBm', 'v2/hz' (default 'dBfs')
    R_ant : float, opcional
        Impedancia de antena en ohmios (default 50)
    corrige_impedancia : bool, opcional
        Si True, corrige por impedancia (default False)
    nperseg : int, opcional
        Muestras por segmento FFT (default 2000)
    overlap : float, opcional
        Solapamiento entre segmentos [0-1] (default 0.5)
    fc : float, opcional
        Frecuencia central. Si None, usa indice*1e6 (default None)
    plot : bool, opcional
        Si True, muestra el gráfico (default False)
    
    Retorna:
    --------
    tuple : (f, Pxx, csv_filename)
        Vector de frecuencias, PSD calculada y ruta del archivo guardado
    """
    
    # Calcular frecuencia central si no se proporciona
    if fc is None:
        fc = indice * 1000000
    
    print(f"[INFO] Procesando archivo: {iq_path}")
    print(f"[INFO] Parámetros: fs={fs} Hz, fc={fc} Hz, scale={scale}, nperseg={nperseg}")

    # === Cargar muestras ===
    iq_samples = load_hackrf_cs8(iq_path)
    print(f"[INFO] Cargadas {len(iq_samples)} muestras IQ desde {iq_path}")

    # === Calcular PSD ===
    f, Pxx = compute_psd_welch(
        iq_samples,
        fs=fs,
        scale=scale,
        R_ant=R_ant,
        corrige_impedancia=corrige_impedancia,
        nperseg=nperseg,
        overlap=overlap
    )

    # Ajustar frecuencias con la frecuencia central
    f += fc

    # === Guardar CSV con índice en el nombre (evita sobreescribir) ===
    os.makedirs(output_path, exist_ok=True)
    base_name = f"psd_output_{scale}_{indice}"
    csv_filename = get_unique_filename(output_path, base_name, "csv")
    save_psd_to_csv(csv_filename, f, Pxx, scale)
    print(f"[OK] PSD guardada en: {csv_filename}")

    # Mostrar RBW efectivo
    rbw = fs / nperseg
    print(f"RBW efectivo (welch): {rbw:.2f} Hz")

    # === Graficar si se solicita ===
    if plot:
        plot_psd(f, Pxx, scale)

    return f, Pxx, csv_filename







