#!/bin/bash
set -e

# ==========================
# CONFIGURACIÓN
# ==========================
BUILD_DIR="build"
EXECUTABLE_NAME="test_capture"

# ==========================
# FUNCIONES AUXILIARES
# ==========================
clean_build() {
    echo "🧹 Limpiando compilación anterior..."
    rm -rf "$BUILD_DIR" "$EXECUTABLE_NAME"
}

# ==========================
# MANEJO DE ARGUMENTOS
# ==========================
if [[ "$1" == "clean" ]]; then
    clean_build
    echo "✔ Limpieza completa."
    exit 0
fi

# ==========================
# COMPILACIÓN
# ==========================
echo "🔧 Creando directorio de compilación..."
mkdir -p "$BUILD_DIR"
cd "$BUILD_DIR"

echo "⚙️ Ejecutando CMake..."
cmake -DCMAKE_BUILD_TYPE=Release ..

echo "🚀 Compilando con make..."
make -j"$(nproc)"

# ==========================
# COPIAR EJECUTABLE AL RAÍZ
# ==========================
if [[ -f "$EXECUTABLE_NAME" ]]; then
    echo "📦 Copiando ejecutable al directorio raíz..."
    cp "$EXECUTABLE_NAME" ..
    cd ..
    echo "✅ Compilación exitosa. Ejecutable generado:"
    echo "   → $(pwd)/$EXECUTABLE_NAME"
else
    echo "❌ Error: no se encontró el ejecutable '$EXECUTABLE_NAME'."
    exit 1
fi
