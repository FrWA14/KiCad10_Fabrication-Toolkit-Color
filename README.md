# Fabrication Toolkit Color : sérigraphie couleur JLCPCB pour KiCad 10

Fork de [Fabrication Toolkit](https://github.com/bennymeg/Fabrication-Toolkit) (Apache-2.0). Il ajoute une image
couleur (PNG ou JPG) sur la face dessus et/ou dessous, et produit un ZIP commandable chez JLCPCB avec l'option
**« EasyEDA multi-color silkscreen »**.

Sans image, le ZIP Gerber est **identique** à celui de Fabrication Toolkit (vérifié par test). Seule différence
voulue : le fichier de positions (CPL) ne liste que les composants présents dans le BOM. Un composant exclu du BOM
(trou de fixation, logo, point de test…) ou « board only » n'y figure plus, même si sa case « Exclure des fichiers
de position » n'est pas cochée dans KiCad ; les assembleurs refusent les lignes de CPL sans ligne de BOM.

## ⚠️ Avertissement

- Le format des fichiers couleur (`.FCTS`, `.FCBS`, `.FCBO`, `.FCBM`) **n'est pas documenté**. Il vient de la
  rétro-ingénierie de [TransJLC](https://github.com/HalfSweet/TransJLC), dont ce plugin est un portage Python.
  JLCPCB indique n'accepter que les exports d'EasyEDA Pro. Le format peut changer sans préavis.
- Pour être reconnu comme « couleur », le ZIP imite un export EasyEDA Pro : Gerbers renommés, en-tête
  `G04 EasyEDA Pro …` et ouverture « empreinte ». La géométrie des Gerbers n'est pas modifiée.
- **Validé à l'upload le 6 octobre 2026** (v0.2.3) : JLCPCB accepte l'option *EasyEDA multi-color silkscreen* et
  son *Gerber Viewer* affiche l'image au bon endroit. **Aucune carte n'a encore été fabriquée** : le rendu physique
  reste à confirmer. Vérifier toujours l'aperçu avant de payer (voir « Valider chez JLCPCB »).
- JLCPCB refuse les fichiers marqués avec une ancienne version d'EasyEDA (« multi-color silkscreen file is outdated…
  V3.2.135 or later »). Les marqueurs par défaut (`3.2.148`, `2.4(2026-05-08)`) passent ; s'ils sont refusés un jour,
  les changer avec `--easyedaVersion` / `--edaVersion` (ou `COLOR_EASYEDA_VERSION` / `COLOR_EDA_VERSION` dans
  `fabrication-toolkit-options.json`).
- Projet non affilié à JLCPCB ni à EasyEDA.

## Installation

**Paquet PCM** (recommandé) :

```bash
python tools/build_pcm.py
```

Puis dans KiCad 10 : *Gestionnaire de plugins et de contenus → Installer depuis un fichier…* →
`dist/fabrication-toolkit-color-0.3.0.zip`.

**Copie de développement** : copier (ou lier) le dossier `plugins/` dans
`%USERPROFILE%\Documents\KiCad\10.0\scripting\plugins\fabrication_toolkit_color\`, puis *Outils → Plugins externes →
Actualiser*.

Le bouton s'appelle **Fabrication Toolkit (Color)**. La version utilisée s'affiche dans le titre de la fenêtre. Le plugin recharge son code à chaque ouverture : une mise à jour par le gestionnaire est prise en compte sans redémarrer KiCad (à partir de la 0.2.2 ; depuis une version plus ancienne, redémarrer KiCad une fois). Il peut coexister avec Fabrication Toolkit d'origine.

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
- **Correction d'impression de cette face, X / Y (mm)** (ligne sous la couleur de sérigraphie), par face : décale toute l'impression couleur de la face (image et sérigraphie
  imprimée) pour compenser un écart mesuré chez JLCPCB. Repère de la vue affichée : X vers la droite, Y vers le bas.
  L'aperçu reste à la position voulue ; seul l'export est décalé.
- **Imprimer la sérigraphie de cette face dans l'image couleur** + **Couleur** : avec le procédé couleur (PCB blanc,
  ENIG), la sérigraphie blanche classique n'apparaît pas. Cette option dessine F.Silkscreen (vue de dessus) ou
  B.Silkscreen (vue de dessous) **dans l'image**, au-dessus de la photo, dans la couleur choisie. Elle fonctionne aussi
  **sans image** sur la face : seule la sérigraphie est alors imprimée en couleur. Réglage par face, mémorisé avec la
  carte.
  Le Gerber de sérigraphie classique de cette face est alors **vidé** dans le ZIP (il garde l'empreinte EasyEDA) : sur un PCB blanc, JLCPCB
  l'imprimerait sinon en noir par-dessus la couleur. Sans cette option, la sérigraphie classique reste imprimée
  (en noir) au-dessus de l'image. La case **« Garder aussi la sérigraphie classique (noire) »** conserve ce Gerber (comportement de la 0.2.7).
- **Sérigraphie : F.Silkscreen / B.Silkscreen** : la sérigraphie de la face affichée en noir sur le blanc (textes, logos, contours), au-dessus de l'image ; celle de l'autre face en gris léger, en transparence. Décocher pour voir l'image seule.

À la génération, chaque image placée est rendue à 1200 DPI sur toute la carte, puis **tout ce qui sort du contour
fermé Edge.Cuts (et des découpes internes) est retiré**. Cette image découpée est celle qui est chiffrée dans
`.FCTS` / `.FCBS` du ZIP, avec sa position. Copies lisibles dans `production/` :
`color_top_composite.png`, `color_bottom_composite.png` (ou `.jpg` au-delà de 3 Mo) et `color_placement.json`.
Ces fichiers restent **hors** du ZIP envoyé à JLCPCB, pour ne pas perturber leur contrôle des fichiers.

### Calques de l'impression couleur (0.3.0)

Pour chaque face, l'image envoyée à JLCPCB est construite en calques, dans cet ordre :

1. **Image** placée dans l'éditeur (ou étirée sur le contour si elle n'est pas placée).
2. **Sérigraphie** de la face, au-dessus de l'image. Activée par défaut, en **noir**, dès qu'une image est chargée
   (case « Couleur par défaut (noir) ») ; choisir une couleur décoche cette case. Le Gerber de sérigraphie classique
   est alors vidé, avec son empreinte EasyEDA.
3. **Découpe booléenne** : l'image est retirée sur toutes les ouvertures du masque (pastilles à souder, pastilles
   thermiques, anneaux des trous de fixation) et sur tous les perçages (pastilles, vias, trous oblongs). Contours
   exacts fournis par KiCad.
4. **Contour** : tout ce qui sort d'Edge.Cuts (et des découpes internes) est retiré.

Le SVG chiffré garde en plus sa propre découpe des ouvertures (double protection).

### Aperçu de l'export et pré-contrôle (0.3.0)

Après chaque génération, une fenêtre **« Aperçu de l'export JLCPCB »** s'ouvre (et le bouton « Aperçu du dernier
export » la rouvre). Elle reconstruit chaque face **à partir des fichiers du ZIP** : vernis blanc, image couleur
(découpée comme chez JLCPCB), sérigraphie Gerber, cuivre nu, perçages, contour. Calques à cocher, zoom à la molette,
déplacement en glissant. Les mêmes images sont écrites dans `production/preview_top.png` et `preview_bottom.png`.

Dessous, le **pré-contrôle** vérifie ce que JLCPCB a déjà refusé : couches présentes, en-tête et version EasyEDA
(≥ 3.2.135), empreinte EasyEDA valide sur chaque Gerber, fichiers couleur présents, sérigraphie classique vidée
quand elle est imprimée en couleur, proportions de l'image, taille du ZIP. Une erreur de pré-contrôle est signalée
(`E_PRECHECK`) mais le ZIP reste disponible.

Limite : l'aperçu montre le contenu des fichiers, pas l'acceptation par JLCPCB (option couleur, contrôles internes).

### Mire de calage

Case **« Mire de calage à la place des images »** dans la fenêtre principale (ou `--calibration`) : sur les deux faces,
l'image est remplacée par des croix rouges et des cercles bleus centrés sur chaque pastille de cuivre nu, des règles
graduées au millimètre le long des bords et une flèche « +X ». Dans le Gerber Viewer de JLCPCB, zoomer sur les
pastilles des quatre coins :
- croix centrées : rien à corriger ;
- croix décalées d'une même valeur partout : saisir l'opposé dans « Correction d'impression » (ex. croix 0,3 mm trop
  à droite → X = −0,30) ;
- décalage qui grandit d'un bord à l'autre : écart d'échelle, à me signaler avec des captures.

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
| `--keepClassicSilk` | avec `--top/bottomSilkColor` : garder aussi le Gerber de sérigraphie classique |
| `--topSilkColor`, `--bottomSilkColor` | `#RRGGBB` : imprime F/B.Silkscreen dans l'image couleur de cette face (même sans image) |
| `--topOffset DX,DY`, `--bottomOffset=DX,DY` | correction d'impression en mm (valeur négative : écrire `--bottomOffset=-0.3,0`) |
| `--calibration` | mire de calage sur les deux faces à la place des images |
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
- Les ouvertures du masque de soudure (pastilles, vias non couverts) sont automatiquement exclues de l'impression. Les ouvertures superposées (pastilles empilées d'un USB-C, vias dans une pastille) sont fusionnées, et la génération s'arrête (`E_MASK_COVERED`) si une pastille devait rester sous l'encre. Règle retenue : **aucune encre sur une ouverture de masque**, y compris les vias des trous de fixation et des pastilles ou plans thermiques ; seuls les vias recouverts de vernis (tented) reçoivent l'encre.
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
| `E_MASK_COVERED` | une pastille resterait couverte d'encre couleur (ouverture de masque manquante ou annulée) |
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
