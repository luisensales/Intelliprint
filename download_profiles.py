import os
import urllib.request
import shutil

os.makedirs('icc_profiles', exist_ok=True)

# URLs directas desde repositorios estables de código abierto
urls = {
    'sRGB2014.icc': 'https://raw.githubusercontent.com/saucecontrol/Compact-ICC-Profiles/master/profiles/sRGB-v4.icc',
    'ISOcoated_v2_300_bas.icc': 'https://raw.githubusercontent.com/quaeler/color-icc-profiles/master/profiles/cmyk/ISOcoated_v2_300_bas.icc'
}

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
}

print('Iniciando descarga de perfiles de color...')
for name, url in urls.items():
    try:
        path = os.path.join('icc_profiles', name)
        print(f'Descargando {name}...')
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req) as resp, open(path, 'wb') as out_file:
            shutil.copyfileobj(resp, out_file)
        print(f' Guardado exitosamente: {path}')
    except Exception as e:
        print(f'❌ No se pudo descargar {name}: {e}')

print('\nProceso finalizado. Archivos en icc_profiles/:')
for f in os.listdir('icc_profiles'):
    print(f' - {f}')
