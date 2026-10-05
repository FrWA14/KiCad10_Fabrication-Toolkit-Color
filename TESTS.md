# Tests

## Lancer

```bash
# Cartes T1..T7 et images de test (Python de KiCad, pcbnew + Pillow)
"C:\Program Files\KiCad\10.0\bin\python.exe" tests/make_boards.py

# Unitaires : Python de KiCad ET Python système (avec cryptography : interop OAEP en plus)
cd tests
"C:\Program Files\KiCad\10.0\bin\python.exe" -m unittest test_unit test_parity test_integration
python -m unittest test_unit

# Matrice carte × image par la CLI réelle (met à jour le tableau ci-dessous)
"C:\Program Files\KiCad\10.0\bin\python.exe" tests/run_matrix.py

# Boîte de dialogue wx hors KiCad (contrôles + options transmises)
"C:\Program Files\KiCad\10.0\bin\python.exe" tests/ui_smoke.py
```

Les tests sont écrits avec `unittest` (pytest n'est pas installé). `pytest -q tests/` les découvre aussi.

Sorties : `out/matrix/<cas>/{report.json, color_silkscreen.log, svg/, production/}` et `out/matrix.json`.
Le dossier `svg/` contient les SVG en clair (option `--debugSvg`). On peut les ouvrir dans un navigateur pour vérifier le rendu.

## Dernier passage (5 octobre 2026, KiCad 10.0.4, Windows 11)

| Suite | Interpréteur | Résultat |
|---|---|---|
| `test_unit` (32 tests) | KiCad 3.11 | OK (1 test sauté : interop `cryptography`, absent) |
| `test_unit` (32 tests) | Système 3.14 | OK |
| `test_parity` (6 tests, TransJLC 0.4.0 + patch debug) | KiCad 3.11 | OK |
| `test_integration` (matrice + non-régression T2/T5 contre FT d'origine) | KiCad 3.11 | OK |
| `ui_smoke.py` | KiCad 3.11 | OK |

### Matrice (générée par `tests/run_matrix.py`)

<!-- matrix:start -->
| Cas | Carte | Image dessus | Image dessous | Options | Attendu | Obtenu | Avertissements | Résultat |
|---|---|---|---|---|---|---|---|---|
| T1-top | T1 | logo.png | — | — | ok | ok | — | ✅ |
| T1-none | T1 | — | — | — | ok | ok | — | ✅ |
| T1-tiny | T1 | tiny.png | — | — | error / E_IMAGE_TOO_SMALL | error / E_IMAGE_TOO_SMALL | — | ✅ |
| T1-bmp | T1 | bad.bmp | — | — | error / E_IMAGE_FORMAT | error / E_IMAGE_FORMAT | — | ✅ |
| T1-missing | T1 | nope.png | — | — | error / E_IMAGE_MISSING | error / E_IMAGE_MISSING | — | ✅ |
| T2-both | T2 | logo.png | photo.jpg | — | ok | ok | — | ✅ |
| T2-transjlc | T2 | logo.png | photo.jpg | --colorProfile transjlc | ok | ok | — | ✅ |
| T3-alpha | T3 | alpha.png | — | — | ok | ok | — | ✅ |
| T4-auxorigin | T4 | logo.png | — | — | ok | ok | — | ✅ |
| T5-4layers | T5 | — | photo.jpg | — | ok | ok | — | ✅ |
| T6-no-outline | T6 | logo.png | — | — | error / E_OUTLINE_MISSING | error / E_OUTLINE_MISSING | — | ✅ |
| T7-huge | T7 | huge.png | — | — | ok | ok | W_IMAGE_RESAMPLED | ✅ |
| T7-contain | T7 | logo.png | — | --colorFit contain | ok | ok | W_IMAGE_PADDED | ✅ |
<!-- matrix:end -->

## Couverture du §6.3 du brief

| # | Vérification | Où |
|---|---|---|
| 1 | Noms de fichiers (Protel en entrée, EasyEDA en sortie) | `JlcConvertTests`, `run_matrix` (contenu du ZIP) |
| 2 | Contenu du ZIP selon les images | `run_matrix` (FCTS/FCBS/FCBO/FCBM, couches internes T5) |
| 3 | Structure binaire : taille = 512 + len(SVG) + 16 | `GenerateTests.test_full_set_and_round_trip`, `test_parity.test_encrypted_sizes`, contrôle à l'exécution dans `generate.py` |
| 4 | Aller-retour avec une clé RSA 2048 de test | `CryptoTests.test_envelope_round_trip_with_test_key`, `GenerateTests` (déchiffre les 3 fichiers) |
| 5 | Parité TransJLC (SVG en clair) | `test_parity` : SVG identiques octet pour octet hors chemins de masque (voir constat 1) ; FCBM et Gerbers identiques hors date et ouverture « hash » |
| 6 | SVG valide, image à la bonne place | `SvgTests` : l'image couvre exactement le contour, le dessous est en miroir double. Contrôle visuel dans un navigateur sur T2 (ouvertures rectangle, rond, RoundRect, ovale aux bonnes positions) |
| 7 | Fichier de marquage parsable, 3 repères à 0,0762 mm à l'intérieur | `MarkerTests` (relu par le parseur Gerber du module) |
| 8 | Tolérance 2 mm | étape `board_vs_gerber` (contour pcbnew contre Gerber) et `svg_*.gerber_delta_mm` ; `test_board_mismatch_over_2mm` |
| 9 | Non-régression sans image | `test_no_image_identical_to_upstream` : ZIP, BOM, CPL et netlist identiques à FT d'origine (T2, T5) |

## Constats

1. **Bug de TransJLC 0.4.0 : ouvertures de masque fausses.** TransJLC ajoute des préfixes `G54` aux sélections d'ouverture, puis relit le masque modifié. Son parseur (`gerber_parser`) ignore `G54Dnn` et retombe sur l'ouverture de plus grand numéro, c'est-à-dire l'ouverture « hash » aléatoire de 0,0x mm qu'il vient d'ajouter. Résultat : toutes les ouvertures font environ 0,07 mm, et l'image couleur est imprimée sur les pastilles. Le profil `default` lit les vraies formes. Le profil `transjlc` reproduit le bug volontairement, pour la parité.
2. **Repères d'alignement.** TransJLC (et Overprint) placent les repères à 0,0762 mm du bord. Dans l'exemple EasyEDA authentique (données de test de TransJLC), l'attribut `mark-points` vaut 3 unités de 10 mil, soit 0,762 mm. On a gardé 0,0762 mm, cohérent avec le `.FCBM` de TransJLC. Réglable par `Options.mark_inset_mm`. **[À VÉRIFIER chez JLCPCB]**
3. **Repère du `.FCBO`.** TransJLC écrit le contour couleur avec Y non inversé (viewBox `x, min_y`), alors que `.FCTS` et `.FCBS` utilisent Y inversé. Le profil `default` met `.FCBO` dans le même repère que `.FCTS` (comme Overprint) ; le profil `transjlc` garde la version de TransJLC. **[À VÉRIFIER]**
4. **Type MIME.** TransJLC écrit `data:image/jpg` (dérivé de l'extension). Le profil `default` écrit `image/jpeg` ou `image/png` d'après le contenu, comme dans l'exemple EasyEDA.
5. **Contours avec arcs.** TransJLC ne prend que les extrémités des arcs. Le profil `default` ajoute les extrema des arcs (contour circulaire ou bombé).
6. **`.FCBM` au format `%FSLAX25Y25%`** : 2 chiffres entiers ne suffisent pas pour des coordonnées ≥ 100 mm. On garde ce format (identique à TransJLC et Overprint) ; les lecteurs Gerber divisent l'entier par 10⁵ de toute façon.
7. **KiCad 10.0.4 : champ masque non déterministe dans l'IPC-D-356.** Sur les enregistrements VIA de `netlist.ipc`, ce champ change à chaque export, avec FT d'origine aussi. La comparaison de non-régression l'ignore.
8. **Fichiers abandonnés** en mode couleur : les cartes de perçage `*-drl_map.gbr` (comme TransJLC). Sans image, rien ne change.

## Validation manuelle chez JLCPCB (à faire par l'utilisateur)

Procédure : README, section « Valider chez JLCPCB ». Reporter ici les messages exacts.

| Date | Carte / ZIP | Profil | Options JLCPCB | Gerber Viewer (couleur visible ?) | Message / erreur exacte | Commande / rendu physique |
|---|---|---|---|---|---|---|
| | T2 (`out/matrix/T2-both/production/T2-both.zip`) | default | blanc, ENIG, 1 oz, EasyEDA multi-color silkscreen | | | |
| | T2 (`out/matrix/T2-transjlc/production/T2-transjlc.zip`) | transjlc | idem | | | |
