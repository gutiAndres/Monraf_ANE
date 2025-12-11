
import subprocess
import time
from pathlib import Path
import numpy as np 
import csv
import os
from psd_welch_hackrf_exec import procesar_archivo_psd
import os, time
import sys


# ==============================
# Configuración general
# ==============================

def main():

    # Modos permitidos
    MODOS_VALIDOS = {
        "dinamic_range",
        "power_precision",
        "DANL",
        "frequency_accuracy",
        "DANL_dbm",
        None,
    }


        
    f_in = sys.argv[1]
    f_fin = sys.argv[2]
    step = sys.argv[3]
    n_cycles = sys.argv[4]
    try:
        test_mode = sys.argv[5]
    except IndexError:
        test_mode = None


        # === Ruta automática ===
    # Obtiene el directorio donde está este script Python actual
    base_dir = Path(__file__).resolve().parent

    
    #### ------------- Parametros ----------- ###
    TIME_SLEEP = 0.5    # tiempo entre ciclo de adquisición al cambiar de frecuencia 
    server_url = "http://192.168.0.102:5000/upload_csv"     # servidor local host corriendo en el dispositivo de destino
 
    #### ------------------------------------ ### 


    # Validar test_mode
    if test_mode not in MODOS_VALIDOS:
        raise ValueError(
            f"Modo inválido: '{test_mode}'. "
            f"Modos permitidos: {', '.join(str(m) for m in MODOS_VALIDOS)}"
        )
    #---------------solo si test_mode = None--------------------
    output_path = base_dir /"Output_power_data2"
    #----------------------------------------------------------


    #------ parametros fijos para testeo -------- 
    exe_path = "./test_capture"
    iq_base_path = base_dir /"Samples"
    corrige_impedancia = False
    R_ant = 50
    nperseg = 2048
    overlap = 0.5
    scale = 'dBm'
    samples = 20000000

    if test_mode == "DANL":
        samples = 10000000
    

   #Vector de frecuencias segun el modo de testeo
    if test_mode == "DANL":
        output_path = base_dir /"Output_DANL"   # Nombre del directorio de destino en el PC
        scale = 'dBfs'
        frecuencias = [freq for freq in range(int(50), int(5950)+1, int(50)) for _ in range(int(5))]
    elif test_mode == "dinamic_range":
        frecuencias = [freq for freq in range(int(98), int(118)+1, int(20)) for _ in range(int(200))]
        output_path = base_dir /"Output_dinamic_range"
    elif test_mode == "power_precision":
        frecuencias = [freq for freq in range(int(98), int(3998)+1, int(100)) for _ in range(int(50))]
        output_path = base_dir /"Output_power_data2"
    elif test_mode == "frequency_accuracy":
        frecuencias = [freq for freq in range(int(998), int(2998)+1, int(1000)) for _ in range(int(20))]
        output_path = base_dir /"Output_frequency_error"
        nperseg = 16384
    elif test_mode is None:
        frecuencias = [freq for freq in range(int(f_in), int(f_fin)+1, int(step)) for _ in range(int(n_cycles))]
    elif test_mode == "DANL_dbm":
        frecuencias = [freq for freq in range(int(98), int(5898)+1, int(10000)) for _ in range(int(5))]
        output_path = base_dir /"Output_DANL"
    
    
    update_static = True          # Actualizar csv del servidor 

    if test_mode == "DANL":
        update_static = False
    

    #------- Amplitudes para rango dinamico ------------
    if test_mode == "dinamic_range":
        dinamic_range = True  #Guardar la amplitud en el nombre del csv resultante 
    else:
        dinamic_range = False
        

    amp_init =-60
    amp_fin =-10
    step_amp = 2

    amp = range(int(amp_init),int(amp_fin)+1,int(step_amp))
    j=0
    ifamp = amp[j]

   #----- Bucle de adquisición y preocesamiento ------

    t_inicio_total = time.perf_counter()


    for i, freq in enumerate(frecuencias, start=1):
        if dinamic_range:
            ifamp = amp[j]
        else:
            ifamp =1

        print(f"\n=== [CICLO {i}] Ejecutando captura y procesamiento para {freq} MHz, MODO {test_mode} ===")
        if (i >1):
            if frecuencias[i-1]==frecuencias[i-2]:
                print("...")
            else:
                print(f"\n==========FRECUENCIA DE MEDICIÓN HA CAMBIADO A {frecuencias[i-1]+2}, ¡¡¡CAMBIE LA FRECUECNIA EN EL GENERADOR!!!======")
                print(f"\n==========FRECUENCIA DE MEDICIÓN HA CAMBIADO A {frecuencias[i-1]+2}, ¡¡¡CAMBIE LA FRECUECNIA EN EL GENERADOR!!!======")
                time.sleep(TIME_SLEEP)               
            

        t_inicio_ciclo = time.perf_counter()

        # --- Ejecutar captura C ---
        print(f"[INFO] Ejecutando captura: {exe_path} {samples} {freq}")
        subprocess.run([
            exe_path,
            str(samples),
            str(freq),
            str(0),
            str(0)
        ], check=True)
        print(f"[OK] Captura completada para {freq} MHz")

        # --- Construir ruta del archivo IQ generado ---
        iq_path = os.path.join(iq_base_path, str(0))  # por ejemplo: Samples/5680
        print(f"[INFO] Procesando archivo IQ: {iq_path}")

        # --- Llamar directamente a la función Python ---
        f, Pxx, csv_filename = procesar_archivo_psd(
            iq_path=iq_path,
            output_path=output_path,
            fs=20e6,
            indice=freq,
            scale=scale,
            R_ant=R_ant,
            corrige_impedancia=corrige_impedancia,
            nperseg=nperseg,
            overlap=overlap,
            plot=False,
            save_csv=False,
            update_static= update_static, 
            Amplitud=ifamp,
            dinamic_range = False,
            server_url = server_url
        )
        if dinamic_range:
            j +=1

        print(f"psd_ {Pxx[10:20]}")

        print(f"[OK] PSD procesada para {freq} MHz. Archivo: {csv_filename}")

        t_fin_ciclo = time.perf_counter()
        print(f"⏱ Duración ciclo {freq} MHz: {t_fin_ciclo - t_inicio_ciclo:.2f} s")

        print("Esperando para la siguiente ...")
        time.sleep(0.3)

    t_fin_total = time.perf_counter()
    print(f"\n🏁 Duración total del proceso: {t_fin_total - t_inicio_total:.2f} s")

if __name__ == "__main__":
    main()