/**
 * @file bacn_RF.c
 * @brief Implementación de captura de datos IQ con HackRF.
 *
 * Este archivo contiene la implementación de funciones para manejar la captura de datos IQ 
 * utilizando un dispositivo HackRF. Incluye manejo de señales, configuración del dispositivo 
 * y almacenamiento de datos en archivos binarios.
 */

#include <libhackrf/hackrf.h>
#include <stdio.h>
#include <string.h>
#include <stdbool.h>
#include <unistd.h>
#include <signal.h>
#include "bacn_RF.h"
#include "IQ.h"
#include "../Drivers/bacn_gpio.h"

/** @brief Variable para controlar la finalización del bucle principal. */
static volatile bool do_exit = false;

/** @brief Archivo para almacenar los datos de salida. */
FILE* file = NULL;

/** @brief Contador de bytes transferidos. */
volatile uint32_t byte_count = 0;

/** @brief Tamaño del buffer de streaming. */
uint64_t stream_size = 0;

/** @brief Puntero al inicio del buffer circular de streaming. */
uint32_t stream_head = 0;

/** @brief Puntero al final del buffer circular de streaming. */
uint32_t stream_tail = 0;

/** @brief Número de streams descartados. */
uint32_t stream_drop = 0;

/** @brief Buffer para almacenamiento temporal de datos de streaming. */
uint8_t* stream_buf = NULL;

/** @brief Flag para limitar la cantidad de muestras transferidas. */
bool limit_num_samples = true;

/** @brief Bytes restantes para transferir. */
size_t bytes_to_xfer = 0;

/** @brief Frecuencia inicial para el barrido. */
int64_t lo_freq = 0;

/** @brief Frecuencia final para el barrido. */
int64_t hi_freq = 0;

/** @brief Dispositivo HackRF activo. */
static hackrf_device* device = NULL;

extern int64_t central_freq[60];

extern uint8_t getData;

/**
 * @brief Detiene el bucle principal de captura.
 */
void stop_main_loop(void)
{
	do_exit = true;
	kill(getpid(), SIGALRM);
}


int rx_callback(hackrf_transfer* transfer)
{
	size_t bytes_to_write;
	size_t bytes_written;

	if (file == NULL) {
		stop_main_loop();
		return -1;
	}

	/* Determina cuántos bytes escribir */
	bytes_to_write = transfer->valid_length;

	/* Actualiza el conteo de bytes */
	byte_count += transfer->valid_length;
	
	if (limit_num_samples) {
		if (bytes_to_write >= bytes_to_xfer) {
			bytes_to_write = bytes_to_xfer;
		}
		bytes_to_xfer -= bytes_to_write;
	}

	/* Escribe los datos directamente en el archivo si no hay búfer de transmisión */
	if (stream_size == 0) {
		bytes_written = fwrite(transfer->buffer, 1, bytes_to_write, file);
		if ((bytes_written != bytes_to_write) ||
		    (limit_num_samples && (bytes_to_xfer == 0))) {
			stop_main_loop();
			fprintf(stderr, "Total Bytes: %u\n",byte_count);
			return -1;
		} else {
			return 0;
		}
	}

	if ((stream_size - 1 + stream_head - stream_tail) % stream_size <
	    bytes_to_write) {
		stream_drop++;
	} else {
		if (stream_tail + bytes_to_write <= stream_size) {
			memcpy(stream_buf + stream_tail,
			       transfer->buffer,
			       bytes_to_write);
		} else {
			memcpy(stream_buf + stream_tail,
			       transfer->buffer,
			       (stream_size - stream_tail));
			memcpy(stream_buf,
			       transfer->buffer + (stream_size - stream_tail),
			       bytes_to_write - (stream_size - stream_tail));
		};
		__atomic_store_n(
			&stream_tail,
			(stream_tail + bytes_to_write) % stream_size,
			__ATOMIC_RELEASE);
	}
	return 0;
}


void sigint_callback_handler(int signum)
{
	fprintf(stderr, "Caught signal %d\n", signum);
	do_exit = true;
}

