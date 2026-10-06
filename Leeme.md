# 🖨️ INTELLIPRINT: Sistema Avanzado de Preflight mediante Redes Neuronales

> **Proyecto de Innovación en Formación Profesional (2026–2027)**  
> *Desarrollado en colaboración entre CPIFP Salesianos Urnieta LHIPI y CIFP Mendizabala LHII.*

---

## 🌐 Language Navigation / Hizkuntza Nabigazioa
- [Español (Castellano)](#-español)
- [Euskara](#-euskara)
- [English](#-english)

---

<a name="-español"></a>
## 🇪🇸 Español

### 📝 Descripción del Proyecto
**INTELLIPRINT** es un sistema de verificación previa (*preflight*) y corrección automática de archivos PDF para el sector de las artes gráficas. Basado en Inteligencia Artificial y redes neuronales, el sistema aprende del histórico de errores del taller para optimizar la preimpresión, minimizar las mermas de papel y tinta, y garantizar un flujo de producción sin paradas.

### 🔑 Características Principales
- **Análisis mediante IA**: Integración de arquitecturas de aprendizaje profundo (RNN-LSTM, CNN y GNN) para analizar código PDF y renderizados visuales.
- **Orquestación Agéntica**: Uso de agentes autónomos con **Google Antigravity** y **Gemini Pro / Gemma**.
- **AgentSkills Personalizadas**: Módulos especializados para la corrección automática de sangrados, perfiles de color (RGB a CMYK), resolución de imágenes y fuentes.
- **Transparencia y Anti-Alucinaciones**: Generación de *Artifacts* (logs, capturas y reportes de validación).
- **Sostenibilidad**: Reducción del desperdicio de material y energía en alineación con los ODS 9, 12 y 13.

### 🛠️ Estructura del Repositorio
```text
├── docs/                 # Documentación técnica y guía de uso
├── src/
│   ├── pdf_checker.py    # Framework principal de análisis y descomposición PDF
│   ├── models/           # Modelos de redes neuronales (RNN-LSTM, CNN)
│   └── skills/           # AgentSkills para Google Antigravity
├── samples/              # PDFs de prueba (errores típicos y validados)
└── README.md
🚀 Instalación y Uso Rápido
Bash
# Clonar el repositorio
git clone [https://github.com/tu-usuario/intelliprint.git](https://github.com/tu-usuario/intelliprint.git)
cd intelliprint

# Instalar dependencias
pip install -r requirements.txt

# Ejecutar verificación básica
python src/pdf_checker.py --input samples/test_file.pdf
