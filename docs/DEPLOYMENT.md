# Despliegue aislado (pendiente de acceso)

No se ha intervenido el VPS. La clave local disponible fue rechazada para root y monitor.
No usar la contraseña expuesta; debe rotarse. No copiar claves al repositorio.

Antes de desplegar, con un acceso válido y preferiblemente un usuario restringido:

1. Inventariar SO, espacio, procesos, unidades systemd, contenedores, puertos y configuración del proxy existente. No editar rutas, firewall, VPN, WireGuard, MikroTik ni túneles.
2. Crear snapshot del proveedor y respaldo verificable de las configuraciones que se vayan a modificar, con permisos 0600. Inventariar los respaldos y probar su lectura/restauración en ubicación aislada.
3. Verificar que 18081 esté libre. Crear un directorio y usuario exclusivos para PreDice. Docker es requisito: no instalarlo ni cambiar su configuración sobre el servidor sin evaluar sus efectos sobre la red existente.
4. Establecer PREDICE_TOKEN como secreto fuera del repositorio. Ejecutar `docker compose -p predice up -d --build`. El proceso del contenedor usa UID 10001 y solo publica loopback.
5. Configurar un hostname HTTPS dedicado mediante el proxy existente solo después del respaldo. Mantener autorización Bearer en HTTP y WebSocket, límites de peticiones y TLS. No publicar 18081 al exterior.
6. Verificar /health, API con token, WebSocket y logs. Primera carga: ~56 días por activo. Revisar calidad y disponibilidad de datos antes de usar señales.
7. Respaldar SQLite mediante la API de backup de SQLite (no copiar solo el .db mientras hay WAL activo). Conservar volumen y snapshots.

Rollback: `docker compose -p predice down` sin `-v`; conserva los datos. Restaurar únicamente el bloque del proxy que se haya cambiado. Nunca ejecutar prune global ni detener servicios ajenos.

La API es de un único usuario; no ofrece aislamiento multiusuario. Configurar el HTTPS y token en Ajustes de Android. El APK debug es instalable para pruebas; producción requiere firma de distribución propia.
