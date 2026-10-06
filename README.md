# INTELLIPRINT: Sistema Avanzado de Preflight mediante Redes Neuronales

> **Proyecto de Innovación en Formación Profesional (2026-2027)**  
> Desarrollado en colaboración entre **CPIFP Salesianos Urnieta LHIPI** (Líder - Gipuzkoa) y **CIFP Mendizabala LHII** (Araba).

---

## 🌐 Language Navigation / Hizkuntza Nabigazioa / Navegación por Idioma

| [🇪🇸 Español](#espanol) | [📐 Euskara](#euskara) | [🇬🇧 English](#english) |
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
**INTELLIPRINT** es un sistema inteligente de verificación previa (*preflight*) y corrección automática de archivos PDF orientado a las artes gráficas y la preimpresión[cite: 1]. Mediante la integración de redes neuronales (*RNN-LSTM*, *CNN*, *GNN*)[cite: 3, 4] y la orquestación agéntica con **Google Antigravity** (Gemini Pro / Gemma)[cite: 4], el sistema analiza y corrige automáticamente fallos críticos antes de la entrada a máquina, minimizando tiempos de parada y desperdicio de material[cite: 1, 3, 5, 6].

<a name="características-clave-es"></a>
### Características Clave
- 🤖 **Preflight Autónomo**: Corrección automática de sangrados, conversión de perfiles de color (RGB a CMYK) y detección de fuentes no incrustadas[cite: 3, 8].
- 📉 **Sostenibilidad y Eficiencia**: Reducción del 30% en desperdicio de papel/maculatura y optimización del tiempo de revisión (< 5 min/archivo)[cite: 6, 8].
- ⚡ **Orquestación Agéntica**: Agentes inteligentes programados mediante *AgentSkills* en Google Antigravity con auditoría de alucinaciones (< 5%)[cite: 4, 5, 9].

---

<a name="euskara"></a>
## 📐 EUSKARA

<a name="deskribapena-eu"></a>
### Proiektuaren Deskribapena
**INTELLIPRINT** arte grafikoen eta inprimatze-atzerako lanetarako PDF artxiboen aldez aurreko egiaztapen (*preflight*) eta zuzenketa automatikorako sistema adimenduna da[cite: 1]. Sare neuronalak (*RNN-LSTM*, *CNN*, *GNN*)[cite: 3, 4] eta **Google Antigravity**-ren (Gemini Pro / Gemma) bidezko agente autonomoak[cite: 4] konbinatuz, sistemak akats kritikoak detektatu eta automatikoki zuzentzen ditu makinara igaro aurretik, geldialdiak eta lehengaien hondakinak nabarmen murriztuz[cite: 1, 3, 5, 6].

<a name="ezaugarri-nagusiak-eu"></a>
### Ezaugarri Nagusiak
- 🤖 **Preflight Autonomoa**: Odol-marken zuzenketa automatikoa, kolore-profilen bihurgunea (RGBdik CMYKra) eta txertatu gabeko tipografien detekzioa[cite: 3, 8].
- 📉 **Jasangarritasuna eta Eraginkortasuna**: Paperezko hondakinen %30eko murrizketa eta berrikuspen denboraren optimizazioa (< 5 min/fitxategiko)[cite: 6, 8].
- ⚡ **Agente bidezko Orokortzea**: Google Antigravity-n garatutako *AgentSkills* bidezko agente adimendunak, aluzinazio-auditoretza zorrotzarekin (< %5)[cite: 4, 5, 9].

---

<a name="english"></a>
## 🇬🇧 ENGLISH

<a name="description-en"></a>
### Project Description
**INTELLIPRINT** is an advanced AI-powered automated preflight and PDF correction system tailored for the graphic arts industry[cite: 1]. By combining deep learning neural networks (*RNN-LSTM*, *CNN*, *GNN*)[cite: 3, 4] with agentic orchestration using **Google Antigravity** (Gemini Pro / Gemma)[cite: 4], INTELLIPRINT automatically detects and fixes critical print errors prior to press runs, dramatically cutting downtime and material waste[cite: 1, 3, 5, 6].

<a name="key-features-en"></a>
### Key Features
- 🤖 **Autonomous Preflight**: Automated bleed correction, color profile conversion (RGB to CMYK), and font embedding verification[cite: 3, 8].
- 📉 **Sustainability & Efficiency**: 30% reduction in paper/material waste and accelerated review workflows (< 5 min/file)[cite: 6, 8].
- ⚡ **Agentic Orchestration**: Intelligent workflows built with *AgentSkills* in Google Antigravity featuring hallucination auditing (< 5%)[cite: 4, 5, 9].

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
