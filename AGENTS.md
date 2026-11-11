# Flujo de trabajo del proyecto

El usuario quiere que los cambios de IntelliPrint se suban siempre a GitHub después de verificarlos.

- Ejecutar las comprobaciones adecuadas a los cambios, crear un commit descriptivo y publicar en el remoto `origin` de la rama de trabajo.
- Comprobar el estado remoto y conservar los cambios ajenos. Usar un push normal, sin reescribir el historial publicado.
- Excluir credenciales, archivos de clientes, trabajos temporales y resultados de pruebas del commit.
- Verificar que el commit local está en GitHub antes de dar la publicación por terminada. Indicar cualquier bloqueo concreto.
- Subir a GitHub no acredita por sí solo que el despliegue web haya terminado.

Comprobaciones disponibles:

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -q
node --test tests/frontend.test.cjs tests/issue_viewer.test.cjs
git diff --check
```
