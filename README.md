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

<a name="-euskara"></a>
📐 Euskara
📝 Proiektuaren Deskribapena
INTELLIPRINT arte grafikoen sektorerako PDF artxiboen aldez aurreko egiaztapen (preflight) eta zuzenketa automatikoko sistema bat da. Adimen Artifizialean eta sare neuronaletan oinarrituta, sistemak inprimategiko akatsen historikotik ikasten du inprimatze-aurreko prozesua optimizatzeko, paper zein tinta hondakinak minimizatzeko eta ekoizpen-jario etenbabea bermatzeko.

🔑 Ezaugarri Nagusiak
IA bidezko Analisia: Sakoneko ikaskuntza-arkitekturak (RNN-LSTM, CNN eta GNN) PDF kodea zein bistaratze bisualak aztertzeko.

Agenteen Orkestrazioa: Agente autonomoak Google Antigravity eta Gemini Pro / Gemma erabiliz.

AgentSkill Pertsonalizatuak: Odol-marren, kolore-profilen (RGBtik CMYKra), irudien bereizmenaren eta tipografien zuzenketa automatikorako modulu espezializatuak.

Gardentasuna eta Anti-Haluzilazioak: Artifacts direlakoen sorrera (erregistroak, kapturak eta balioztatze-txostenak).

Jasangarritasuna: Material zein energia hondakinen murrizketa, 9, 12 eta 13 GJHekin lerrokatuta.

🛠️ Biltegiaren Egitura
Plaintext
├── docs/                 # Dokumentazio teknikoa eta erabiltzaile-gida
├── src/
│   ├── pdf_checker.py    # PDFak aztertzeko eta deskonposatzeko esparru nagusia
│   ├── models/           # Sare neuronalen modeloak (RNN-LSTM, CNN)
│   └── skills/           # Google Antigravity-rako AgentSkill-ak
├── samples/              # Proba-PDFak (ohiko akatsak eta balioztatutakoak)
└── README.md
🚀 Instalazioa eta Erabilera Azkarra
Bash
# Biltegia klonatu
git clone [https://github.com/zure-erabiltzailea/intelliprint.git](https://github.com/zure-erabiltzailea/intelliprint.git)
cd intelliprint

# Mendekotasunak instalatu
pip install -r requirements.txt

# Oinarrizko egiaztapena gauzatu
python src/pdf_checker.py --input samples/test_file.pdf
🇬🇧 English
📝 Project Overview
INTELLIPRINT is an advanced AI-powered automated preflight and PDF correction system for the graphic arts industry. Utilizing deep learning neural networks, the system autonomously learns from historic print-shop errors to optimize pre-press workflows, minimize paper/ink waste, and eliminate production downtime.

🔑 Key Features
AI Analysis: Deep learning architectures (RNN-LSTM, CNN, and GNN) for parsing PDF code and evaluating visual page renderings.

Agentic Orchestration: Autonomous agent workflows built on Google Antigravity using Gemini Pro / Gemma.

Custom AgentSkills: Specialized skill modules for auto-correcting bleed margins, color spaces (RGB to CMYK conversion), image resolution, and font embedding.

Transparency & Hallucination Control: Automated Artifacts generation (execution logs, before/after screenshots, and validation reports).

Sustainability: Reduces waste and energy footprint aligned with UN SDGs 9, 12, and 13.

🛠️️ Repository Structure
Plaintext
├── docs/                 # Technical documentation and user guides
├── src/
│   ├── pdf_checker.py    # Core PDF parsing and metadata extraction framework
│   ├── models/           # Deep learning models (RNN-LSTM, CNN)
│   └── skills/           # Custom AgentSkills for Google Antigravity
├── samples/              # Sample PDF files for testing and evaluation
└── README.md
🚀 Quick Start & Installation
Bash
# Clone the repository
git clone [https://github.com/your-username/intelliprint.git](https://github.com/your-username/intelliprint.git)
cd intelliprint

# Install requirements
pip install -r requirements.txt

# Run a basic preflight check
python src/pdf_checker.py --input samples/test_file.pdf
👥 Participating Centers / Zentro Parte-hartzaileak
CPIFP Salesianos Urnieta LHIPI (Leading Center / Zentro Liderra)

CIFP Mendizabala LHII (Partner Center / Zentro Parte-hartzailea)

📜 License
This project is licensed under the MIT License - see the LICENSE file for details.
