# Live Studio

Integración de Home Assistant para un estudio local de streaming. **0.5.3 — versión
de desarrollo**, licencia MIT. Requiere Live Studio Engine 0.5.1 o posterior para editar cámaras durante la emisión.

## Qué incluye

- Crear y administrar varios lives independientes desde un solo motor.
- Asistente inicial de conexión por URL y token, sin YAML; se reutiliza para nuevos lives.
- Nombre propio,1–8 fuentes de cámara y0–8 sensores opcionales por live.
- Menús de cámaras, vídeo/música, textos y selección automática.
- Selector manual/automático con cambios de cámara sin reiniciar música ni salida.
- Sensores de cámara actual, vídeo reciente, estado y decisión de selección.
- Cámaras de instantáneas por fuente y vista actual, sin imágenes antiguas tras fallos.
- Cinco ajustes numéricos para margen, preferencia diurna, permanencia, intervalo
  y confirmaciones; textos editables para título, marquesina y CTA.
- Botones compactos de vista previa, detener y comparar vistas ahora.
- IA opcional mediante un proveedor existente de LLM Vision, local o cloud.
- Español e inglés; actualización local cada 15 segundos.

## Instalar

1. Instalar **Live Studio Engine** desde el repositorio de apps
   `https://github.com/tuxevil/home-assistant` y configurar su token API.
2. Dejar el destino vacío para probar. Actualizar el motor antes que la integración.
3. Añadir `tuxevil/ha-live-studio` en HACS como repositorio personalizado de tipo
   **Integración**, descargar y reiniciar Home Assistant.
4. Ajustes → Dispositivos y servicios → Añadir integración → **Live Studio**.
5. Indicar dirección interna del motor y token. En Opciones, añadir cámaras,
   carpeta MP3, vídeo y textos. Grabar primero una vista previa local.

Alternativa manual: copiar `custom_components/live_studio/` a la carpeta
`custom_components/` de Home Assistant y reiniciar. La integración no incluye
FFmpeg dentro del Core ni instala el motor por sí sola.

