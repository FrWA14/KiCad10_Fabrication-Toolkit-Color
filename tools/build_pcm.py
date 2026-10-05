"""Build the KiCad Plugin and Content Manager archive: out/fabrication-toolkit-color-<version>.zip

    python tools/build_pcm.py

Install: KiCad 10 > Plugin and Content Manager > Install from File...
"""
import json
import os
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    with open(os.path.join(ROOT, "metadata.json"), encoding="utf-8") as fh:
        meta = json.load(fh)
    ns = {}
    with open(os.path.join(ROOT, "plugins", "version.py"), encoding="utf-8") as fh:
        exec(fh.read(), ns)
    version = ns["VERSION"]
    meta["versions"][0]["version"] = version
    with open(os.path.join(ROOT, "metadata.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(meta, fh, indent=4, ensure_ascii=False)
    out = os.path.join(ROOT, "out", "fabrication-toolkit-color-{}.zip".format(version))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("metadata.json", json.dumps(meta, indent=4, ensure_ascii=False))
        z.write(os.path.join(ROOT, "resources", "icon.png"), "resources/icon.png")
        for base, dirs, files in os.walk(os.path.join(ROOT, "plugins")):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for name in files:
                if name.endswith(".pyc"):
                    continue
                path = os.path.join(base, name)
                z.write(path, os.path.relpath(path, ROOT).replace(os.sep, "/"))
        for name in ("LICENSE", "NOTICE"):
            z.write(os.path.join(ROOT, name), "plugins/" + name)
    print(out)


if __name__ == "__main__":
    main()
