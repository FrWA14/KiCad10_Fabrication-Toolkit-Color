"""Typed errors: every failure carries a code, a message and a fix hint."""

HINTS = {
    "E_NO_PCBNEW": "Lancer avec le Python de KiCad 10 (bin/python.exe), qui fournit le module pcbnew.",
    "E_OUTLINE_MISSING": "Dessiner le contour de la carte sur la couche Edge.Cuts (contour fermé).",
    "E_OUTLINE_PARSE": "Ré-exporter les Gerbers ; vérifier que le fichier Edge.Cuts n'est pas vide ou corrompu.",
    "E_IMAGE_FORMAT": "Fournir une image PNG ou JPG (seuls formats acceptés par JLCPCB).",
    "E_IMAGE_TOO_SMALL": "Fournir une image plus grande (idéalement 1200 DPI à la taille de la carte).",
    "E_IMAGE_MISSING": "Vérifier le chemin de l'image.",
    "E_MASK_PARSE": "Ré-exporter les Gerbers ; le fichier de masque de soudure est illisible.",
    "E_CRYPTO_BACKEND": "Aucun moteur de chiffrement utilisable ; signaler le problème avec le log.",
    "E_ZIP": "Vérifier les droits d'écriture et l'espace disque du dossier de sortie.",
    "E_BOARD_TOO_LARGE_ADJUST": "Le contour Gerber et l'image couleur diffèrent de plus de 2 mm : "
                                "vérifier Edge.Cuts, l'origine auxiliaire et les options User.1/User.2.",
    "E_GERBER_MISSING": "Le jeu de Gerbers est incomplet ; vérifier les couches activées.",
    "E_PLACEMENT": "Corriger le placement (taille > 0, rotation 0/90/180/270) dans l'éditeur de placement.",
    "E_MASK_COVERED": "Des pastilles seraient couvertes d'encre couleur : vérifier les ouvertures de masque "
                      "(F/B.Mask) de ces pastilles et signaler le cas avec le log.",
    "E_INTERNAL": "Erreur inattendue ; joindre color_silkscreen.log au rapport de bug.",
}


class ColorSilkError(Exception):
    def __init__(self, code, message, hint=None):
        super().__init__("[{}] {}".format(code, message))
        self.code = code
        self.message = message
        self.hint = hint or HINTS.get(code, "")

    def as_dict(self):
        return {"code": self.code, "message": self.message, "hint": self.hint}

    def user_text(self):
        return "{}\n\n{}\n\nPiste : {}".format(self.code, self.message, self.hint)
