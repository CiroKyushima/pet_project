#!/usr/bin/env python3
# =====================================================================
#  ota_manifest.py  -  Gera o version.json da atualização do Puma (OTA).
#
#  Normalmente quem roda isto é a GitHub Action (.github/workflows/ota-release.yml),
#  sozinha, quando você publica uma Release. Dá para rodar no computador também:
#
#    python tools/ota_manifest.py puma_virtual_cat_IA/build/esp32.esp32.esp32s3/puma_virtual_cat_IA.ino.bin --repo SEU_USUARIO/pet_project
#
#  e depois anexar o version.json na Release junto com o .bin.
#
#  O que ele faz:
#   - acha, entre os .bin passados, o firmware do Puma (o que tem "PUMA_FW_VERSION=" dentro;
#     ignora o merged, o bootloader e o partitions);
#   - lê a versão DE DENTRO do .bin (assim o version.json nunca mente a versão);
#   - confere se a tag da Release bate com essa versão (ex.: tag v1.0.1 <-> FW_VERSION "1.0.1");
#   - calcula o tamanho e o SHA-256 (a "impressão digital" que o pet confere depois de baixar);
#   - escreve o version.json.
#  Só usa a biblioteca padrão do Python 3 (nada para instalar).
# =====================================================================
import argparse
import hashlib
import json
import os
import re
import sys
import urllib.parse

MARK = b"PUMA_FW_VERSION="           # (veja version.h e ota.cpp)
APP_ID = "puma_virtual_cat_IA"       # (FW_APP_ID no version.h)
SLOT_SIZE = 0x300000                 # cada metade do programa tem 3 MB ("16M Flash (3MB APP/9.9MB FATFS)")
NOTES_MAX = 150                      # o pet mostra as novidades num cartão pequeno


def fail(msg):
    print("ERRO: " + msg, file=sys.stderr)
    sys.exit(1)


def firmware_version(data):
    i = data.find(MARK)
    if i < 0:
        return None
    j = data.find(b";", i, i + 64)
    if j < 0:
        return None
    v = data[i + len(MARK):j].decode("ascii", "replace")
    return v if re.fullmatch(r"\d+\.\d+\.\d+", v) else None


def is_merged(data):                 # o .merged.bin tem bootloader + tabela de partições + app (não serve para OTA)
    return len(data) > 0x8002 and data[0x8000:0x8002] == b"\xaa\x50"


def clean_notes(text):
    text = re.sub(r"[*`>_]+", "", text or "")          # tira a formatação do Markdown das notas da Release
    text = "".join(c for c in text if ord(c) <= 0xFFFF and c != "\ufe0f")   # sem emojis (a fonte do pet não tem)
    items = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):           # títulos ("## Novidades": o pet já escreve "Novidades:")
            continue
        line = re.sub(r"^([-+]|\d+[.)])\s+", "", line)  # marcadores de lista
        items.append(" ".join(line.split()))
    text = "; ".join(items)                            # um item da lista depois do outro
    return text if len(text) <= NOTES_MAX else text[:NOTES_MAX - 3].rstrip() + "..."


def main():
    ap = argparse.ArgumentParser(description="Gera o version.json da atualização do Puma.")
    ap.add_argument("bins", nargs="+", help="arquivo(s) .bin (o certo é escolhido sozinho)")
    ap.add_argument("--repo", help="usuario/repositorio do GitHub (para montar o link do .bin)")
    ap.add_argument("--tag", help="tag da Release (padrão: v + versão do firmware)")
    ap.add_argument("--url", help="link do .bin (se não for numa Release do GitHub)")
    ap.add_argument("--notes", default="", help="novidades (texto curto)")
    ap.add_argument("--notes-file", help="arquivo com as novidades (ex.: a descrição da Release)")
    ap.add_argument("--out", default="version.json", help="arquivo de saída (padrão: version.json)")
    a = ap.parse_args()

    found = []
    for path in a.bins:
        with open(path, "rb") as f:
            data = f.read()
        if not data or data[0] != 0xE9 or is_merged(data):
            continue                 # não é a imagem do aplicativo
        v = firmware_version(data)
        if v:
            found.append((path, data, v))
    if not found:
        fail("nenhum .bin do Puma encontrado. Use o arquivo .ino.bin exportado pela Arduino IDE "
             "(não o .merged.bin, .bootloader.bin ou .partitions.bin) de um firmware com o ota.cpp.")
    if len(found) > 1:
        fail("mais de um firmware do Puma: " + ", ".join(p for p, _, _ in found) + ". Deixe só um.")
    path, data, version = found[0]

    tag = a.tag or ("v" + version)
    if tag.lstrip("vV") != version:
        fail(f"a tag da Release é '{tag}', mas o firmware diz que é a versão {version}. "
             f"Você esqueceu de mudar FW_VERSION no version.h? (o .bin precisa ser exportado DEPOIS de mudar)")
    if len(data) > SLOT_SIZE:
        fail(f"o firmware tem {len(data)} bytes e não cabe na metade de {SLOT_SIZE} bytes da placa.")

    if a.url:
        url = a.url
    elif a.repo:
        url = "https://github.com/{}/releases/download/{}/{}".format(
            a.repo.strip("/"), urllib.parse.quote(tag), urllib.parse.quote(os.path.basename(path)))
    else:
        fail("diga --repo usuario/repositorio (ou --url com o link do .bin).")

    notes = a.notes
    if a.notes_file and os.path.exists(a.notes_file):
        with open(a.notes_file, encoding="utf-8", errors="replace") as f:
            notes = f.read()
    manifest = {
        "app": APP_ID,
        "version": version,
        "url": url,
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "notes": clean_notes(notes),
    }
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"{a.out} criado: versão {version}, {len(data)} bytes ({os.path.basename(path)})")
    print(f"  link: {url}")


if __name__ == "__main__":
    main()
