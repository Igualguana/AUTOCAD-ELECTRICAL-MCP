# AutoCAD Electrical — AI Control Center
## Guía completa de instalación, uso y validación

---

## Resumen del sistema

Este proyecto conecta AutoCAD Electrical 2025 con motores de IA (Claude y Ollama) mediante dos modos de operación:

| Modo | Cliente | Motor IA | Requiere |
|------|---------|----------|----------|
| **Modo A** | Claude Code (CLI) | Claude API | API key de Anthropic |
| **Modo B** | Interfaz web local | Ollama (local) | Ollama instalado |

Ambos modos usan el mismo núcleo: `src/tools/` → `src/autocad/connection.py` → AutoCAD Electrical 2025 via COM.

---

## Estructura del proyecto

```
MCP AutoCAD/
├── src/
│   ├── server.py           ← Servidor MCP (FastMCP, 34 tools, stdio)
│   ├── config.py           ← Cargador de config YAML + .env
│   ├── autocad/
│   │   ├── connection.py   ← Singleton COM hacia AutoCAD
│   │   └── utils.py        ← Helpers: layers, attrs, geometry
│   ├── providers/
│   │   ├── base.py         ← Interfaz abstracta BaseProvider
│   │   ├── claude.py       ← Anthropic SDK
│   │   ├── ollama.py       ← Ollama HTTP streaming
│   │   └── openai_compat.py← OpenAI/Groq/LM Studio
│   └── tools/
│       ├── drawing.py      ← 5 tools: líneas, círculos, arcos, texto, rect
│       ├── electrical.py   ← 7 tools: símbolos, ladders, PLC, cross-refs
│       ├── wires.py        ← 5 tools: cables, numeración, atributos
│       ├── components.py   ← 6 tools: CRUD componentes + búsqueda
│       ├── reports.py      ← 5 tools: BOM, wire list, terminal, PLC I/O
│       └── project.py      ← 6 tools: gestión proyecto y dibujos
├── web/
│   ├── backend/
│   │   ├── app.py          ← FastAPI: endpoints REST
│   │   ├── chat.py         ← Orquestación IA → tools
│   │   └── state.py        ← Buffer de logs e historial
│   └── frontend/
│       ├── index.html      ← Dashboard web
│       ├── css/style.css   ← Tema oscuro premium
│       └── js/
│           ├── api.js      ← Llamadas al backend
│           └── main.js     ← Lógica de UI
├── scripts/
│   ├── install.py          ← Setup automático
│   ├── test_connection.py  ← Diagnóstico AutoCAD COM
│   ├── switch_model.py     ← Cambiar provider/modelo
│   └── ollama_manager.py   ← Gestionar modelos Ollama
├── tests/
│   └── test_tools.py       ← Tests unitarios + integración
├── config.yaml             ← Configuración principal
├── mcp_config.json         ← Registro MCP para Claude Code
├── .env                    ← API keys (no subir al repo)
├── pyproject.toml          ← Dependencias del proyecto
├── start_web.py            ← Arranca la interfaz web (Python)
└── start_web.bat           ← Arranca la interfaz web (Windows)
```

---

## Requisitos previos

- Windows 10/11 (64-bit)
- Python 3.11 o superior
- AutoCAD Electrical 2025 instalado
- Para Modo B: Ollama instalado (ver más abajo)
- Para Modo A: API key de Anthropic

---

## Instalación

### Paso 1 — Instalar dependencias Python

```cmd
cd "\\data2\ENG_D\randy\randy dev\Nuevo\MCP AutoCAD"
pip install -e .
```

Esto instala todas las dependencias incluyendo FastAPI, uvicorn, mcp, pywin32, anthropic, etc.

O manualmente:

```cmd
pip install mcp pywin32 pyautocad pyyaml python-dotenv anthropic openai httpx click rich fastapi "uvicorn[standard]"
```

### Paso 2 — Configurar variables de entorno

El archivo `.env` ya existe con valores de ejemplo. Édítalo:

```
# Para Modo B (Ollama, sin Claude): no necesitas cambiar nada
ACTIVE_PROVIDER=ollama

# Para Modo A (Claude): agrega tu API key
ANTHROPIC_API_KEY=sk-ant-...
```

### Paso 3 — Instalar Ollama (para Modo B)

1. Descarga Ollama desde: https://ollama.com
2. Instala y ejecuta:
   ```cmd
   ollama serve
   ```
3. Descarga el modelo configurado:
   ```cmd
   ollama pull qwen3.5:4b
   ```

   O cualquier otro modelo que prefieras (edita `config.yaml` → `providers.ollama.model`).

---

## Modo A — Con Claude Code

### Cómo funciona

```
Claude Code CLI → stdio → src/server.py (FastMCP) → src/tools/* → AutoCAD Electrical
```

Claude envía llamadas MCP al servidor. El servidor ejecuta las tools directamente en AutoCAD via COM.

### Verificar que está registrado

El servidor ya está registrado en Claude Code (visible en esta sesión). Para confirmar:

```cmd
claude mcp list
```

Deberías ver `autocad-electrical` en la lista.

