# Live Studio

Integración de Home Assistant para un estudio local de streaming. **0.1.0 — versión
de desarrollo**, licencia MIT. Controla el motor independiente Live Studio Engine.

## Qué incluye

- Asistente de conexión por URL y token, sin YAML.
- Opciones para una cámara RTSP, música, codificación y elementos en pantalla.
- Interruptor de emisión, botones de vista previa y detener.
- Entidades de texto para título, marquesina y CTA.
- Sensor de estado; sensor de Home Assistant seleccionable para mostrar su valor.
- Español e inglés; actualización local cada 15 segundos.

## Instalar

1. Instalar **Live Studio Engine** desde el repositorio de apps
   `https://github.com/tuxevil/home-assistant` y seguir su documentación.
2. Configurar su token API y arrancar el motor, dejando vacío el destino para probar.
3. Añadir `tuxevil/ha-live-studio` en HACS como repositorio
   personalizado de tipo **Integración**, descargar y reiniciar Home Assistant.
4. Ajustes → Dispositivos y servicios → Añadir integración → **Live Studio**.
5. Indicar dirección interna del motor y token. Abrir **Opciones** para configurar
   RTSP, carpeta MP3, textos y sensor. Probar primero la grabación local.

Alternativa manual de desarrollo: copiar `custom_components/live_studio/` a la
carpeta `custom_components/` de Home Assistant y reiniciar. Esta integración no
instala el motor ni incluye FFmpeg dentro del proceso de Home Assistant.

[Documentación del motor y sus opciones](https://github.com/tuxevil/home-assistant/blob/main/live_studio/DOCS.md).
No está incluida en el catálogo predeterminado de HACS: eso requiere publicación,
validación y, si se solicita, revisión independiente por HACS.

## Uso y automatizaciones

Añadir al dashboard las entidades del dispositivo Live Studio. Los identificadores
exactos dependen del idioma, registro y otras instalaciones del usuario. Los textos
se pueden actualizar con la acción nativa `text.set_value`; así una automatización
propia puede enviar el título de un nuevo vídeo o cualquier otro mensaje.

Las opciones permiten elegir un sensor, cuya información se oculta cuando no está
disponible o deja de actualizarse. Los textos vacíos se ocultan. Detener antes de
cambiar parámetros de vídeo. El motor sigue funcionando al reiniciar Home Assistant.

Para retirar el sistema, detener la salida y después quitar integración y motor.
No se detiene una emisión simplemente al descargar la integración del Core.

## Alcance de esta versión

Una fuente RTSP, un sensor, H.264 por CPU, música en bucle y elementos de texto.
No incluye editor gráfico, logo configurable, escenas múltiples, cambio de cámara
sin cortes, IA, OAuth de YouTube, Analytics ni WhatsApp. Son módulos futuros, no
requisitos para instalar las funciones básicas. No migra configuraciones existentes.

Home Assistant mínimo declarado 2026.10.0; verificado con 2026.10.1.
La carga de codificación se mide por separado en el motor.
