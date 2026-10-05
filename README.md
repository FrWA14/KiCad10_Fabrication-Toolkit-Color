# Fabrication Toolkit Color : sérigraphie couleur JLCPCB pour KiCad 10

Fork de [Fabrication Toolkit](https://github.com/bennymeg/Fabrication-Toolkit) (Apache-2.0). Il ajoute une image
couleur (PNG ou JPG) sur la face dessus et/ou dessous, et produit un ZIP commandable chez JLCPCB avec l'option
**« EasyEDA multi-color silkscreen »**.

Sans image, le comportement et le ZIP sont **identiques** à Fabrication Toolkit (vérifié par test). BOM et CPL ne
changent pas.

## ⚠️ Avertissement

- Le format des fichiers couleur (`.FCTS`, `.FCBS`, `.FCBO`, `.FCBM`) **n'est pas documenté**. Il vient de la
  rétro-ingénierie de [TransJLC](https://github.com/HalfSweet/TransJLC), dont ce plugin est un portage Python.
  JLCPCB indique n'accepter que les exports d'EasyEDA Pro. Le format peut changer sans préavis.
- Pour être reconnu comme « couleur », le ZIP imite un export EasyEDA Pro : Gerbers renommés, en-tête
  `G04 EasyEDA Pro …` et ouverture « empreinte ». La géométrie des Gerbers n'est pas modifiée.
- **Aucune commande réelle n'a encore validé cette sortie.** Vérifier toujours l'aperçu dans le *Gerber Viewer* de
  JLCPCB avant de payer (voir « Valider chez JLCPCB »).
- Projet non affilié à JLCPCB ni à EasyEDA.

## Installation

**Paquet PCM** (recommandé) :

```bash
python tools/build_pcm.py
```

Puis dans KiCad 10 : *Gestionnaire de plugins et de contenus → Installer depuis un fichier…* →
`dist/fabrication-toolkit-color-0.2.0.zip`.

**Copie de développement** : copier (ou lier) le dossier `plugins/` dans
`%USERPROFILE%\Documents\KiCad\10.0\scripting\plugins\fabrication_toolkit_color\`, puis *Outils → Plugins externes →
Actualiser*.

Le bouton s'appelle **Fabrication Toolkit (Color)**. Il peut coexister avec Fabrication Toolkit d'origine.

## Utilisation

### Dans KiCad

Les réglages habituels de Fabrication Toolkit sont suivis de :

- **Image face dessus** : PNG/JPG, vue de dessus.
- **Image face dessous** : PNG/JPG, **telle qu'on la voit en retournant la carte** (le plugin applique le miroir).
- **Conserver les proportions** : ajoute des marges (transparentes en PNG, blanches en JPG) au lieu de déformer.

- **Placer / redimensionner les images…** : ouvre l'éditeur visuel (voir ci-dessous).

Les chemins et placements sont mémorisés par carte dans `fabrication-toolkit-options.json`. Résultat dans `production/` :
`<nom>.zip`, `color_silkscreen_report.json` et `color_silkscreen.log`. En cas d'erreur, une fenêtre affiche le
code, le message et une piste de correction.

### Éditeur de placement (vues dessus / dessous)

La carte y est dessinée comme JLCPCB la fabriquera : vernis blanc, cuivre nu doré (aucune encre n'y est
déposée), composants de la face en gris, contour Edge.Cuts en vert.

- **Vue de dessus / Vue de dessous** : la vue de dessous montre la carte retournée (miroir), telle qu'on la regarde.
- **Charger une image…** : l'image arrive entière, centrée, dans le contour.
- Souris : glisser pour **déplacer**, tirer un **coin** pour redimensionner (proportions gardées ; Maj ou
  « Proportions libres » pour déformer), **molette** pour agrandir/réduire autour du curseur. Flèches : 0,1 mm
  (Maj : 1 mm).
- Boutons **Contenir** (image entière dans le contour), **Couvrir** (remplit tout le contour), **Centrer**,
  **Rotation 90°**, **Retirer**. Champs Centre X/Y, Largeur, Hauteur en mm, et résolution effective (DPI, en rouge
  sous 150).
- **Aperçu découpé au contour** : montre déjà ce qui restera.

À la génération, chaque image placée est rendue à 1200 DPI sur toute la carte, puis **tout ce qui sort du contour
fermé Edge.Cuts (et des découpes internes) est retiré**. Cette image découpée est celle qui est chiffrée dans
`.FCTS` / `.FCBS` du ZIP, avec sa position. Copies lisibles dans `production/` :
`color_top_composite.png`, `color_bottom_composite.png` (ou `.jpg` au-delà de 3 Mo) et `color_placement.json`.
Ces fichiers restent **hors** du ZIP envoyé à JLCPCB, pour ne pas perturber leur contrôle des fichiers.

### En ligne de commande (sans interface)

```bash
"C:\Program Files\KiCad\10.0\bin\python.exe" -m plugins.cli -p ma_carte.kicad_pcb --topColorImage logo.png --bottomColorImage dos.jpg --report out/report.json --archiveName ma_carte
```

| Option | Rôle |
|---|---|
| `--topColorImage`, `--bottomColorImage` | images PNG/JPG (au moins une pour activer la couleur) |
| `--colorFit stretch\|contain` | déformer l'image au format de la carte (défaut) ou ajouter des marges |
| `--colorProfile default\|transjlc` | `transjlc` reproduit la sortie de TransJLC 0.4.0, bugs compris (voir TESTS.md) |
| `--report PATH`, `--log PATH` | rapport JSON et log (défaut : dans `production/`) |
| `--placement FILE` | placements de l'éditeur (`color_placement.json`) : position, taille et rotation par face |
| `--debugSvg DIR` | écrit aussi les SVG **en clair** (avant chiffrement) pour les inspecter dans un navigateur |

Code de sortie : `0` si tout va bien, `1` en cas d'échec (détail dans le rapport), `2` si `pcbnew` est introuvable.

## Préparer l'image

- Imprimante UV 6 couleurs à **1200 DPI**. Taille idéale en pixels : largeur (mm) / 25,4 × 1200. Une carte de
  50 mm demande donc 2362 px.
  Au-delà, l'image est réduite automatiquement (avertissement `W_IMAGE_RESAMPLED`). En dessous de 150 DPI, un
  avertissement `W_IMAGE_LOW_DPI` est émis.
- L'image couvre le **rectangle englobant du contour** (Edge.Cuts). Les zones transparentes du PNG laissent le blanc
  de la carte.
- Les ouvertures du masque de soudure (pastilles, vias non couverts) sont automatiquement exclues de l'impression.
- La sérigraphie classique (F/B.Silkscreen) est conservée telle quelle dans le ZIP.

## Commander chez JLCPCB

| Option | Valeur |
|---|---|
| Matériau | FR4 |
| Couleur du PCB | **Blanc** (obligatoire) |
| Finition | **ENIG** (obligatoire) |
| Couches | 2 ou 4 |
| Cuivre extérieur | 1 oz |
| Advanced Options → *Silkscreen Technology* | **EasyEDA multi-color silkscreen** |
| Livraison | Single PCB ou Panel by Customer (la panelisation JLCPCB ne duplique pas la couleur) |

- Si ces options n'apparaissent pas : mettre au panier, puis *edit order*.
- Prévoir du cuivre sur chaque face imprimée : une carte sans cuivre peut être signalée par les ingénieurs JLCPCB.
- Si JLCPCB doit ajuster les Gerbers de plus de **2 mm**, la couleur est retirée. Le plugin compare donc le contour
  de la carte au Gerber et refuse un écart supérieur à 2 mm (`E_BOARD_TOO_LARGE_ADJUST`).

### Valider chez JLCPCB

1. Générer le ZIP d'une petite carte (type T2 : `tests/make_boards.py`).
2. jlcpcb.com → *Add Gerber file* → envoyer le ZIP. Régler les options ci-dessus.
3. Ouvrir le **Gerber Viewer** de JLCPCB : la couleur y est simulée. Un visualiseur Gerber ordinaire montre une zone vide,
   c'est normal.
4. Si JLCPCB refuse le fichier ou retire la couleur, recommencer avec `--colorProfile transjlc` pour comparer, puis
   noter le message exact dans `TESTS.md`.
5. Ne commander une carte d'essai qu'après un aperçu correct.

## Codes d'erreur

| Code | Cause |
|---|---|
| `E_NO_PCBNEW` | lancé hors du Python de KiCad |
| `E_OUTLINE_MISSING` | pas de contour Edge.Cuts |
| `E_OUTLINE_PARSE` | Gerber de contour illisible ou dégénéré |
| `E_IMAGE_MISSING` | chemin d'image introuvable |
| `E_IMAGE_FORMAT` | ni PNG ni JPG (BMP, SVG… refusés) |
| `E_IMAGE_TOO_SMALL` | moins de 32 px de côté |
| `E_MASK_PARSE` | Gerber de masque illisible |
| `E_CRYPTO_BACKEND` | aucun moteur AES-GCM utilisable |
| `E_ZIP` | écriture impossible |
| `E_BOARD_TOO_LARGE_ADJUST` | contour Gerber et contour de la carte écartés de plus de 2 mm |
| `E_INTERNAL` | autre erreur (voir le log) |

Les avertissements (`W_*`) sont listés dans le rapport et affichés en fin de génération.

## Fonctionnement

```
plugins/
  thread.py            # FT : étape couleur insérée entre les perçages et l'archive
  cli.py, plugin.py    # FT : options couleur (CLI, boîte de dialogue)
  color_silkscreen/
    generate.py        # orchestration -> rapport
    jlc_convert.py     # noms/en-têtes EasyEDA (port TransJLC converter/gerber/patterns)
    gerber.py          # lecteur RS-274X minimal
    outline.py         # bornes du contour
    mask.py            # ouvertures du masque -> chemins SVG
    svg_builder.py     # SVG dessus/dessous/contour (port de svg.rs)
    crypto.py          # RSA-OAEP-SHA256 + AES-128-GCM (nonce 16 octets)
    marker.py          # .FCBM (Gerber des repères)
    image.py           # validation, 1200 DPI, proportions
    board_view.py      # contour, pastilles, composants (pcbnew -> données simples)
    placement.py       # composition 1200 DPI + découpe au contour Edge.Cuts
  placement_dialog.py  # éditeur wx (vues dessus/dessous)
```

Fichiers couleur : `RSA-OAEP(clé AES) ‖ RSA-OAEP(IV) ‖ AES-128-GCM(SVG) ‖ tag`, avec la clé publique de JLCPCB.
Un SVG contient l'image en base64, détourée par le contour et par les ouvertures du masque.

Tests et constats (dont un bug de TransJLC sur les ouvertures de masque) : [TESTS.md](TESTS.md). Environnement :
[ENV.md](ENV.md).

## Licences

- Fabrication Toolkit : Apache-2.0, © Benny Megidish et contributeurs ([LICENSE](LICENSE)). Les fichiers modifiés
  portent une mention.
- Portage de TransJLC : Apache-2.0, © HalfSweet ([plugins/color_silkscreen/LICENSE-TransJLC](plugins/color_silkscreen/LICENSE-TransJLC)).
- Détails et attributions : [NOTICE](NOTICE). Documentation d'origine de FT :
  [FABRICATION_TOOLKIT_README.md](FABRICATION_TOOLKIT_README.md).