Si no aparece, registra manualmente:

```cmd
cd "\\data2\ENG_D\randy\randy dev\Nuevo\MCP AutoCAD"
claude mcp add autocad-electrical python -m src.server --cwd "\\data2\ENG_D\randy\randy dev\Nuevo\MCP AutoCAD"
```

### Cómo usar con Claude

1. Abre AutoCAD Electrical 2025
2. Abre un dibujo
3. En Claude Code, escribe instrucciones como:
   ```
   Dibuja una línea de 0,0 a 200,100 en el layer WIRES
   Inserta un contacto normalmente abierto WD_NOPEN en 50,150
   Lista todos los componentes del dibujo
   Genera el BOM del proyecto
   ```

Claude seleccionará automáticamente la herramienta MCP correcta y la ejecutará en AutoCAD.

### Arrancar el servidor MCP manualmente (para pruebas)

```cmd
cd "\\data2\ENG_D\randy\randy dev\Nuevo\MCP AutoCAD"
python -m src.server
```

El servidor arranca y espera conexiones via stdio. En modo normal, Claude Code lo lanza automáticamente.

---

## Modo B — Sin Claude (Interfaz Web + Ollama)

### Cómo funciona

```
Browser (localhost:8080) → FastAPI → Ollama → src/tools/* → AutoCAD Electrical
```

El usuario escribe instrucciones en lenguaje natural. Ollama interpreta y decide qué herramienta ejecutar. El resultado aparece en el chat.

### Arrancar la interfaz web

**Opción 1 — Doble clic:**
```
start_web.bat
```

**Opción 2 — Terminal:**
```cmd
cd "\\data2\ENG_D\randy\randy dev\Nuevo\MCP AutoCAD"
python start_web.py
```

**Opción 3 — Puerto personalizado:**
```cmd
python start_web.py --port 9090
```

**Opción 4 — Acceso desde red local:**
```cmd
python start_web.py --host 0.0.0.0 --port 8080
```

La interfaz se abre automáticamente en el navegador en `http://127.0.0.1:8080`.

### Descripción de la interfaz

| Sección | Función |
|---------|---------|
| **Topbar** | Estado en tiempo real: AutoCAD, Ollama, MCP, dibujo activo |
| **Selector de motor** | Cambiar entre Ollama, Claude, Groq, etc. sin reiniciar |
| **Panel Chat** | Escribir instrucciones en lenguaje natural |
| **Panel Tools** | Ver las 34 herramientas MCP disponibles, buscar, ejecutar |
| **Panel Logs** | Ver logs del sistema en tiempo real |
| **Panel Drawing** | Ver información del dibujo y proyecto activos |

### Ejemplo de uso

1. Abre AutoCAD Electrical 2025 con un dibujo
2. Ejecuta `start_web.bat`
3. En el chat, escribe:
   ```
   ¿Cuál es el dibujo activo?
   Dibuja una línea de 0,0 a 100,50
   Lista todos los componentes
   Genera el BOM en formato CSV
   ```

---

## Cambiar proveedor de IA

### Desde la interfaz web
Usa el selector en la barra superior derecha. Cambia entre Ollama, Claude, Groq, etc. en tiempo real.

### Desde la línea de comandos
```cmd
python scripts/switch_model.py --status
python scripts/switch_model.py -p ollama -m llama3.2:3b
python scripts/switch_model.py -p claude
```

### Editar config.yaml directamente
```yaml
active_provider: ollama   # cambia a: claude, openai, groq, lmstudio

providers:
  ollama:
    model: qwen3.5:4b     # cambia el modelo aquí
```

---

## Gestión de modelos Ollama

```cmd
# Ver modelos instalados
python scripts/ollama_manager.py list

# Buscar modelos disponibles
python scripts/ollama_manager.py search "coding"

# Descargar un modelo
python scripts/ollama_manager.py pull llama3.2:3b

# Ver modelos corriendo en GPU
python scripts/ollama_manager.py running

# Eliminar un modelo
python scripts/ollama_manager.py delete qwen3.5:4b
```

---

## Pruebas recomendadas

### Prueba 1 — Conexión AutoCAD

```cmd
cd "\\data2\ENG_D\randy\randy dev\Nuevo\MCP AutoCAD"
python scripts/test_connection.py
```

Resultado esperado:
```
✓ pywin32 disponible
✓ Conectado a AutoCAD Electrical 2025
✓ Dibujo activo: MiDibujo.dwg
✓ Comando de prueba ejecutado
```

### Prueba 2 — Tests unitarios

```cmd
python -m pytest tests/ -v --tb=short -m "not integration"
```

Resultado esperado: 41 tests pasando.

### Prueba 3 — Arranque del servidor MCP

```cmd
python -m src.server
```

Debe mostrar en consola:
```
[INFO] Starting autocad-electrical-mcp v1.0.0
[INFO] Active AI provider: ollama
[INFO] AutoCAD connection established (o: warning si no está abierto)
```

Detener con Ctrl+C.

### Prueba 4 — Verificar Ollama

```cmd
ollama list
curl http://localhost:11434/api/tags
```

