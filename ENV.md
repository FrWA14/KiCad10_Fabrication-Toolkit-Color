# Environnement de développement

Relevé automatique le 5 octobre 2026.

| Élément | Valeur |
|---|---|
| OS | Windows 11 Pro 10.0.26200 |
| `kicad-cli version` | 10.0.4 |
| Python de KiCad | `C:\Program Files\KiCad\10.0\bin\python.exe` (3.11.5) |
| `import pcbnew` (Python de KiCad) | OK, `GetBuildVersion()` = 10.0.4 : l'API SWIG est toujours fournie |
| wxPython (Python de KiCad) | 4.2.2 msw, wxWidgets 3.3.2 |
| Pillow (Python de KiCad) | 12.2.0 |
| `cryptography` (Python de KiCad) | **absent** → moteurs OpenSSL via ctypes et Python pur |
| OpenSSL embarqué (module `ssl`) | 3.6.0 : utilisé par le moteur AES-GCM `openssl` |
| `cairosvg` | absent (les deux Python) → vérification SVG structurelle et visuelle (navigateur) |
| Python système | 3.14.7 (avec `cryptography`, Pillow ; sans pytest) |
| Rust / cargo | rustc 1.98.1 / cargo 1.98.1 (TransJLC compilé pour les tests de parité) |
| Dossier des plugins KiCad 10 | `C:\Users\frwa3\Documents\KiCad\10.0\scripting\plugins` (vide) ; les paquets PCM vont dans `...\10.0\3rdparty\plugins` |

## Réponses aux questions ouvertes du brief (§3)

1. **`pcbnew` sous KiCad 10** : disponible (SWIG). L'API IPC (`kipy`) n'est pas nécessaire. Le paquet `kipy` n'est d'ailleurs pas installé.
2. **Fabrication Toolkit sous KiCad 10** : la version `7f627b6b` fonctionne telle quelle (CLI testée sur T1 à T7). Elle prend déjà en charge KiCad 10 (`utils.is_v10`).
3. **Chiffrement** : `cryptography` est absent du Python de KiCad. Trois moteurs AES-128-GCM (nonce 16 octets) sont essayés dans l'ordre : `cryptography`, puis OpenSSL via ctypes, puis Python pur (≈ 1 Mo/s). Tous trois reproduisent le vecteur de test EasyEDA de TransJLC. RSA-OAEP-SHA256 est en Python pur, avec `pow` natif.
4. **Nommage** : les noms de TransJLC et d'Overprint concordent : `Fabrication_ColorfulBoardOutlineLayer.FCBO` et `Fabrication_ColorfulBoardOutlineMark.FCBM`. Ce que JLCPCB accepte réellement reste à confirmer (voir TESTS.md, validation manuelle).
5. **Cadre** : voir README, section « Avertissement ».

## Dépôts de référence (`ref/`, non versionné)

```bash
git clone https://github.com/bennymeg/Fabrication-Toolkit.git ref/Fabrication-Toolkit
git clone https://github.com/HalfSweet/TransJLC.git ref/TransJLC
git clone https://github.com/Dirdmaster/overprint.git ref/overprint
git -C ref/TransJLC apply ../../tests/transjlc_debug_svg.patch
cargo build --release --manifest-path ref/TransJLC/Cargo.toml
```