[Documentación completa y selección automática](https://github.com/tuxevil/home-assistant/blob/main/live_studio/DOCS.md).
[Verificación previa a una migración](https://github.com/tuxevil/home-assistant/blob/main/live_studio/MIGRATION.md).
No está incluida en el catálogo predeterminado de HACS.

## Uso y automatizaciones

Añadir al dashboard entidades del dispositivo Live Studio. Los identificadores
exactos dependen del registro de cada instalación. Los textos aceptan la acción
`text.set_value`; las reglas usan `number.set_value` y la cámara `select.select_option`.
El sensor de cámara actual incluye `camera_entity` para asociarlo con automatizaciones
propias. La cámara de vista actual y el binario de vídeo permiten validar frescura.

La lista de sensores se elige por live en Opciones → Live y sensores. Puede quedar
vacía; solo se omiten las lecturas no disponibles. Las líneas largas se desplazan.
Las imágenes de comparación se envían al proveedor de LLM Vision elegido: revisar
su privacidad y costes. Sin habilitar IA, el cambio manual y la recuperación por
fallo funcionan de forma local. No se requiere ninguna cuenta de Live Studio.

Detener antes de modificar conexiones o codificación. El motor continúa al reiniciar
Home Assistant o descargar la integración. Detener explícitamente antes de retirarlo.

No incluye editor gráfico, GPU, OAuth/Analytics de YouTube ni WhatsApp. Esos módulos
pueden convivir con Live Studio mediante entidades; no se migran automáticamente.
Mínimo Home Assistant 2026.10.0; verificado con 2026.10.1.

## Crear y manejar cada live

Ajustes → Integraciones → Live Studio → Añadir entrada → Crear un live. Elegir el
motor existente, nombre, una o varias fuentes y sensores opcionales. El live se
crea detenido y sin destino. Si no hay fuentes, el asistente pide la primera URL
RTSP. En Opciones se agregan otras fuentes o se seleccionan las ya configuradas.

Cada entrada y dispositivo tienen controles, selección de cámara, textos, reglas,
música y destino propios. En Destino de emisión se introduce su URL privada con
clave; no se expone en diagnósticos ni se copia a las opciones de HA. Iniciar,
detener o eliminar un live no modifica otro. Para borrar debe estar detenido y
confirmarse la acción. La app completa sigue siendo un punto común: reiniciarla
interrumpe todas sus salidas. No hace falta una app adicional por cada live.

Las entidades y el sensor único de0.2 migran sin perder sus IDs: aquel sensor pasa a
una lista de un elemento. Un live puede tener una lista vacía. La opción nativa
Reconfigurar permite reconectar un live migrado a otro motor solo si conserva su
identidad; no permite sustituirlo accidentalmente por otro live.

## Local or external engine

The companion can run as an HAOS app or on an external Linux machine/container. The same integration controls either through its authenticated HTTP API. No Proxmox or GPU is required. Preserve engine/profile identities when relocating existing entries and use Reconfigure to change their endpoint. Never run two senders with the same ingest key.

Video options select CPU, VAAPI or automatic encoder/decoder, an optional render device and a bounded camera buffer. CPU is the default; explicit VAAPI requires a working device. Automatic mode reports its selected backend/fallback. VAAPI support depends on the host driver and codecs; test actual inputs.

### Overlay editor (engine0.5.0+)

The integration includes a Lovelace card; no separate frontend repository or
manual resource registration is needed. Add a custom card with this configuration
and select the status entity belonging to the live you want to edit:

```yaml
type: custom:live-studio-overlay-card
entity: sensor.live_studio_engine_status
```

The card groups controls by element and includes quick camera/date/time
visibility switches. Configure the top/bottom information bar, placement, offsets,
font size, scrolling speed/direction, foreground/background colors, opacity,
shadows, date/time formats and CTA timing. Changes apply to that live without
restarting its encoder or music. Font sizes, offsets and speeds scale from a
1080p reference. Editing requires a Home Assistant administrator. Text remains
literal and engine credentials are never sent to the browser.

Each live also exposes an **Overlay preview** camera showing a fresh composed
JPEG. Add it as a normal picture-entity card, or set `preview: true` on the editor
card. With an existing browser tab, refresh once after upgrading to load the card.

## Cámaras de cada live

Añade una tarjeta al dashboard, usando el sensor de estado del live correspondiente:

```yaml
type: custom:live-studio-cameras-card
entity: sensor.live_studio_engine_status
```

La lista descubre automáticamente las entidades de cámara de la integración
**Frigate** instalada en Home Assistant, con sus nombres y fuentes RTSP. Marca o
desmarca las que quieras y pulsa **Guardar cámaras**. Cada directo mantiene su
propia selección. Las cámaras retiradas permanecen en la biblioteca del motor.
**Otra fuente (avanzado)** permite registrar una fuente ajena a Frigate mediante nombre
y dirección privada. Los nombres deben ser únicos dentro de un live; al importar
nombres repetidos se añade un sufijo. Se admiten entre1 y8 fuentes.

Requiere usuario administrador. La tarjeta recibe nombres e identificadores opacos;
las direcciones RTSP y el token del motor no se devuelven al navegador. La emisión
y la música continúan al cambiar la lista. Si retiras la cámara activa, se elige
otra fuente del mismo live; una fuente nueva puede tardar en entregar vídeo.
Los cambios de resolución, FPS y codificación siguen requiriendo detener la salida.

El descubrimiento utiliza la API de cámaras de Home Assistant y respeta las
plantillas RTSP de Frigate. Para un motor externo, reutiliza el origen RTSP ya
configurado para la misma instancia de Frigate; así evita enviar nombres DNS
internos de apps al servidor externo. No abre decodificadores para cámaras
desmarcadas. Las entidades deshabilitadas o sin una fuente RTSP disponible no
se ofrecen como fuentes reproducibles. Frigate es opcional; las fuentes
registradas manualmente siguen disponibles cuando no está instalado.

Cada live puede definir su tema y criterios en Opciones → Selección automática →
**Tema y criterios visuales del live**. Por ejemplo, un canal de animales puede
priorizar animales visibles y encuadre antes que un paisaje vacío. Si se deja
vacío se conservan los criterios de paisaje. El proveedor y modelo siguen siendo
opcionales e independientes para cada live.

### Camera sidebar

Engine 0.6.0 adds an optional Camera sidebar switch and Thumbnail refresh interval per live. Controls apply while broadcasting, without restarting audio or the encoder. The sidebar reuses existing decoded camera frames at a default interval of three seconds. Supported output: 1920×1080. Turn the switch off to return to full screen.
