# Tests

## Lancer

```bash
# Cartes T1..T7 et images de test (Python de KiCad, pcbnew + Pillow)
"C:\Program Files\KiCad\10.0\bin\python.exe" tests/make_boards.py

# Unitaires : Python de KiCad ET Python système (avec cryptography : interop OAEP en plus)
cd tests
"C:\Program Files\KiCad\10.0\bin\python.exe" -m unittest test_unit test_placement test_parity test_integration
python -m unittest test_unit test_placement

# Matrice carte × image par la CLI réelle (met à jour le tableau ci-dessous)
"C:\Program Files\KiCad\10.0\bin\python.exe" tests/run_matrix.py

# Boîte de dialogue wx hors KiCad (contrôles + options transmises)
"C:\Program Files\KiCad\10.0\bin\python.exe" tests/ui_smoke.py

# Éditeur de placement, hors écran : déplacer / redimensionner / rotation / champs, rendu des deux vues
# dans out/placement/editor_*.png (rendu en mémoire, aucune capture d'écran) et composition 1200 DPI
"C:\Program Files\KiCad\10.0\bin\python.exe" tests/placement_smoke.py [carte.kicad_pcb] [dessus.png] [dessous.jpg]
```

Les tests sont écrits avec `unittest` (pytest n'est pas installé). `pytest -q tests/` les découvre aussi.

Sorties : `out/matrix/<cas>/{report.json, color_silkscreen.log, svg/, production/}` et `out/matrix.json`.
Le dossier `svg/` contient les SVG en clair (option `--debugSvg`). On peut les ouvrir dans un navigateur pour vérifier le rendu.

## Dernier passage (6 octobre 2026, KiCad 10.0.4, Windows 11)

| Suite | Interpréteur | Résultat |
|---|---|---|
| `test_unit` (32 tests) | KiCad 3.11 | OK (1 test sauté : interop `cryptography`, absent) |
| `test_unit` (32 tests) | Système 3.14 | OK |
| `test_parity` (6 tests, TransJLC 0.4.0 + patch debug) | KiCad 3.11 | OK |
| `test_integration` (matrice + non-régression T2/T5 contre FT d'origine) | KiCad 3.11 | OK |
| `test_placement` (7 tests : cadrage, découpe contour + découpe interne, position, miroir, rotation) | KiCad 3.11 et système 3.14 | OK |
| `ui_smoke.py` | KiCad 3.11 | OK |
| `placement_smoke.py` (T2 et copie de la carte RP2350 de l'utilisateur) | KiCad 3.11 | OK |

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
| T3-placement | T3 | logo.png (placé) | photo.jpg (placé, 90°) | --placement AUTO | ok | ok | — | ✅ |
| T2-silk-only | T2 | — | — | --topSilkColor #C0392B | ok | ok | — | ✅ |
| T5-calibration | T5 | — | — | --calibration --bottomOffset=-0.3,0 | ok | ok | W_CALIBRATION | ✅ |
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

9. **Retour JLCPCB du 6 octobre 2026 (ZIP RP2350, profil default 0.2.2).** Fichiers couleur **reconnus** : l'option
   *EasyEDA multi-color silkscreen* apparaît, mais grisée, avec le message : *« The multi-color silkscreen file is
   outdated. Please update to EasyEDA version V3.2.135 or later and re-export the Gerber file for the multi-color
   silkscreen. »* Le chiffrement et la structure sont donc acceptés ; un contrôle de version bloque. Deux marqueurs
   possibles, maintenant réglables (`--easyedaVersion`, `--edaVersion`) : l'en-tête Gerber `EasyEDA Pro v2.2.42.2` et
   l'attribut SVG `eda-version="1.6(2025-08-27)"`. Depuis la 0.2.3, valeurs par défaut `3.2.148` et `2.4(2026-05-08)`
   (Overprint). Variantes à tester : `out/jlc_tests/RP2350_test_{A,B,C}.zip` (A : Gerber 2.2.42.2 + SVG 2.4 ;
   B : Gerber 3.2.148 + SVG 1.6 ; C : Gerber 3.2.148 + SVG 2.4).
   **Résultat : C est accepté** (option sélectionnable, aperçu couleur correct dans le Gerber Viewer). A et B
   n'ont pas été testés : on ne sait pas lequel des deux marqueurs est contrôlé, mais les valeurs par défaut de
   la 0.2.3 fonctionnent. Le profil `transjlc` (anciennes valeurs) est refusé par JLCPCB à cette date.

10. **Décalage observé le 7 octobre 2026 (face dessous, image `back.png`, v0.2.4).** Comparaison au pixel de la capture
    de l'éditeur et de celle du Gerber Viewer, en prenant les 4 trous de fixation comme référence : écart nul en Y
    (< 0,04 mm) ; en X l'image est plus à droite chez JLCPCB, de +0,26 mm (côté gauche) à +0,38 mm (côté droit).
    Notre chaîne (éditeur = composite = SVG) est cohérente à 0,01 mm près : l'écart vient de l'interprétation par
    JLCPCB (visualiseur, ou axe de miroir de la face dessous). On ignore s'il existe aussi sur la face dessus et sur la
    carte imprimée. Ajouts 0.2.5 : correction d'impression par face et mire de calage
    (`out/jlc_tests/RP2350_mire_calage.zip`) pour mesurer l'écart sur les deux faces.

11. **Bug corrigé en 0.2.6 : pastilles couvertes d'encre (signalé par JLCPCB le 10 octobre 2026).** Avec l'option
    couleur, l'aperçu JLCPCB ne montrait que 8 des 12 pastilles de l'USB-C J1. L'empreinte HCTL HC-TYPE-C-16P-01A
    empile deux pastilles identiques (A1/B12, A12/B1, A4/B9, A9/B4). Le Gerber F.Mask est correct, mais le SVG couleur
    découpe les ouvertures avec `fill-rule: evenodd` : deux ouvertures superposées **s'annulent** et l'encre couvrait
    ces 4 pastilles. Même défaut pour les 8 vias de chaque trou de fixation (points d'encre dans les trous) et les
    vias thermiques du RP2350. Correctif (`union.py`) : doublons retirés, ouvertures incluses dans une autre
    retirées, autres chevauchements unis en rectangles disjoints (pas de 0,01 mm). Contrôle ajouté : chaque centre de
    pastille doit rester ouvert, sinon erreur `E_MASK_COVERED`. Sur la carte RP2350 : 4 doublons + 41 ouvertures
    incluses (dessus), 32 (dessous), aucune pastille couverte. Le profil `transjlc` garde l'ancien comportement.

12. **Sérigraphie en double (10 octobre 2026, corrigé en 0.2.8).** Avec « sérigraphie imprimée dans l'image » en bleu
    sur le dessus, l'aperçu JLCPCB montrait la sérigraphie en noir par-dessus le bleu : le ZIP contenait toujours
    `Gerber_TopSilkscreenLayer.GTO`, que JLCPCB imprime en noir sur un PCB blanc. Ce défaut existait depuis la 0.2.4.
    Désormais, le Gerber de sérigraphie d'une face imprimée en couleur est remplacé par un Gerber vide
    (en-tête EasyEDA, aucune ouverture, aucun tracé).

## Validation manuelle chez JLCPCB (à faire par l'utilisateur)

Procédure : README, section « Valider chez JLCPCB ». Reporter ici les messages exacts.

| Date | Carte / ZIP | Profil | Options JLCPCB | Gerber Viewer (couleur visible ?) | Message / erreur exacte | Commande / rendu physique |
|---|---|---|---|---|---|---|
| 2026-10-06 | RP2350 (`RP2350_couleur_dos.zip`) | default 0.2.2 | blanc, ENIG | option couleur grisée | « multi-color silkscreen file is outdated… EasyEDA V3.2.135 or later » | — |
| | RP2350 `RP2350_test_A.zip` | Gerber 2.2.42.2 / SVG 2.4 | idem | | | |
| | RP2350 `RP2350_test_B.zip` | Gerber 3.2.148 / SVG 1.6 | idem | | | |
| 2026-10-06 | RP2350 `RP2350_test_C.zip` | Gerber 3.2.148 / SVG 2.4 (= défaut 0.2.3) | blanc, ENIG | **option couleur sélectionnable ; Gerber Viewer « Bottom » : image visible, bien placée, découpée au contour, ouvertures alignées** | aucun | commande non passée |
| | T2 (`out/matrix/T2-both/production/T2-both.zip`) | default | blanc, ENIG, 1 oz, EasyEDA multi-color silkscreen | | | |
| | T2 (`out/matrix/T2-transjlc/production/T2-transjlc.zip`) | transjlc | idem | | | |
