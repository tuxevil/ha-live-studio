# Live Studio

Integración de Home Assistant para un estudio local de streaming. **0.2.0 — versión
de desarrollo**, licencia MIT. Requiere Live Studio Engine 0.2.0 o posterior.

## Qué incluye

- Asistente de conexión por URL y token, sin YAML.
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

El sensor de información se elige en Opciones y se oculta si deja de estar disponible.
Las imágenes de comparación se envían al proveedor de LLM Vision elegido: revisar
su privacidad y costes. Sin habilitar IA, el cambio manual y la recuperación por
fallo funcionan de forma local. No se requiere ninguna cuenta de Live Studio.

Detener antes de modificar conexiones o codificación. El motor continúa al reiniciar
Home Assistant o descargar la integración. Detener explícitamente antes de retirarlo.

No incluye editor gráfico, GPU, OAuth/Analytics de YouTube ni WhatsApp. Esos módulos
pueden convivir con Live Studio mediante entidades; no se migran automáticamente.
Mínimo Home Assistant 2026.10.0; verificado con 2026.10.1.
