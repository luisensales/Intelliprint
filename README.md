# INTELLIPRINT: Sistema Avanzado de Preflight mediante Redes Neuronales

> **Proyecto de Innovación en Formación Profesional (2026-2027)**  
> Desarrollado en colaboración entre **CPIFP Salesianos Urnieta LHIPI** (Líder - Gipuzkoa) y **CIFP Mendizabala LHII** (Araba).

---

## 🌐 Language Navigation / Hizkuntza Nabigazioa / Navegación por Idioma

| [🇪🇸 Español](#-español) | [📐 Euskara](#-euskara) | [🇬🇧 English](#-english) |
| :--- | :--- | :--- |
| • [Descripción](#descripción-es) | • [Deskribapena](#deskribapena-eu) | • [Description](#description-en) |
| • [Características](#características-clave-es) | • [Ezaugarri Nagusiak](#ezaugarri-nagusiak-eu) | • [Key Features](#key-features-en) |
| • [Estructura](#estructura-del-repositorio) | • [Egitura](#estructura-del-repositorio) | • [Repository Structure](#estructura-del-repositorio) |
| • [Instalación](#instalación-y-uso) | • [Instalazioa](#instalación-y-uso) | • [Installation](#instalación-y-uso) |

---

<a name="espanol"></a>
## 🇪🇸 ESPAÑOL

<a name="descripción-es"></a>
### Descripción del Proyecto
**INTELLIPRINT** es un sistema inteligente de verificación previa (*preflight*) y corrección automática de archivos PDF orientado a las artes gráficas y la preimpresión. Mediante la integración de redes neuronales (*RNN-LSTM*, *CNN*, *GNN*) y la orquestación agéntica con **Google Antigravity** (Gemini Pro / Gemma), el sistema analiza y corrige automáticamente fallos críticos antes de la entrada a máquina, minimizando tiempos de parada y desperdicio de material.

<a name="características-clave-es"></a>
### Características Clave
- 🤖 **Preflight Autónomo**: Corrección automática de sangrados, conversión de perfiles de color (RGB a CMYK) y detección de fuentes no incrustadas.
- 📉 **Sostenibilidad y Eficiencia**: Reducción del 30% en desperdicio de papel/maculatura y optimización del tiempo de revisión (< 5 min/archivo).
- ⚡ **Orquestación Agéntica**: Agentes inteligentes programados mediante *AgentSkills* en Google Antigravity con auditoría de alucinaciones (< 5%).

---

<a name="euskara"></a>
## 📐 EUSKARA

<a name="deskribapena-eu"></a>
### Proiektuaren Deskribapena
**INTELLIPRINT** arte grafikoen eta inprimatze-atzerako lanetarako PDF artxiboen aldez aurreko egiaztapen (*preflight*) eta zuzenketa automatikorako sistema adimenduna da. Sare neuronalak (*RNN-LSTM*, *CNN*, *GNN*) eta **Google Antigravity**-ren (Gemini Pro / Gemma) bidezko agente autonomoak konbinatuz, sistemak akats kritikoak detektatu eta automatikoki zuzentzen ditu makinara igaro aurretik, geldialdiak eta lehengaien hondakinak nabarmen murriztuz.

<a name="ezaugarri-nagusiak-eu"></a>
### Ezaugarri Nagusiak
- 🤖 **Preflight Autonomoa**: Odol-marken zuzenketa automatikoa, kolore-profilen bihurgunea (RGBdik CMYKra) eta txertatu gabeko tipografien detekzioa.
- 📉 **Jasangarritasuna eta Eraginkortasuna**: Paperezko hondakinen %30eko murrizketa eta berrikuspen denboraren optimizazioa (< 5 min/fitxategiko).
- ⚡ **Agente bidezko Orokortzea**: Google Antigravity-n garatutako *AgentSkills* bidezko agente adimendunak, aluzinazio-auditoretza zorrotzarekin (< %5).

---

<a name="english"></a>
## 🇬🇧 ENGLISH

<a name="description-en"></a>
### Project Description
**INTELLIPRINT** is an advanced AI-powered automated preflight and PDF correction system tailored for the graphic arts industry. By combining deep learning neural networks (*RNN-LSTM*, *CNN*, *GNN*) with agentic orchestration using **Google Antigravity** (Gemini Pro / Gemma), INTELLIPRINT automatically detects and fixes critical print errors prior to press runs, dramatically cutting downtime and material waste.

<a name="key-features-en"></a>
### Key Features
- 🤖 **Autonomous Preflight**: Automated bleed correction, color profile conversion (RGB to CMYK), and font embedding verification.
- 📉 **Sustainability & Efficiency**: 30% reduction in paper/material waste and accelerated review workflows (< 5 min/file).
- ⚡ **Agentic Orchestration**: Intelligent workflows built with *AgentSkills* in Google Antigravity featuring hallucination auditing (< 5%).

---

## 📁 Estructura del Repositorio / Repository Structure

```text
intelliprint/
├── src/
│   ├── pdf_checker.py       # Framework principal de orquestación y metadatos
│   ├── models/              # Modelos de redes neuronales (RNN-LSTM, CNN)
│   └── agents/              # Definición de AgentSkills para Google Antigravity
├── config/                  # Configuración de perfiles de preflight y color
├── tests/                   # Batería de pruebas con PDFs reales de taller
├── docs/                    # Documentación técnica y anexos del proyecto
└── README.md
```

---

## 🛠️ Instalación y Uso / Installation & Setup

1. **Clonar el repositorio / Clone repository:**
   ```bash
   git clone https://github.com/usuario/intelliprint.git
   cd intelliprint
   ```

2. **Instalar dependencias / Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Ejecutar verificación de prueba / Run check:**
   ```bash
   python src/pdf_checker.py --input muestra.pdf --profile cmyk_300dpi
   ```
