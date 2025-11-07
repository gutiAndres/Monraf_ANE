import numpy as np
import matplotlib.pyplot as plt
import os
import csv

# ----------------------------
# Configuración
# ----------------------------
FIRST_FILE = 'hack_rf.csv'
SECOND_FILE = 'Keisight_analizer.csv'
ERROR_CSV = 'error_comparison.csv'

# ----------------------------
# Función robusta para leer CSV
# ----------------------------
def load_csv(filepath):
    try:
        data = np.genfromtxt(filepath, delimiter=',', skip_header=1, invalid_raise=False)
        # eliminar filas con NaN (por si hay texto o celdas vacías)
        data = data[~np.isnan(data).any(axis=1)]
        freqs = data[:, 0]
        amps = data[:, 1]
        return freqs, amps
    except Exception as e:
        raise RuntimeError(f"Error leyendo '{filepath}': {e}")

# ----------------------------
# Leer ambos archivos
# ----------------------------
if not (os.path.exists(FIRST_FILE) and os.path.exists(SECOND_FILE)):
    raise FileNotFoundError("Asegúrate de que existan 'first.csv' y 'second.csv' en el directorio actual.")

freq1, amp1 = load_csv(FIRST_FILE)
freq2, amp2 = load_csv(SECOND_FILE)

# Ajustar longitudes: usar hasta donde haya datos en second.csv
n = min(len(freq1), len(freq2))
freq1 = freq1[:n]
amp1 = amp1[:n]
amp2 = amp2[:n]

# ----------------------------
# Calcular error
# ----------------------------
error = amp1 - amp2

# ----------------------------
# Guardar error en CSV
# ----------------------------
with open(ERROR_CSV, 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['Frecuencia (MHz)', 'Error (dB)'])
    for fc, err in zip(freq1, error):
        writer.writerow([fc, err])

print(f"✅ Error guardado en '{ERROR_CSV}'")

# ----------------------------
# Graficar ambas amplitudes
# ----------------------------
plt.figure(figsize=(10, 5))
plt.plot(freq1, amp1, label=f'{FIRST_FILE}.csv', linewidth=1.5)
plt.plot(freq1, amp2, label=f'{SECOND_FILE}.csv', linewidth=1.5, linestyle='--')
plt.title("Comparación de espectros")
plt.xlabel("Frecuencia (MHz)")
plt.ylabel("Amplitud (dBm)")
plt.legend()
plt.grid(True, linestyle='--', alpha=0.6)
plt.tight_layout()
plt.show()

# ----------------------------
# Graficar error
# ----------------------------
plt.figure(figsize=(10, 5))
plt.plot(freq1, error, color='red', linewidth=1.3)
plt.title(f"Error ({FIRST_FILE} - {SECOND_FILE})")
plt.xlabel("Frecuencia (MHz)")
plt.ylabel("Error (dB)")
plt.grid(True, linestyle='--', alpha=0.6)
plt.tight_layout()
plt.show()
