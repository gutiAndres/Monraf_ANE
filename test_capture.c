#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <complex.h>
#include "Modules/capture.h"
#include "Modules/processing.h"
#include "Modules/storage.h"


int main(int argc, char *argv[]) {

    // Parámetros obligatorios u opcionales
    long samples = (argc > 1) ? strtol(argv[1], NULL, 10) : 20000000;
    uint64_t freq = (argc > 2) ? strtoull(argv[2], NULL, 10) : 498;

    // Nuevos parámetros desde la línea de comandos
    uint16_t lna  = (argc > 3) ? (uint16_t)atoi(argv[3]) : 24;  // LNA gain
    uint16_t vga  = (argc > 4) ? (uint16_t)atoi(argv[4]) : 2;   // VGA gain

    printf("▶ Parámetros usados: samples=%ld, freq=%lu MHz, LNA=%u, VGA=%u\n",
           samples, freq, lna, vga);

    // Llamada actualizada a la función
    if (capture_signal(samples, freq, lna, vga) != 0)
        return 1;

    size_t N;
    complex double* x = convert_cs8("Samples/0", &N);
    if (!x) return 1;
    
   /*
    remove_dc(x, N);
   
    int segment_length = 4096;
    double fs = 20000000;
    double overlap = 0.5;

    double* f = malloc(segment_length * sizeof(double));
    double* Pxx_dB = malloc(segment_length * sizeof(double));

    compute_welch_psd(x, N, fs, segment_length, overlap, f, Pxx_dB);
    save_psd_to_csv(f, Pxx_dB, segment_length, "Outputs/resultado_psd_db.csv");

    free(x); free(f); free(Pxx_dB);
    
    */

    return 0;
}