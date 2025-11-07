import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

# Cargar el archivo CSV
file_path = '/home/ogutierreze/GPDS_Proyects/Test_ANE/ANE2_Procesamiento/ANE2_procesamiento/MonRaF-ANE1/Outputs/resultado_psd_db.csv'

# Opción 1: Cargar sin encabezados y convertir explícitamente a numérico
df = pd.read_csv(file_path, header=None)

# Convertir ambas columnas a numérico, forzando errores a NaN
frecuencias = pd.to_numeric(df.iloc[:, 0], errors='coerce')
potencias = pd.to_numeric(df.iloc[:, 1], errors='coerce')

# Eliminar filas con NaN (si las hay)
mask = ~(np.isnan(frecuencias) | np.isnan(potencias))
frecuencias = frecuencias[mask]
potencias = potencias[mask]

# Crear el plot
plt.figure(figsize=(12, 6))
plt.plot(frecuencias, potencias, linewidth=1)
plt.xlabel('Frecuencia (Hz)')
plt.ylabel('Potencia (dBm)')
plt.title('Densidad Espectral de Potencia (PSD)')
plt.grid(True, alpha=0.3)
plt.tight_layout()
plt.show()

# Opcional: mostrar información de los datos
print(f"Forma de los datos: {len(frecuencias)} puntos")
print(f"Rango de frecuencia: {frecuencias.min():.2f} - {frecuencias.max():.2f} Hz")
print(f"Rango de potencia: {potencias.min():.2f} - {potencias.max():.2f} dBm")