O desde Python:
```cmd
python -c "import httpx; r=httpx.get('http://localhost:11434/api/tags'); print(r.status_code, r.json())"
```

### Prueba 5 — Interfaz web

```cmd
python start_web.py
```

Abrir `http://127.0.0.1:8080`. Verificar:
- Topbar muestra estado de AutoCAD y Ollama
- Panel Tools muestra las 34 herramientas
- Panel Logs muestra entradas del sistema
- Escribir "¿cuál es el dibujo activo?" en el chat

### Prueba 6 — Test de integración completo (requiere AutoCAD abierto)

```cmd
python -m pytest tests/ -v -m integration
```

### Prueba 7 — API directamente

Con el servidor web corriendo:
```cmd
# Estado del sistema
curl http://127.0.0.1:8080/api/status

# Lista de tools
curl http://127.0.0.1:8080/api/tools

# Chat (requiere Ollama corriendo)
curl -X POST http://127.0.0.1:8080/api/chat -H "Content-Type: application/json" -d "{\"message\": \"dibuja una linea de 0,0 a 100,50\"}"

# Ejecución directa de tool
curl -X POST http://127.0.0.1:8080/api/execute -H "Content-Type: application/json" -d "{\"tool\": \"get_active_drawing\", \"params\": {}}"
```

---

## Endpoints de la API web

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/` | Dashboard web (frontend) |
| GET | `/api/status` | Estado: AutoCAD, Ollama, MCP |
| GET | `/api/tools` | 34 herramientas agrupadas por categoría |
| GET | `/api/logs` | Logs del sistema (param: limit, min_level) |
| DELETE | `/api/logs` | Limpiar logs |
| GET | `/api/history` | Historial del chat |
| DELETE | `/api/history` | Limpiar historial |
| GET | `/api/drawing/info` | Dibujo activo + info del proyecto |
| GET | `/api/providers` | Proveedores configurados |
| POST | `/api/providers/switch` | Cambiar proveedor activo |
| POST | `/api/chat` | Enviar mensaje → IA → AutoCAD |
| POST | `/api/execute` | Ejecutar tool directamente (sin IA) |
| GET | `/api/docs` | Documentación Swagger de la API |

---

## Herramientas MCP disponibles (34 total)

### Drawing (5)
`draw_line`, `draw_circle`, `draw_arc`, `draw_text`, `draw_rectangle`

### Electrical (7)
`insert_electrical_symbol`, `insert_ladder`, `get_symbol_list`, `set_wire_number`, `insert_plc_module`, `create_cross_reference`, `edit_component_attributes`

### Wires (5)
`draw_wire`, `number_wires`, `get_wire_numbers`, `set_wire_attributes`, `create_wire_from_to`

### Components (6)
`get_component_list`, `get_component_info`, `update_component`, `delete_component`, `move_component`, `search_components`

### Reports (5)
`generate_bom`, `generate_wire_list`, `generate_terminal_plan`, `generate_plc_io_list`, `get_project_summary`

### Project (6)
`get_project_info`, `list_drawings`, `open_drawing`, `close_drawing`, `sync_project`, `get_active_drawing`

---

## Solución de problemas

### AutoCAD no se conecta

```
Error: Could not connect to AutoCAD
```

- Verifica que AutoCAD Electrical 2025 esté abierto
- Ejecuta `python scripts/test_connection.py`
- Verifica que pywin32 esté instalado: `pip show pywin32`

### Ollama no responde

```
Error: Cannot connect to Ollama at http://localhost:11434
```

- Ejecuta `ollama serve` en una terminal separada
- Verifica que el modelo esté instalado: `ollama list`
- Si el modelo no existe: `ollama pull qwen3.5:4b`

### El servidor MCP no arranca

```
ImportError: No module named 'mcp'
```

- Instala las dependencias: `pip install -e .`

### FastAPI no arranca

```
ModuleNotFoundError: No module named 'fastapi'
```

- Instala: `pip install fastapi "uvicorn[standard]"`

### Claude no ve las herramientas MCP

- Verifica el registro: `claude mcp list`
- Si no aparece, registra: `claude mcp add autocad-electrical python -m src.server --cwd "<ruta del proyecto>"`
- Verifica `mcp_config.json` tiene la ruta correcta en `cwd`

---

## Pendiente y mejoras futuras

| Característica | Estado | Prioridad |
|---|---|---|
| Interfaz web local (Modo B) | ✅ Implementado | — |
| Servidor MCP (Modo A con Claude) | ✅ Funcional | — |
| Multi-provider (Claude, Ollama, Groq...) | ✅ Completo | — |
| Streaming de respuestas en el chat web | ⏳ Pendiente | Media |
| Proveedor Gemini | ⏳ Pendiente | Baja |
| Descubrimiento dinámico de símbolos WD | ⏳ Pendiente | Media |
| Autenticación para acceso en red | ⏳ Pendiente | Baja |
| Modo VPS / acceso remoto | ⏳ Pendiente | Baja |
| Tests de integración completos (34 tools) | ⏳ Pendiente | Alta |

---

*Generado automáticamente — AutoCAD Electrical AI Control Center v1.0.0*