/**
 * @brief Manejador para la señal SIGALRM.
 */
void sigalrm_callback_handler()
{
}



/**
 * @brief Captura muestras desde la HackRF One y las guarda en archivos binarios.
 * 
 * La función puede operar en varios modos (RX o TDT). 
 * En modo normal realiza barridos (sweep) cambiando la frecuencia central
 * en pasos definidos por el ancho de banda. En modo TDT fija una frecuencia específica.
 * 
 * @param central_freq_Rx_MHz Frecuencia central de recepción (en MHz)
 * @param samples_to_xfer_max Número máximo de muestras a transferir por captura
 * @param transceiver_mode    Modo de operación (RX, TX, TDT, etc.)
 * @param lna_gain            Ganancia del amplificador de bajo ruido (LNA)
 * @param vga_gain            Ganancia del amplificador de ganancia variable (VGA)
 * @param centralFrec_TDT     Frecuencia central usada en modo TDT
 * @param is_second_sample    Indica si se trata del segundo bloque (ajuste de frecuencia)
 * 
 * @return 0 si la captura se ejecuta correctamente, -1 en caso de error.
 */

int getSamples(uint64_t central_freq_Rx_MHz, long samples_to_xfer_max, transceiver_mode_t transceiver_mode, uint16_t lna_gain, uint16_t vga_gain, uint16_t centralFrec_TDT, bool is_second_sample)
{
	int64_t c_f = central_freq_Rx_MHz;
    int result = 0;                     // Variable para almacenar códigos de retorno
	int64_t lo_freq = 0, hi_freq = 0;   // Límites inferior y superior de frecuencia (en Hz)
	uint8_t tSample = 0;                // Número de bloques (ventanas) a capturar
	int64_t FreqTDT;                    // Frecuencia central para modo TDT (Hz)
	uint64_t byte_count_now = 0;        // Bytes recibidos por ventana
	char path[20];                      // Ruta de archivo para guardar muestras
	fprintf(stderr, "frecuencia central: %lu\n", c_f);
	// -------------------------------------------------------------------------
	// 1. Cálculo de frecuencias de captura según modo de operación
	// -------------------------------------------------------------------------

	if (transceiver_mode == TRANSCEIVER_MODE_TDT) { 
		// Modo TDT: captura fija en una sola frecuencia
		FreqTDT = centralFrec_TDT * 1000000;    // Conversión MHz → Hz
		fprintf(stderr, "central frequency: %lu\n", FreqTDT);
		tSample = 1;                            // Solo una ventana
	} 
	else {
		// Modo normal (barrido): define rango de ±10 MHz alrededor de la frecuencia central
		lo_freq = (central_freq_Rx_MHz - 10) * 1000000;
		hi_freq = (central_freq_Rx_MHz + 10) * 1000000;

		// Si se solicita un segundo bloque, desplaza 2 MHz el rango
		if (is_second_sample) {
			lo_freq += 2000000;
			hi_freq += 2000000;
		}

		// Calcula número de pasos (ventanas) en el sweep
		tSample = (hi_freq - lo_freq) / DEFAULT_SAMPLE_RATE_HZ;
		fprintf(stderr, "frequency_lo: %lu\n", lo_freq);

		// Define la frecuencia inicial del primer bloque
		central_freq[0] = lo_freq + DEFAULT_CENTRAL_FREQ_HZ;

		
		// Calcula y muestra las frecuencias centrales para cada paso
		for(uint8_t i = 1; i < tSample; i++) {
			central_freq[i] = central_freq[0] + DEFAULT_SAMPLE_RATE_HZ;
			fprintf(stderr, "central frequency: %lu\n", central_freq[i]); 
		}
	}

	// -------------------------------------------------------------------------
	// 2. Selección automática de antena según frecuencia
	// RF1 para frecuencias altas (> 1 GHz), RF2 para bajas
	// -------------------------------------------------------------------------
	if(lo_freq > 999999999) {
		switch_ANTENNA(RF1);
	} else {
		switch_ANTENNA(RF2);
	}

	// -------------------------------------------------------------------------
	// 3. Inicialización de la librería HackRF
	// -------------------------------------------------------------------------
	result = hackrf_init();
	if (result != HACKRF_SUCCESS) {
		fprintf(stderr, "hackrf_init() failed: %s (%d)\n",
		        hackrf_error_name(result), result);
		return -1;
	}

	// -------------------------------------------------------------------------
	// 4. Configuración de manejadores de señales del sistema
	// Permite detener la adquisición limpiamente al recibir señales
	// -------------------------------------------------------------------------
	signal(SIGINT, &sigint_callback_handler);
	signal(SIGILL, &sigint_callback_handler);
	signal(SIGFPE, &sigint_callback_handler);
	signal(SIGSEGV, &sigint_callback_handler);
	signal(SIGTERM, &sigint_callback_handler);
	signal(SIGABRT, &sigint_callback_handler);
	signal(SIGALRM, &sigalrm_callback_handler);

	fprintf(stderr, "Device initialized\r\n");

	// -------------------------------------------------------------------------
	// 5. Bucle principal de captura (barrido)
	// Recorre todas las frecuencias planificadas
	// -------------------------------------------------------------------------

	for(uint8_t i=0; i<tSample; i++)
	{		
		byte_count_now = 0;
		// Determina el número de bytes a transferir según modo
		if (transceiver_mode == TRANSCEIVER_MODE_TDT) { 
			bytes_to_xfer = DEFAULT_SAMPLES_TDT_XFER_MAX * 2ull;
		} else {
			// bytes_to_xfer = DEFAULT_SAMPLES_TO_XFER_MAX * 2ull;
			bytes_to_xfer = samples_to_xfer_max * 2ull;
		}
		
		// ---------------------------------------------------------------------
		// 6. Creación del archivo donde se guardarán las muestras IQ
		// Cada paso se guarda en un archivo distinto: Samples/0, Samples/1, ...
		// ---------------------------------------------------------------------

		memset(path, 0, 20);
		sprintf(path, "Samples/%d", i);
		file = fopen(path, "wb");
	
		if (file == NULL) {
			fprintf(stderr, "Failed to open file: %s\n", path);
			return -1;
		}
		// Aumenta el tamaño del buffer de escritura para optimizar IO
		result = setvbuf(file, NULL, _IOFBF, FD_BUFFER_SIZE);
		if (result != 0) {
			fprintf(stderr, "setvbuf() failed: %d\n", result);
			return -1;
		}

		fprintf(stderr,"Start Acquisition\n");

		// ---------------------------------------------------------------------
		// 7. Apertura del dispositivo HackRF
		// ---------------------------------------------------------------------

		result = hackrf_open(&device);
		if (result != HACKRF_SUCCESS) {
			fprintf(stderr,
				"hackrf_open() failed: %s (%d)\n",
				hackrf_error_name(result),
				result);
			return -1;
		}

		// ---------------------------------------------------------------------
		// 8. Configura tasa de muestreo según modo
		// ---------------------------------------------------------------------

		if (transceiver_mode == TRANSCEIVER_MODE_TDT) { 
			result = hackrf_set_sample_rate(device, DEFAULT_SAMPLE_RATE_TDT);
			if (result != HACKRF_SUCCESS) {
				fprintf(stderr,
					"hackrf_set_sample_rate() failed: %s (%d)\n",
					hackrf_error_name(result),
					result);
				return -1;
			}
		} else {
			result = hackrf_set_sample_rate(device, DEFAULT_SAMPLE_RATE_HZ);
			if (result != HACKRF_SUCCESS) {
				fprintf(stderr,
					"hackrf_set_sample_rate() failed: %s (%d)\n",
					hackrf_error_name(result),
					result);
				return -1;
			}
		}	
		
        // Desactiva modo de sincronización por hardware
		result = hackrf_set_hw_sync_mode(device, 0);
		if (result != HACKRF_SUCCESS) {
			fprintf(stderr,
				"hackrf_set_hw_sync_mode() failed: %s (%d)\n",
				hackrf_error_name(result),
				result);
			return -1;
		}

		// ---------------------------------------------------------------------
		// 9. Configura frecuencia central para este paso
		// ---------------------------------------------------------------------

		if (transceiver_mode == TRANSCEIVER_MODE_TDT) { 
			result = hackrf_set_freq(device, FreqTDT);
		if (result != HACKRF_SUCCESS) {
			fprintf(stderr,
				"hackrf_set_freq() failed: %s (%d)\n",
				hackrf_error_name(result),
				result);
			return -1;
		}	
		} else {
			result = hackrf_set_freq(device, central_freq[i]);
			if (result != HACKRF_SUCCESS) {
				fprintf(stderr,
					"hackrf_set_freq() failed: %s (%d)\n",
					hackrf_error_name(result),
					result);
				return -1;
			}	
		}	
		// ---------------------------------------------------------------------
		// 10. Configura ganancias y comienza la captura (RX)
		// ---------------------------------------------------------------------

		if (transceiver_mode == TRANSCEIVER_MODE_RX) {
			// RX estándar con ganancia mínima
			result = hackrf_set_vga_gain(device, 0);
			result |= hackrf_set_lna_gain(device, 0);
			result |= hackrf_start_rx(device, rx_callback, NULL);
		} else {
			// Modo configurable con ganancias dadas
			result = hackrf_set_vga_gain(device, vga_gain);
			result |= hackrf_set_lna_gain(device, lna_gain);
			result |= hackrf_start_rx(device, rx_callback, NULL);
		}

		if (result != HACKRF_SUCCESS) {
			fprintf(stderr,
				"hackrf_start_rx() failed: %s (%d)\n",
				hackrf_error_name(result),
				result);
			return -1;
		}

		// ---------------------------------------------------------------------
		// 11. Espera señal (SIGALRM o interrupción del usuario)
		// Bloquea ejecución hasta que se complete la adquisición
		// ---------------------------------------------------------------------
		pause();

		// Lee contador de bytes transferidos en este intervalo
		byte_count_now = byte_count;
		byte_count = 0;

		if (!((byte_count_now == 0))) {
			fprintf(stderr, "Name file RDY: %d\n", i);				
		}

		if ((byte_count_now == 0)) {
			fprintf(stderr,
				"Couldn't transfer any bytes for one second.\n");
			break;
		}	

		// ---------------------------------------------------------------------
		// 12. Detiene la captura y cierra recursos del paso actual
		// ---------------------------------------------------------------------
		result = hackrf_is_streaming(device);
		if (do_exit) {
			fprintf(stderr, "Exiting...\n");
		} else {
			fprintf(stderr,
				"Exiting... device_is_streaming() result: %s (%d)\n",
				hackrf_error_name(result),
				result);
		}

		// Detiene recepción RX
		result = hackrf_stop_rx(device);
		if (result != HACKRF_SUCCESS) {
			fprintf(stderr,
				"stop_rx() failed: %s (%d)\n",
				hackrf_error_name(result),
				result);
		} else {
			fprintf(stderr, "stop_rx() done\n");
		}		
	
		// Cierra archivo actual
		if (file != NULL) {
			if (file != stdin) {
				fflush(file);
			}
			if ((file != stdout) && (file != stdin)) {
				fclose(file);
				file = NULL;
				fprintf(stderr, "fclose() done\n");
			}
		}

		// Cierra dispositivo HackRF
		result = hackrf_close(device);
		if (result != HACKRF_SUCCESS) {
			fprintf(stderr,
				"device_close() failed: %s (%d)\n",
				hackrf_error_name(result),
				result);
		} else {
			fprintf(stderr, "device_close() done\n");
		}			
	}

	// -------------------------------------------------------------------------
	// 13. Finaliza sesión HackRF global
	// -------------------------------------------------------------------------

	if (device != NULL) 
	{
		hackrf_exit();
		fprintf(stderr, "device_exit() done\n");
	}

	fprintf(stderr, "exit\n");
	return 0;
}
