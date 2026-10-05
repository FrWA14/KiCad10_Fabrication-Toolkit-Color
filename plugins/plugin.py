# Modified 2026 by Fabrication Toolkit Color: JLCPCB multi-colour silkscreen support (see NOTICE).
import os
import wx
import pcbnew  # type: ignore

from .thread import ProcessThread
from .events import StatusEvent
from .options import AUTO_FILL_OPT, AUTO_TRANSLATE_OPT, EXCLUDE_DNP_OPT, EXTEND_EDGE_CUT_OPT, ALTERNATIVE_EDGE_CUT_OPT, EXTRA_LAYERS, ALL_ACTIVE_LAYERS_OPT, ARCHIVE_NAME, OPEN_BROWSER_OPT, BACKUP_OPT
from .options import TOP_IMAGE_OPT, BOTTOM_IMAGE_OPT, COLOR_FIT_OPT, COLOR_PROFILE_OPT, TOP_PLACEMENT_OPT, BOTTOM_PLACEMENT_OPT
from .utils import load_user_options, save_user_options, get_layer_names


# WX GUI form that show the plugin progress
class KiCadToJLCForm(wx.Frame):
    def __init__(self):
        wx.Dialog.__init__(
            self,
            None,
            id=wx.ID_ANY,
            title=u"Fabrication Toolkit (Color)",
            pos=wx.DefaultPosition,
            size=wx.DefaultSize,
            style=wx.DEFAULT_DIALOG_STYLE)

        # self.app = wx.PySimpleApp()
        icon = wx.Icon(os.path.join(os.path.dirname(__file__), 'icon.png'))
        self.SetIcon(icon)
        self.SetBackgroundColour(wx.LIGHT_GREY)

        self.SetSizeHints(wx.Size(600, 100), wx.DefaultSize)

        userOptions = load_user_options({
            EXTRA_LAYERS: "",
            ALL_ACTIVE_LAYERS_OPT: False,
            ARCHIVE_NAME: "",
            EXTEND_EDGE_CUT_OPT: False,
            ALTERNATIVE_EDGE_CUT_OPT: False,
            AUTO_TRANSLATE_OPT: True,
            AUTO_FILL_OPT: True,
            EXCLUDE_DNP_OPT: False,
            OPEN_BROWSER_OPT: True,
            BACKUP_OPT: True,
            TOP_IMAGE_OPT: "",
            BOTTOM_IMAGE_OPT: "",
            COLOR_FIT_OPT: "stretch",
            COLOR_PROFILE_OPT: "default",
            TOP_PLACEMENT_OPT: None,
            BOTTOM_PLACEMENT_OPT: None,
        })
        self.placements = {"top": userOptions[TOP_PLACEMENT_OPT], "bottom": userOptions[BOTTOM_PLACEMENT_OPT]}
        self.userOptions = userOptions

        self.mOptionsLabel = wx.StaticText(self, label='Options:')
        # self.mOptionsSeparator = wx.StaticLine(self)

        layers = get_layer_names(pcbnew.GetBoard())
        self.mAdditionalLayersControl = wx.TextCtrl(self, size=wx.Size(600, 50))
        self.mAdditionalLayersControl.Hint = "Additional layers (comma-separated) [optional]"
        self.mAdditionalLayersControl.AutoComplete(layers)
        self.mAdditionalLayersControl.Enable()
        self.mAdditionalLayersControl.SetValue(userOptions[EXTRA_LAYERS])
        self.mArchiveNameControl = wx.TextCtrl(self, size=wx.Size(600, 50))
        self.mArchiveNameControl.Hint = "Archive name (e.g. ${TITLE}_${REVISION}) [optional]"
        self.mArchiveNameControl.Enable()
        self.mArchiveNameControl.SetValue(userOptions[ARCHIVE_NAME])
        self.mAllActiveLayersCheckbox = wx.CheckBox(self, label='Plot all active layers')
        self.mAllActiveLayersCheckbox.SetValue(userOptions[ALL_ACTIVE_LAYERS_OPT])
        self.mExtendEdgeCutsCheckbox = wx.CheckBox(self, label='Set User.1 as V-Cut layer')
        self.mExtendEdgeCutsCheckbox.SetValue(userOptions[EXTEND_EDGE_CUT_OPT])
        self.mAlternativeEdgeCutsCheckbox = wx.CheckBox(self, label='Set User.2 as alternative Edge-Cut layer')
        self.mAlternativeEdgeCutsCheckbox.SetValue(userOptions[ALTERNATIVE_EDGE_CUT_OPT])
        self.mAutomaticTranslationCheckbox = wx.CheckBox(self, label='Apply automatic component translations')
        self.mAutomaticTranslationCheckbox.SetValue(userOptions[AUTO_TRANSLATE_OPT])
        self.mAutomaticFillCheckbox = wx.CheckBox(self, label='Apply automatic fill for all zones')
        self.mAutomaticFillCheckbox.SetValue(userOptions[AUTO_FILL_OPT])
        self.mExcludeDnpCheckbox = wx.CheckBox(self, label='Exclude DNP components from BOM')
        self.mExcludeDnpCheckbox.SetValue(userOptions[EXCLUDE_DNP_OPT])
        self.mOpenBrowserCheckbox = wx.CheckBox(self, label='Open browser after generation')
        self.mOpenBrowserCheckbox.SetValue(userOptions[OPEN_BROWSER_OPT])
        self.mBackupCheckbox = wx.CheckBox(self, label='Generate backup files')
        self.mBackupCheckbox.SetValue(userOptions[BACKUP_OPT])

        imageWildcard = "Images PNG/JPG (*.png;*.jpg;*.jpeg)|*.png;*.jpg;*.jpeg"
        self.mColorLabel = wx.StaticText(self, label='Sérigraphie couleur JLCPCB (optionnel) :')
        self.mTopImagePicker = wx.FilePickerCtrl(self, message="Image couleur, face dessus", wildcard=imageWildcard,
                                                 size=wx.Size(600, -1), style=wx.FLP_OPEN | wx.FLP_FILE_MUST_EXIST | wx.FLP_USE_TEXTCTRL)
        self.mTopImagePicker.SetPath(userOptions[TOP_IMAGE_OPT] or "")
        self.mTopImagePicker.SetToolTip("Face dessus, vue de dessus. Laisser vide : pas d'impression couleur.")
        self.mBottomImagePicker = wx.FilePickerCtrl(self, message="Image couleur, face dessous (vue de dessous)", wildcard=imageWildcard,
                                                    size=wx.Size(600, -1), style=wx.FLP_OPEN | wx.FLP_FILE_MUST_EXIST | wx.FLP_USE_TEXTCTRL)
        self.mBottomImagePicker.SetPath(userOptions[BOTTOM_IMAGE_OPT] or "")
        self.mBottomImagePicker.SetToolTip("Face dessous, telle qu'on la voit en retournant la carte.")
        self.mTopImageLabel = wx.StaticText(self, label='Image face dessus :')
        self.mBottomImageLabel = wx.StaticText(self, label='Image face dessous (vue de dessous) :')
        self.mColorFitCheckbox = wx.CheckBox(self, label="Conserver les proportions de l'image (ajoute des marges)")
        self.mColorFitCheckbox.SetValue(userOptions[COLOR_FIT_OPT] == "contain")
        self.mPlacementButton = wx.Button(self, label="Placer / redimensionner les images (vues dessus et dessous)…")
        self.mPlacementButton.Bind(wx.EVT_BUTTON, self.onPlacementButtonClick)
        self.mPlacementLabel = wx.StaticText(self, label="")
        for picker in (self.mTopImagePicker, self.mBottomImagePicker):
            picker.Bind(wx.EVT_FILEPICKER_CHANGED, lambda e: self.updatePlacementLabel())
        self.updatePlacementLabel()

        self.mGaugeStatus = wx.Gauge(
            self, wx.ID_ANY, 100, wx.DefaultPosition, wx.Size(600, 20), wx.GA_HORIZONTAL)
        self.mGaugeStatus.SetValue(0)
        self.mGaugeStatus.Hide()

        self.mGenerateButton = wx.Button(self, label='Generate', size=wx.Size(600, 60))
        self.mGenerateButton.Bind(wx.EVT_BUTTON, self.onGenerateButtonClick)

        boxSizer = wx.BoxSizer(wx.VERTICAL)

        boxSizer.Add(self.mOptionsLabel, 0, wx.ALL, 5)
        # boxSizer.Add(self.mOptionsSeparator, 0, wx.ALL, 5)
        boxSizer.Add(self.mArchiveNameControl, 0, wx.ALL, 5)
        boxSizer.Add(self.mAdditionalLayersControl, 0, wx.ALL, 5)
        boxSizer.Add(self.mAllActiveLayersCheckbox, 0, wx.ALL, 5)
        boxSizer.Add(self.mExtendEdgeCutsCheckbox, 0, wx.ALL, 5)
        boxSizer.Add(self.mAlternativeEdgeCutsCheckbox, 0, wx.ALL, 5)
        boxSizer.Add(self.mAutomaticTranslationCheckbox, 0, wx.ALL, 5)
        boxSizer.Add(self.mAutomaticFillCheckbox, 0, wx.ALL, 5)
        boxSizer.Add(self.mExcludeDnpCheckbox, 0, wx.ALL, 5)
        boxSizer.Add(self.mOpenBrowserCheckbox, 0, wx.ALL, 5)
        boxSizer.Add(self.mBackupCheckbox, 0, wx.ALL, 5)
        boxSizer.Add(self.mColorLabel, 0, wx.ALL, 5)
        boxSizer.Add(self.mTopImageLabel, 0, wx.LEFT | wx.RIGHT, 5)
        boxSizer.Add(self.mTopImagePicker, 0, wx.ALL, 5)
        boxSizer.Add(self.mBottomImageLabel, 0, wx.LEFT | wx.RIGHT, 5)
        boxSizer.Add(self.mBottomImagePicker, 0, wx.ALL, 5)
        boxSizer.Add(self.mColorFitCheckbox, 0, wx.ALL, 5)
        boxSizer.Add(self.mPlacementButton, 0, wx.ALL | wx.EXPAND, 5)
        boxSizer.Add(self.mPlacementLabel, 0, wx.LEFT | wx.RIGHT, 5)
        boxSizer.Add(self.mGaugeStatus, 0, wx.ALL, 5)
        boxSizer.Add(self.mGenerateButton, 0, wx.ALL, 5)

        self.SetSizer(boxSizer)
        self.Layout()
        boxSizer.Fit(self)

        self.Centre(wx.BOTH)

        # Bind the ESC key event to a handler
        self.Bind(wx.EVT_CHAR_HOOK, self.onKey)

    # Close the dialog when pressing the ESC key
    def onKey(self, event):
        if event.GetKeyCode() == wx.WXK_ESCAPE:
            self.Close(True)
        else:
            event.Skip()

    def onGenerateButtonClick(self, event):
        options = dict()
        options[ARCHIVE_NAME] = self.mArchiveNameControl.GetValue()
        options[EXTRA_LAYERS] = self.mAdditionalLayersControl.GetValue()
        options[ALL_ACTIVE_LAYERS_OPT] = self.mAllActiveLayersCheckbox.GetValue()
        options[EXTEND_EDGE_CUT_OPT] = self.mExtendEdgeCutsCheckbox.GetValue()
        options[ALTERNATIVE_EDGE_CUT_OPT] = self.mAlternativeEdgeCutsCheckbox.GetValue()
        options[AUTO_TRANSLATE_OPT] = self.mAutomaticTranslationCheckbox.GetValue()
        options[AUTO_FILL_OPT] = self.mAutomaticFillCheckbox.GetValue()
        options[EXCLUDE_DNP_OPT] = self.mExcludeDnpCheckbox.GetValue()
        options[OPEN_BROWSER_OPT] = self.mOpenBrowserCheckbox.GetValue()
        options[BACKUP_OPT] = self.mBackupCheckbox.GetValue()
        options[TOP_IMAGE_OPT] = self.mTopImagePicker.GetPath().strip()
        options[BOTTOM_IMAGE_OPT] = self.mBottomImagePicker.GetPath().strip()
        options[COLOR_FIT_OPT] = "contain" if self.mColorFitCheckbox.GetValue() else "stretch"
        options[COLOR_PROFILE_OPT] = self.userOptions.get(COLOR_PROFILE_OPT) or "default"  # set by hand in the options file
        options[TOP_PLACEMENT_OPT] = self.placementFor("top", options[TOP_IMAGE_OPT])
        options[BOTTOM_PLACEMENT_OPT] = self.placementFor("bottom", options[BOTTOM_IMAGE_OPT])

        save_user_options(options)

        self.mOptionsLabel.Hide()
        self.mArchiveNameControl.Hide()
        self.mAdditionalLayersControl.Hide()
        self.mAllActiveLayersCheckbox.Hide()
        self.mExtendEdgeCutsCheckbox.Hide()
        self.mAlternativeEdgeCutsCheckbox.Hide()
        self.mAutomaticTranslationCheckbox.Hide()
        self.mAutomaticFillCheckbox.Hide()
        self.mExcludeDnpCheckbox.Hide()
        self.mOpenBrowserCheckbox.Hide()
        self.mBackupCheckbox.Hide()
        for control in (self.mColorLabel, self.mTopImageLabel, self.mTopImagePicker, self.mBottomImageLabel,
                        self.mBottomImagePicker, self.mColorFitCheckbox, self.mPlacementButton, self.mPlacementLabel):
            control.Hide()
        self.mGenerateButton.Hide()
        self.mGaugeStatus.Show()

        self.Fit()
        self.SetTitle('Fabrication Toolkit (Processing...)')

        StatusEvent.invoke(self, self.updateDisplay)
        ProcessThread(self, options, openBrowser=options[OPEN_BROWSER_OPT])

    def placementFor(self, side, image):
        '''Placement only applies to the image it was made for.'''
        p = self.placements.get(side)
        if not p or not image:
            return None
        same = os.path.normcase(os.path.abspath(p["image"])) == os.path.normcase(os.path.abspath(image))
        return p if same else None

    def updatePlacementLabel(self):
        parts = []
        for side, picker, name in (("top", self.mTopImagePicker, "dessus"), ("bottom", self.mBottomImagePicker, "dessous")):
            p = self.placementFor(side, picker.GetPath().strip())
            if p:
                parts.append("{} : {:.1f} x {:.1f} mm".format(name, p["w"], p["h"]))
        self.mPlacementLabel.SetLabel("Placement : " + (" ; ".join(parts) if parts else
                                      "aucun (l'image couvre tout le contour)"))

    def onPlacementButtonClick(self, event):
        from .placement_dialog import PlacementDialog
        from .color_silkscreen import board_view
        from .color_silkscreen.errors import ColorSilkError
        try:
            view = board_view.extract(pcbnew.GetBoard())
        except ColorSilkError as e:
            wx.MessageBox(e.user_text(), "Sérigraphie couleur", wx.OK | wx.ICON_ERROR)
            return
        current = {}
        for side, picker in (("top", self.mTopImagePicker), ("bottom", self.mBottomImagePicker)):
            image = picker.GetPath().strip()
            current[side] = self.placementFor(side, image)
        dlg = PlacementDialog(self, view, current)
        for side, picker in (("top", self.mTopImagePicker), ("bottom", self.mBottomImagePicker)):
            image = picker.GetPath().strip()
            if image and not current[side] and os.path.isfile(image):
                dlg.load_image(image, side)
        dlg.set_side("top")
        if dlg.ShowModal() == wx.ID_OK:
            self.placements = dlg.result()
            for side, picker in (("top", self.mTopImagePicker), ("bottom", self.mBottomImagePicker)):
                picker.SetPath(self.placements[side]["image"] if self.placements[side] else "")
            self.updatePlacementLabel()
            self.Layout()
        dlg.Destroy()

    def updateDisplay(self, status):
        if status.data == -1:
            self.SetTitle('Fabrication Toolkit (Done!)')
            pcbnew.Refresh()
            self.Destroy()
        else:
            self.mGaugeStatus.SetValue(int(status.data))


# Plugin definition
class Plugin(pcbnew.ActionPlugin):
    def __init__(self):
        self.name = "Fabrication Toolkit (Color)"
        self.category = "Manufacturing"
        self.description = "Fabrication Toolkit + JLCPCB multi-colour silkscreen from a PNG/JPG image"
        self.pcbnew_icon_support = hasattr(self, "show_toolbar_button")
        self.show_toolbar_button = True
        self.icon_file_name = os.path.join(os.path.dirname(__file__), 'icon.png')
        self.dark_icon_file_name = os.path.join(os.path.dirname(__file__), 'icon.png')

    def Run(self):
        KiCadToJLCForm().Show()
